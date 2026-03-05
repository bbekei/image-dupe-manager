"""
backend/api.py — pywebview API bridge for DejaView.

Exposes Python backend functions to the React frontend via pywebview's
JS<->Python bridge. Each public method becomes callable from JavaScript as:

    window.pywebview.api.method_name(args)

This module is the ONLY interface between the React frontend and the Python
backend. It wraps existing core/, data/, and sync modules.

Event forwarding: Scanner and PlanExecutor emit Qt signals which are forwarded
to the React frontend as CustomEvent objects via window.evaluate_js().
"""

import base64
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import webview

from core.selection import SelectionPreset, apply_preset
from core.similarity import build_similarity_groups
from core.similarity_selection import (
    SimilarityPreset,
    apply_similarity_preset,
    recommend_keeper,
)
from core.trash import purge_expired, recover, soft_delete
from data.db import Database
from data.export import build_export_payload, import_payload

log = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return {}
    return dict(row)


def _rows_to_list(rows) -> list[dict]:
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]


def _emit_event(window: webview.Window, event_name: str, detail: dict) -> None:
    """Dispatch a CustomEvent to the React frontend via evaluate_js."""
    detail_json = json.dumps(detail)
    js = (
        f'window.dispatchEvent(new CustomEvent("{event_name}", '
        f'{{detail: {detail_json}}}));'
    )
    try:
        window.evaluate_js(js)
    except Exception as exc:
        log.debug("Failed to emit event %s: %s", event_name, exc)


class DejaViewAPI:
    """API class exposed to pywebview. All public methods are callable from JS."""

    def __init__(
        self,
        db: Database,
        thumb_dir: Path,
        trash_root: Path,
        app_dir: Path,
        drive_sync=None,
    ):
        self._db = db
        self._thumb_dir = thumb_dir
        self._trash_root = trash_root
        self._app_dir = app_dir
        self._drive_sync = drive_sync
        self._scanner = None
        self._executor = None
        self._window: Optional[webview.Window] = None

        # Scan progress state (updated by signal handlers, read by polling)
        self._scan_phase = "idle"
        self._scan_current = 0
        self._scan_total = 0
        self._scan_discovered = 0
        self._scan_duplicates = 0
        self._scan_message = ""

    def set_window(self, window: webview.Window) -> None:
        """Called after window creation to enable event forwarding."""
        self._window = window

    # ── Helper: emit events to frontend ────────────────────────────

    def _emit(self, event_name: str, detail: dict) -> None:
        if self._window:
            _emit_event(self._window, event_name, detail)

    # ── Scan & Session Management ──────────────────────────────────

    def get_scan_progress(self) -> dict:
        """Return current scan progress state (called by frontend polling)."""
        return {
            "phase": self._scan_phase,
            "current": self._scan_current,
            "total": self._scan_total,
            "discovered": self._scan_discovered,
            "duplicates": self._scan_duplicates,
            "message": self._scan_message,
        }

    def start_scan(
        self, folders: list[str], session_name: str, enable_similarity: bool
    ) -> int:
        """Start a new multi-pass scan. Returns session_id."""
        from PyQt6.QtCore import QCoreApplication

        # Reset progress state
        self._scan_phase = "started"
        self._scan_current = 0
        self._scan_total = 0
        self._scan_discovered = 0
        self._scan_duplicates = 0
        self._scan_message = ""

        now = datetime.now(timezone.utc).isoformat()
        session_id = self._db.create_session(session_name, now)
        for folder in folders:
            self._db.add_session_folder(session_id, folder)

        from core.scanner import Scanner

        max_workers = self._db.get_max_scan_workers()
        perf_monitor = None
        if os.environ.get("DEJAVIEW_PERF"):
            from core.perf_monitor import PerformanceMonitor
            perf_monitor = PerformanceMonitor(
                output_dir=self._app_dir, enabled=True
            )

        scanner = Scanner(
            db=self._db,
            session_id=session_id,
            thumb_dir=self._thumb_dir,
            max_workers=max_workers,
            perf_monitor=perf_monitor,
            similarity_enabled=enable_similarity,
        )
        self._scanner = scanner

        # Connect Qt signals to event forwarding
        self._connect_scanner_signals(scanner)

        scanner.start()
        return session_id

    def _connect_scanner_signals(self, scanner) -> None:
        """Wire Scanner Qt signals to in-memory progress state + CustomEvent dispatches.

        Uses DirectConnection so handlers run in the Scanner's thread directly,
        bypassing Qt's event-loop-based signal delivery. This is critical because
        pywebview's thread (where connections are made) has no Qt event loop.
        """
        from PyQt6.QtCore import Qt

        DC = Qt.ConnectionType.DirectConnection

        def on_progress(c, t):
            # Emit final discovery count when transitioning to hashing
            if self._scan_phase not in ("hashing", "similarity"):
                self._emit(
                    "scan:discovery_progress",
                    {"discovered": self._scan_discovered},
                )
            self._scan_current = c
            self._scan_total = t
            self._scan_phase = "hashing"
            self._emit("scan:progress", {"current": c, "total": t, "phase": "hashing"})

        def on_file_discovered(fid, path):
            self._scan_discovered += 1
            # Throttle event emission to avoid flooding the frontend
            if self._scan_discovered <= 5 or self._scan_discovered % 10 == 0:
                self._emit(
                    "scan:discovery_progress",
                    {"discovered": self._scan_discovered},
                )

        def on_duplicate_found(h, ids):
            self._scan_duplicates += len(ids)
            self._emit("scan:duplicate_found", {"pixel_hash": h, "count": len(ids)})

        def on_similarity_progress(c, t):
            self._scan_current = c
            self._scan_total = t
            self._scan_phase = "similarity"
            self._emit("scan:similarity_progress", {"current": c, "total": t})

        def on_status(status, message=""):
            self._scan_phase = status
            self._scan_message = message
            self._emit("scan:status", {"status": status, "message": message})

        def on_info_message(message):
            # Informational text only — don't overwrite _scan_phase
            self._scan_message = message
            self._emit("scan:status", {"status": "info", "message": message})

        scanner.progress_updated.connect(on_progress, DC)
        scanner.file_discovered.connect(on_file_discovered, DC)
        scanner.hash_complete.connect(
            lambda fid, h: self._emit("scan:hash_complete", {"file_id": fid, "pixel_hash": h}),
            DC,
        )
        scanner.hash_complete_batch.connect(
            lambda batch: self._emit("scan:hash_batch", {"count": len(batch), "duplicates_found": 0}),
            DC,
        )
        scanner.directory_hashed.connect(
            lambda d: self._emit("scan:directory_hashed", {"directory": d, "file_count": 0}),
            DC,
        )
        scanner.duplicate_found.connect(on_duplicate_found, DC)
        scanner.similarity_progress.connect(on_similarity_progress, DC)
        scanner.similarity_grouping_complete.connect(
            lambda gc: self._emit("scan:similarity_complete", {"group_count": gc}),
            DC,
        )
        scanner.scan_started.connect(lambda: on_status("started", "Scan started"), DC)
        scanner.scan_paused.connect(lambda: on_status("paused", "Scan paused"), DC)
        scanner.scan_resumed.connect(lambda: on_status("resumed", "Scan resumed"), DC)
        scanner.scan_stopped.connect(lambda: on_status("stopped", "Scan stopped"), DC)
        scanner.scan_complete.connect(lambda: on_status("complete", "Scan complete"), DC)
        scanner.scan_error.connect(lambda p, m: on_status("error", f"{p}: {m}"), DC)
        scanner.status_message.connect(on_info_message, DC)

    def pause_scan(self) -> None:
        if self._scanner:
            self._scanner.pause()

    def resume_scan(self, session_id: int) -> None:
        """Resume a paused scan."""
        if self._scanner and self._scanner.isRunning():
            return

        from core.scanner import Scanner

        max_workers = self._db.get_max_scan_workers()
        scanner = Scanner(
            db=self._db,
            session_id=session_id,
            thumb_dir=self._thumb_dir,
            max_workers=max_workers,
        )
        scanner.set_resuming(True)
        self._scanner = scanner
        self._connect_scanner_signals(scanner)
        scanner.start()

    def stop_scan(self) -> None:
        if self._scanner:
            self._scanner.stop()

    def get_sessions(self) -> list[dict]:
        """Return all scan sessions."""
        sessions = []
        latest = self._db.get_latest_session()
        if latest:
            # Return all sessions by querying them
            # For now return just the latest session info
            row = latest
            folders = self._db.get_session_folders(row["id"])
            files = self._db.get_files_for_session(row["id"])
            sessions.append({
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "status": row["status"],
                "folder_count": len(folders),
                "file_count": len(files),
            })
        return sessions

    def get_scan_summary(self, session_id: int) -> dict:
        """Return aggregate stats for a scan session."""
        session = self._db.get_session(session_id)
        if not session:
            return {
                "session_id": session_id,
                "total_files": 0,
                "total_groups": 0,
                "total_duplicates": 0,
                "recoverable_bytes": 0,
                "similarity_group_count": 0,
            }
        files = self._db.get_files_for_session(session_id)
        dupe_groups = self._db.get_duplicate_groups(session_id)
        sim_count = self._db.get_similarity_group_count(session_id)

        total_dupe_files = sum(g["file_count"] for g in dupe_groups)
        # Recoverable = total dupe file size minus one keeper per group
        recoverable = 0
        for group in dupe_groups:
            group_files = self._db.get_files_by_pixel_hash(
                session_id, group["pixel_hash"]
            )
            if len(group_files) > 1:
                sizes = sorted(
                    [f["size"] for f in group_files if f["size"]], reverse=True
                )
                recoverable += sum(sizes[1:])  # everything except the largest

        return {
            "session_id": session_id,
            "total_files": len(files),
            "total_groups": len(dupe_groups),
            "total_duplicates": total_dupe_files,
            "recoverable_bytes": recoverable,
            "similarity_group_count": sim_count,
        }

    # ── Duplicate Groups & File Actions ────────────────────────────

    def get_duplicate_groups(
        self,
        session_id: int,
        offset: int = 0,
        limit: int = 50,
        filters: dict | None = None,
    ) -> list[dict]:
        """Paginated query returning duplicate groups with file metadata."""
        groups_rows = self._db.get_duplicate_groups(session_id)
        result = []
        for i, g in enumerate(groups_rows):
            if i < offset:
                continue
            if len(result) >= limit:
                break
            files = self._db.get_files_by_pixel_hash(session_id, g["pixel_hash"])
            result.append({
                "pixel_hash": g["pixel_hash"],
                "hash_algorithm": g["hash_algorithm"],
                "file_count": g["file_count"],
                "files": _rows_to_list(files),
            })
        return result

    def get_group_detail(self, session_id: int, pixel_hash: str) -> list[dict]:
        """Return full metadata for all files in a specific duplicate group.

        Each file dict includes an ``action`` key (``'keep'``, ``'delete'``,
        ``'ignore'``, or ``None`` if undecided).
        """
        files = self._db.get_files_by_pixel_hash(session_id, pixel_hash)
        result = _rows_to_list(files)
        file_ids = [f["id"] for f in result]
        actions = self._get_group_actions(session_id, file_ids)
        for f in result:
            f["thumbnail_data"] = self._read_thumbnail_base64(f.get("thumbnail_path"))
            f["action"] = actions.get(f["id"])
        return result

    def _read_thumbnail_base64(self, thumb_path: str | None) -> str:
        """Read a thumbnail file and return a data URI, or empty string."""
        if not thumb_path:
            return ""
        try:
            data = Path(thumb_path).read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
        except OSError:
            return ""

    def _get_file_action(
        self, session_id: int, file_id: int
    ) -> str | None:
        """Return the current action for a file, or None if undecided."""
        row = self._db.conn.execute(
            "SELECT action FROM file_actions "
            "WHERE session_id = ? AND file_id = ?",
            (session_id, file_id),
        ).fetchone()
        return row["action"] if row else None

    def _get_group_actions(
        self, session_id: int, file_ids: list[int]
    ) -> dict[int, str]:
        """Return ``{file_id: action}`` for the given file IDs."""
        if not file_ids:
            return {}
        ph = ",".join("?" * len(file_ids))
        rows = self._db.conn.execute(
            f"SELECT file_id, action FROM file_actions "
            f"WHERE session_id = ? AND file_id IN ({ph})",
            [session_id, *file_ids],
        ).fetchall()
        return {r["file_id"]: r["action"] for r in rows}

    def _auto_keep_last_undecided(
        self, session_id: int, pixel_hash: str
    ) -> None:
        """If only one undecided file remains in a group, auto-mark it 'keep'."""
        group_files = self._db.get_files_by_pixel_hash(session_id, pixel_hash)
        file_ids = [f["id"] for f in group_files]
        existing = self._get_group_actions(session_id, file_ids)
        undecided = [fid for fid in file_ids if fid not in existing]
        if len(undecided) == 1:
            now = datetime.now(timezone.utc).isoformat()
            self._db.set_file_action(
                session_id, undecided[0], "keep", "file", now
            )

    def set_file_action(self, file_id: int, action: str, scope: str) -> dict:
        """Mark a file with an action (keep/delete/ignore).

        Supports toggle: clicking the same action again clears it.
        Auto-keep: when 'delete' leaves only one undecided file in the
        duplicate group, that file is automatically marked 'keep'.

        Returns ``{"actions": {file_id: action, ...}}`` for every file in the
        group so the frontend can refresh its state in one round-trip.
        """
        file_row = self._db.get_file(file_id)
        if not file_row:
            return {"actions": {}}

        session_id = file_row["session_id"]
        pixel_hash = file_row["pixel_hash"]
        now = datetime.now(timezone.utc).isoformat()

        # Toggle: same action again → clear it
        current = self._get_file_action(session_id, file_id)
        if current == action:
            self._db.clear_file_action(session_id, file_id)
        else:
            self._db.set_file_action(session_id, file_id, action, scope, now)
            # Auto-keep the last undecided file when deleting
            if action == "delete" and pixel_hash:
                self._auto_keep_last_undecided(session_id, pixel_hash)

        # Return all actions for the group
        group_actions = {}
        if pixel_hash:
            group_files = self._db.get_files_by_pixel_hash(
                session_id, pixel_hash
            )
            file_ids = [f["id"] for f in group_files]
            group_actions = self._get_group_actions(session_id, file_ids)
        return {"actions": group_actions}

    def apply_selection_preset(
        self, session_id: int, preset: str, group_ids: list[str] | None = None
    ) -> dict:
        """Apply a smart selection preset to specified groups."""
        preset_enum = SelectionPreset[preset]
        keep, delete = apply_preset(
            self._db, session_id, preset_enum,
            pixel_hashes=group_ids,
        )
        return {"keep_count": keep, "delete_count": delete}

    def get_plan_summary(self, session_id: int) -> dict:
        """Return all planned actions for review before execution."""
        summary = self._db.get_plan_summary(session_id)
        # Get detailed action list
        actions_rows = self._db.get_delete_actions_with_paths(session_id)
        actions = []
        for r in actions_rows:
            actions.append({
                "file_id": r["file_id"],
                "path": r["path"],
                "size": r["size"],
                "action": "delete",
                "pixel_hash": r["pixel_hash"] or "",
            })
        return {
            "keep_count": summary.get("keep_count", 0),
            "delete_count": summary.get("delete_count", 0),
            "ignore_count": summary.get("ignore_count", 0),
            "total_size_bytes": summary.get("delete_bytes", 0),
            "actions": actions,
        }

    def execute_plan(self, session_id: int) -> None:
        """Execute all planned file actions (soft-delete, sync). Emits progress events."""
        from PyQt6.QtCore import Qt

        from core.executor import PlanExecutor

        DC = Qt.ConnectionType.DirectConnection

        executor = PlanExecutor(
            db=self._db,
            session_id=session_id,
            trash_root=self._trash_root,
            drive_sync=self._drive_sync,
        )
        self._executor = executor

        # Connect executor signals to event forwarding
        # Uses DirectConnection so handlers run in PlanExecutor's thread
        # (no Qt event loop in pywebview's main thread).
        executor.progress_updated.connect(
            lambda c, t: self._emit("exec:progress", {
                "current": c, "total": t, "action": "cleanup", "file_path": "",
            }),
            DC,
        )
        executor.execution_complete.connect(
            lambda s, e: self._emit("exec:complete", {
                "success": s, "errors": e,
                "summary": f"{s} succeeded, {e} failed",
            }),
            DC,
        )
        executor.execution_error.connect(
            lambda path, msg: self._emit("exec:error", {
                "message": msg, "file_path": path,
            }),
            DC,
        )
        executor.log_message.connect(
            lambda msg: self._emit("exec:progress", {
                "current": 0, "total": 0, "action": "log", "file_path": msg,
            }),
            DC,
        )
        executor.stage_changed.connect(
            lambda stage: self._emit("exec:progress", {
                "current": 0, "total": 0, "action": stage, "file_path": "",
            }),
            DC,
        )

        executor.start()

    def clear_all_actions(self, session_id: int) -> None:
        """Clear all planned actions for a session."""
        self._db.clear_all_actions(session_id)

    # ── Similarity Detection ───────────────────────────────────────

    def get_similarity_groups(
        self, session_id: int, threshold: int = 8
    ) -> list[dict]:
        """Return groups of visually similar images."""
        db_groups = self._db.get_similarity_groups(session_id)
        result = []
        for g in db_groups:
            members = self._db.get_similarity_group_members(g["id"])
            member_list = _rows_to_list(members)
            for m in member_list:
                m["thumbnail_data"] = self._read_thumbnail_base64(
                    m.get("thumbnail_path")
                )
            result.append({
                "id": g["id"],
                "session_id": session_id,
                "member_count": len(member_list),
                "members": member_list,
            })
        return result

    def apply_similarity_preset(
        self,
        session_id: int,
        preset: str,
        group_ids: list[int] | None = None,
    ) -> dict:
        """Apply selection preset to similarity groups."""
        preset_enum = SimilarityPreset[preset]
        keep, delete = apply_similarity_preset(
            self._db, session_id, preset_enum, group_ids=group_ids
        )
        return {"keep_count": keep, "delete_count": delete}

    def recommend_keeper(self, files: list[dict]) -> dict:
        """Return the recommended file to keep and the reason."""
        file_id, reason = recommend_keeper(files)
        return {"file_id": file_id, "reason": reason}

    # ── Duplicates Bin (Soft Delete) ───────────────────────────────

    def get_bin_items(self, session_id: int) -> list[dict]:
        """Return all soft-deleted items."""
        rows = self._db.get_active_soft_deletes(session_id)
        return _rows_to_list(rows)

    def restore_from_bin(self, soft_delete_id: int) -> None:
        """Restore a soft-deleted file to its original location."""
        # Look up the soft-delete record
        # We need to find the record by ID from db
        rows = self._db.conn.execute(
            "SELECT * FROM soft_deletes WHERE id = ? AND recovered_at IS NULL",
            (soft_delete_id,),
        ).fetchone()
        if rows:
            recover(rows["trash_path"], rows["original_path"])
            now = datetime.now(timezone.utc).isoformat()
            self._db.record_recovery(soft_delete_id, now)

    def permanent_delete(self, soft_delete_ids: list[int]) -> None:
        """Permanently delete specified bin items from disk."""
        for sid in soft_delete_ids:
            row = self._db.conn.execute(
                "SELECT * FROM soft_deletes WHERE id = ?", (sid,),
            ).fetchone()
            if row and row["trash_path"]:
                try:
                    Path(row["trash_path"]).unlink(missing_ok=True)
                except OSError:
                    pass

    def purge_expired(self) -> int:
        """Permanently delete all bin items past their 30-day retention period."""
        purged = purge_expired(self._trash_root)
        return len(purged)

    # ── Family Sharing ─────────────────────────────────────────────

    def export_hashes(self, session_id: int) -> str:
        """Export hashes and metadata to a JSON file for sharing."""
        config = self._db.get_sync_config()
        username = config["local_username"] if config else "local_user"
        privacy = config["export_privacy"] if config else "hash_only"
        payload = build_export_payload(self._db, session_id, username, privacy)

        export_path = self._app_dir / f"export_{session_id}.json"
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return str(export_path)

    def import_hashes(self, file_path: str) -> dict:
        """Import a peer's hash export file."""
        if not file_path:
            # Use pywebview file dialog
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("JSON Files (*.json)",),
            )
            if not result:
                return {"imported": 0, "treasures": 0}
            file_path = result[0]

        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        username = payload.get("username", "unknown")
        # Find the active session
        session = self._db.get_latest_session()
        session_id = session["id"] if session else 0
        imported, treasures = import_payload(
            self._db, payload, username, session_id
        )
        return {"imported": imported, "treasures": treasures}

    def sync_drive(self) -> dict:
        """Upload export to Google Drive and download peer exports."""
        if not self._drive_sync:
            return {"status": "unavailable", "errors": {}}

        session = self._db.get_latest_session()
        if not session:
            return {"status": "no_session", "errors": {}}

        status, errors = self._drive_sync.sync(session["id"])
        return {"status": status, "errors": errors}

    def get_remote_peers(self) -> list[dict]:
        rows = self._db.get_all_remote_peers()
        return _rows_to_list(rows)

    def get_requests(self, session_id: int) -> list[dict]:
        rows = self._db.get_requests_for_session(session_id)
        return _rows_to_list(rows)

    def respond_to_request(self, request_id: int, response: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.update_request_status(request_id, response, responded_at=now)

    # ── Thumbnails & Configuration ─────────────────────────────────

    def get_thumbnail_url(self, thumb_path: str) -> str:
        """Return a file:// URL for the thumbnail."""
        if not thumb_path:
            return ""
        normalized = thumb_path.replace("\\", "/")
        return f"file:///{normalized}"

    def get_app_config(self) -> dict:
        config = self._db.get_app_config()
        if not config:
            return {
                "language": "en",
                "theme": "dark",
                "max_scan_workers": 4,
                "perf_logging": False,
                "scan_delay_ms": 0,
            }
        return {
            "language": config["language"],
            "theme": config["theme"],
            "max_scan_workers": config["max_scan_workers"],
            "perf_logging": bool(config["perf_logging"]),
            "scan_delay_ms": self._db.get_scan_delay_ms(),
        }

    def set_app_config(self, key: str, value) -> None:
        """Update a single configuration value."""
        allowed_keys = {
            "language", "theme", "max_scan_workers",
            "perf_logging", "scan_delay_ms",
        }
        if key not in allowed_keys:
            return
        if key == "scan_delay_ms":
            self._db.upsert_sync_config(scan_delay_ms=int(value))
        else:
            self._db.upsert_app_config(**{key: value})

    # ── File Dialogs ───────────────────────────────────────────────

    def select_folders(self) -> list[str]:
        """Open a native folder selection dialog."""
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
        )
        if result:
            return list(result)
        return []
