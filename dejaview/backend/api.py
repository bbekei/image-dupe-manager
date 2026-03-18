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

from core.selection import SelectionPreset, apply_preset
from core.similarity import build_similarity_groups
from core.similarity_selection import (
    SimilarityPreset,
    apply_similarity_preset,
    recommend_keeper,
)
from core.sort_chain import SortCriterion

_EVT_SELECTION_PROGRESS = "selection:progress"
_EVT_SELECTION_COMPLETE = "selection:complete"
_EVT_SCAN_DISCOVERY = "scan:discovery_progress"
_EVT_SCAN_STATUS = "scan:status"
_EVT_EXEC_PROGRESS = "exec:progress"
from core.trash import purge_expired, recover, soft_delete
from data.db import Database, MigrationResult
from data.export import build_export_payload, import_payload
from version import APP_VERSION

log = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return {}
    return dict(row)


def _rows_to_list(rows) -> list[dict]:
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]


ALLOWED_EVENTS: frozenset[str] = frozenset({
    "scan:progress",
    _EVT_SCAN_DISCOVERY,
    _EVT_SCAN_STATUS,
    # scan:hash_complete omitted — not consumed by any frontend listener
    # scan:hash_batch omitted — not consumed by any frontend listener
    # scan:directory_hashed omitted — not consumed by any frontend listener
    "scan:duplicate_found",
    "scan:similarity_progress",
    # scan:similarity_complete omitted — not consumed by any frontend listener
    "scan:error",
    _EVT_EXEC_PROGRESS,
    "exec:complete",
    "exec:error",
    _EVT_SELECTION_PROGRESS,
    _EVT_SELECTION_COMPLETE,
})


class DejaViewAPI:
    """API class exposed to pywebview. All public methods are callable from JS."""

    def __init__(
        self,
        db: Database,
        thumb_dir: Path,
        trash_root: Path,
        app_dir: Path,
        drive_sync=None,
        migration_result: MigrationResult | None = None,
    ):
        self._db = db
        self._thumb_dir = thumb_dir
        self._trash_root = trash_root
        self._app_dir = app_dir
        self._drive_sync = drive_sync
        self._migration_result = migration_result
        self._scanner = None
        self._executor = None
        self._window = None
        self._emit_callback = None

        # Scan progress state (updated by signal handlers, read by polling)
        self._scan_phase = "idle"
        self._scan_current = 0
        self._scan_total = 0
        self._scan_discovered = 0
        self._scan_duplicates = 0
        self._scan_message = ""

    def set_emit_callback(self, cb) -> None:
        """Register a callback for event forwarding: cb(event_name, detail)."""
        self._emit_callback = cb

    # ── Helper: emit events to frontend ────────────────────────────

    def _emit(self, event_name: str, detail: dict) -> None:
        if self._emit_callback:
            self._emit_callback(event_name, detail)

    # ── Version & Migration ─────────────────────────────────────────

    def get_app_version(self) -> str:
        """Return the application version string."""
        return APP_VERSION

    def get_migration_status(self) -> dict:
        """Return migration status for the frontend to act on."""
        mr = self._migration_result
        if mr is None:
            return {"needed": False, "app_version": APP_VERSION}
        return {
            "needed": mr.needs_user_confirmation,
            "from_version": mr.from_version,
            "to_version": mr.to_version,
            "breaking_changes": [
                {
                    "version": m.version,
                    "description": m.description,
                    "reason_key": m.breaking_reason,
                }
                for m in mr.breaking_migrations
            ],
            "backup_path": mr.backup_path,
            "app_version": APP_VERSION,
        }

    def confirm_migration(self) -> dict:
        """User confirmed breaking changes — run pending migrations now."""
        try:
            result = self._db.confirm_breaking_migrations()
            self._migration_result = result
            return {
                "ok": True,
                "validation_errors": result.validation_errors,
            }
        except Exception as exc:
            log.error("confirm_migration failed: %s", exc)
            return {"ok": False, "error": str(exc)}

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
        # Reset progress state
        self._scan_phase = "started"
        self._scan_current = 0
        self._scan_total = 0
        self._scan_discovered = 0
        self._scan_duplicates = 0
        self._scan_message = ""

        now = datetime.now(timezone.utc).isoformat()
        session_id = self._db.create_session(session_name, now, similarity_enabled=enable_similarity)
        for folder in folders:
            self._db.add_session_folder(session_id, folder)

        from core.scanner import Scanner

        max_workers = self._db.get_max_scan_workers()
        perf_monitor = None
        if os.environ.get("DEJAVIEW_PERF") or self._db.get_perf_logging():
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
        """Wire Scanner signals to in-memory progress state + event forwarding."""

        def on_progress(c, t):
            # Emit final discovery count when transitioning to hashing
            if self._scan_phase not in ("hashing", "similarity"):
                self._emit(
                    _EVT_SCAN_DISCOVERY,
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
                    _EVT_SCAN_DISCOVERY,
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
            self._emit(_EVT_SCAN_STATUS, {"status": status, "message": message})

        def on_info_message(message):
            # Informational text only — don't overwrite _scan_phase
            self._scan_message = message
            self._emit(_EVT_SCAN_STATUS, {"status": "info", "message": message})

        scanner.progress_updated.connect(on_progress)
        scanner.file_discovered.connect(on_file_discovered)
        # hash_complete, hash_complete_batch, directory_hashed omitted —
        # unconsumed events (Architect default decision, 2026-03-16)
        scanner.duplicate_found.connect(on_duplicate_found)
        scanner.similarity_progress.connect(on_similarity_progress)
        # similarity_grouping_complete omitted — unconsumed event
        scanner.scan_started.connect(lambda: on_status("started", "Scan started"))
        scanner.scan_paused.connect(lambda: on_status("paused", "Scan paused"))
        scanner.scan_resumed.connect(lambda: on_status("resumed", "Scan resumed"))
        scanner.scan_stopped.connect(lambda: on_status("stopped", "Scan stopped"))
        scanner.scan_complete.connect(lambda: on_status("complete", "Scan complete"))
        scanner.scan_error.connect(
            lambda p, m: self._emit("scan:error", {"path": p, "message": m}),
        )
        scanner.status_message.connect(on_info_message)

    def pause_scan(self) -> None:
        if self._scanner:
            self._scanner.pause()

    def resume_scan(self, session_id: int) -> None:
        """Resume a paused scan."""
        if self._scanner and self._scanner.is_alive():
            return

        from core.scanner import Scanner

        session = self._db.get_session(session_id)
        similarity_enabled = bool(session["similarity_enabled"]) if session else False

        max_workers = self._db.get_max_scan_workers()
        scanner = Scanner(
            db=self._db,
            session_id=session_id,
            thumb_dir=self._thumb_dir,
            max_workers=max_workers,
            similarity_enabled=similarity_enabled,
        )
        scanner.set_resuming(True)
        self._scanner = scanner
        self._connect_scanner_signals(scanner)
        scanner.start()

    def stop_scan(self) -> None:
        if self._scanner:
            if self._scanner.is_alive():
                self._scanner.stop()
            else:
                # Scanner thread has already exited (e.g., scan is paused).
                # Set stopped state directly since no thread will emit the signal.
                session_id = self._scanner._session_id
                self._db.update_session_status(session_id, "stopped")
                self._scan_phase = "stopped"
                self._emit("scan:status", {"status": "stopped", "message": "Scan stopped"})

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
    ) -> dict:
        """Paginated query returning duplicate groups with file metadata."""
        groups_rows = self._db.get_duplicate_groups(session_id)
        total_count = len(groups_rows)
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
        return {"groups": result, "total_count": total_count}

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

    def _is_safe_thumb_path(self, thumb_path: str) -> bool:
        """Return True only if *thumb_path* resolves inside ``self._thumb_dir``."""
        try:
            resolved = Path(thumb_path).resolve(strict=False)
            return resolved.is_relative_to(self._thumb_dir.resolve())
        except (OSError, ValueError):
            return False

    def _read_thumbnail_base64(self, thumb_path: str | None) -> str:
        """Read a thumbnail file and return a data URI, or empty string.

        Only reads files that resolve inside the application's thumbnail
        directory to prevent arbitrary file reads.
        """
        if not thumb_path:
            return ""
        if not self._is_safe_thumb_path(thumb_path):
            log.warning("Blocked thumbnail read outside thumb_dir: %s", thumb_path)
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
        if not isinstance(file_id, int) or not isinstance(action, str) or not isinstance(scope, str):
            return {"actions": {}}
        if action not in ("keep", "delete", "ignore"):
            return {"actions": {}}
        if scope not in ("file", "folder"):
            return {"actions": {}}
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

    def keep_and_delete_others(
        self, keep_file_id: int, group_file_ids: list[int]
    ) -> dict:
        """Mark one file 'keep' and all others in the group 'delete'.

        Works for both duplicate groups (shared pixel_hash) and similarity
        groups (different pixel_hashes).  Accepts the full list of file IDs
        in the group from the frontend so no grouping assumptions are needed.

        Returns ``{"actions": {file_id: action, ...}}`` for the whole group.
        """
        if not isinstance(keep_file_id, int):
            return {"actions": {}}
        if not isinstance(group_file_ids, list) or not all(isinstance(i, int) for i in group_file_ids):
            return {"actions": {}}
        now = datetime.now(timezone.utc).isoformat()
        file_row = self._db.get_file(keep_file_id)
        if not file_row:
            return {"actions": {}}

        session_id = file_row["session_id"]

        for fid in group_file_ids:
            if fid == keep_file_id:
                self._db.set_file_action(session_id, fid, "keep", "file", now)
            else:
                self._db.set_file_action(
                    session_id, fid, "delete", "file", now
                )

        return {
            "actions": self._get_group_actions(session_id, group_file_ids)
        }

    def apply_folder_action(
        self, session_id: int, folder_path: str, action: str
    ) -> dict:
        """Apply an action to ALL scanned files in a folder across all groups.

        Unlike ``set_file_action`` (single-file toggle), this is a batch
        operation: it sets the action on every file whose parent directory
        matches *folder_path*, skipping files that already carry the same
        action.  Auto-keep logic is triggered per-group when deleting.

        Returns ``{"affected": <int>}`` — the number of files changed.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Normalise separators so we can match both / and \
        norm = folder_path.replace("\\", "/")
        rows = self._db.conn.execute(
            """
            SELECT f.id, f.pixel_hash FROM files f
            WHERE f.session_id = ?
              AND REPLACE(f.path, '\\', '/') LIKE ? || '/%'
              AND f.pixel_hash IS NOT NULL
              AND f.pixel_hash IN (
                  SELECT pixel_hash FROM files
                  WHERE session_id = ? AND pixel_hash IS NOT NULL
                  GROUP BY pixel_hash HAVING COUNT(*) > 1
              )
            """,
            (session_id, norm, session_id),
        ).fetchall()

        affected = 0
        seen_hashes: set[str] = set()
        for r in rows:
            fid = r["id"]
            ph = r["pixel_hash"]
            current = self._get_file_action(session_id, fid)
            if current == action:
                continue
            self._db.set_file_action(session_id, fid, action, "folder", now)
            affected += 1
            if ph:
                seen_hashes.add(ph)

        # Auto-keep last undecided file per affected group
        if action == "delete":
            for ph in seen_hashes:
                self._auto_keep_last_undecided(session_id, ph)

        return {"affected": affected}

    def apply_selection_preset(
        self, session_id: int, preset: str, group_ids: list[str] | None = None
    ) -> dict:
        """Apply a smart selection preset to specified groups.

        Clears existing duplicate actions before applying (scoped clear).
        """
        preset_enum = SelectionPreset[preset]
        if group_ids is None:
            self._db.clear_duplicate_actions(session_id)
        keep, delete = apply_preset(
            self._db, session_id, preset_enum,
            pixel_hashes=group_ids,
            progress_callback=lambda c, t: self._emit(
                _EVT_SELECTION_PROGRESS, {"current": c, "total": t}
            ),
        )
        self._emit(_EVT_SELECTION_COMPLETE, {
            "keep_count": keep, "delete_count": delete,
            "active_preset": preset,
        })
        return {"keep_count": keep, "delete_count": delete, "active_preset": preset}

    def apply_custom_selection(
        self, session_id: int, criteria: list[dict]
    ) -> dict:
        """Apply a custom sort-chain to duplicate groups.

        Args:
            criteria: List of {"field": str, "ascending": bool} dicts.
        """
        chain = [SortCriterion(c["field"], c["ascending"]) for c in criteria]
        self._db.clear_duplicate_actions(session_id)
        keep, delete = apply_preset(
            self._db, session_id, chain,
            progress_callback=lambda c, t: self._emit(
                _EVT_SELECTION_PROGRESS, {"current": c, "total": t}
            ),
        )
        self._emit(_EVT_SELECTION_COMPLETE, {
            "keep_count": keep, "delete_count": delete,
            "active_preset": "custom",
        })
        return {"keep_count": keep, "delete_count": delete, "active_preset": "custom"}

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
        from core.executor import PlanExecutor

        executor = PlanExecutor(
            db=self._db,
            session_id=session_id,
            trash_root=self._trash_root,
            drive_sync=self._drive_sync,
        )
        self._executor = executor

        executor.progress_updated.connect(
            lambda c, t: self._emit(_EVT_EXEC_PROGRESS, {
                "current": c, "total": t, "action": "cleanup", "file_path": "",
            }),
        )
        executor.execution_complete.connect(
            lambda s, e: self._emit("exec:complete", {
                "success": s, "errors": e,
                "summary": f"{s} succeeded, {e} failed",
            }),
        )
        executor.execution_error.connect(
            lambda path, msg: self._emit("exec:error", {
                "message": msg, "file_path": path,
            }),
        )
        executor.log_message.connect(
            lambda msg: self._emit(_EVT_EXEC_PROGRESS, {
                "action": "log", "file_path": msg,
            }),
        )
        executor.stage_changed.connect(
            lambda stage: self._emit(_EVT_EXEC_PROGRESS, {
                "action": stage, "file_path": "",
            }),
        )

        executor.start()

    def clear_all_actions(self, session_id: int) -> None:
        """Clear all planned actions for a session."""
        self._db.clear_all_actions(session_id)

    # ── Similarity Detection ───────────────────────────────────────

    def get_similarity_groups(
        self, session_id: int, offset: int = 0, limit: int = 50
    ) -> dict:
        """Return paginated similarity group summaries (no members/thumbnails)."""
        total = self._db.get_similarity_group_count(session_id)
        db_groups = self._db.get_similarity_groups_paginated(
            session_id, offset, limit,
        )
        groups = []
        for g in db_groups:
            groups.append({
                "id": g["id"],
                "session_id": g["session_id"],
                "member_count": g["member_count"],
                "status": g["status"],
                "representative_path": g["representative_path"],
            })
        return {"groups": groups, "total_count": total}

    def get_similarity_group_detail(self, group_id: int) -> dict:
        """Return full member data with thumbnails for a single group.

        Each member dict includes an ``action`` key (``'keep'``, ``'delete'``,
        ``'ignore'``, or ``None`` if undecided), mirroring ``get_group_detail``.
        """
        members = self._db.get_similarity_group_members(group_id)
        member_list = _rows_to_list(members)
        if member_list:
            session_id = member_list[0]["session_id"]
            file_ids = [m["id"] for m in member_list]
            actions = self._get_group_actions(session_id, file_ids)
        else:
            actions = {}
        for m in member_list:
            m["thumbnail_data"] = self._read_thumbnail_base64(
                m.get("thumbnail_path")
            )
            m["action"] = actions.get(m["id"])
        return {
            "id": group_id,
            "member_count": len(member_list),
            "members": member_list,
        }

    def apply_similarity_preset(
        self,
        session_id: int,
        preset: str,
        group_ids: list[int] | None = None,
    ) -> dict:
        """Apply selection preset to similarity groups.

        Clears existing similarity actions before applying (scoped clear).
        """
        preset_enum = SimilarityPreset[preset]
        if group_ids is None:
            self._db.clear_similarity_actions(session_id)
        keep, delete = apply_similarity_preset(
            self._db, session_id, preset_enum, group_ids=group_ids,
            progress_callback=lambda c, t: self._emit(
                _EVT_SELECTION_PROGRESS, {"current": c, "total": t}
            ),
        )
        self._emit(_EVT_SELECTION_COMPLETE, {
            "keep_count": keep, "delete_count": delete,
            "active_preset": preset,
        })
        return {"keep_count": keep, "delete_count": delete, "active_preset": preset}

    def apply_custom_similarity_selection(
        self, session_id: int, criteria: list[dict]
    ) -> dict:
        """Apply a custom sort-chain to similarity groups.

        Args:
            criteria: List of {"field": str, "ascending": bool} dicts.
        """
        chain = [SortCriterion(c["field"], c["ascending"]) for c in criteria]
        self._db.clear_similarity_actions(session_id)
        keep, delete = apply_similarity_preset(
            self._db, session_id, chain,
            progress_callback=lambda c, t: self._emit(
                _EVT_SELECTION_PROGRESS, {"current": c, "total": t}
            ),
        )
        self._emit(_EVT_SELECTION_COMPLETE, {
            "keep_count": keep, "delete_count": delete,
            "active_preset": "custom",
        })
        return {"keep_count": keep, "delete_count": delete, "active_preset": "custom"}

    def recommend_keeper(self, files: list[dict]) -> dict:
        """Return the recommended file to keep and the reason."""
        file_id, reason = recommend_keeper(files)
        return {"file_id": file_id, "reason": reason}

    # ── Duplicates Bin (Soft Delete) ───────────────────────────────

    def get_bin_items(self, session_id: int) -> list[dict]:
        """Return all soft-deleted items with thumbnail data."""
        rows = self._db.get_active_soft_deletes(session_id)
        result = _rows_to_list(rows)
        for item in result:
            file_row = self._db.get_file(item["file_id"]) if item.get("file_id") else None
            thumb_path = file_row["thumbnail_path"] if file_row else None
            item["thumbnail_data"] = self._read_thumbnail_base64(thumb_path)
        return result

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
        now = datetime.now(timezone.utc).isoformat()
        for sid in soft_delete_ids:
            row = self._db.conn.execute(
                "SELECT * FROM soft_deletes WHERE id = ?", (sid,),
            ).fetchone()
            if row and row["trash_path"]:
                try:
                    Path(row["trash_path"]).unlink(missing_ok=True)
                except OSError:
                    pass
                self._db.record_recovery(sid, now)

    def purge_expired(self) -> int:
        """Permanently delete all bin items past their 30-day retention period."""
        now = datetime.now(timezone.utc).isoformat()
        expired_rows = self._db.get_expired_soft_deletes(now)
        purged = purge_expired(self._trash_root)
        for row in expired_rows:
            self._db.record_recovery(row["id"], now)
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
        """Import a peer's hash export file.

        Validates that the file exists, has a ``.json`` extension, and is
        within a reasonable size before parsing.
        """
        if not file_path:
            return {"imported": 0, "treasures": 0, "error": "no_file_provided"}

        resolved = Path(file_path).resolve(strict=False)
        if resolved.suffix.lower() != ".json":
            log.warning("Import rejected — not a .json file: %s", file_path)
            return {"imported": 0, "treasures": 0, "error": "invalid_file_type"}

        if not resolved.is_file():
            log.warning("Import rejected — file not found: %s", file_path)
            return {"imported": 0, "treasures": 0, "error": "file_not_found"}

        MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB
        if resolved.stat().st_size > MAX_IMPORT_BYTES:
            log.warning("Import rejected — file too large: %s", file_path)
            return {"imported": 0, "treasures": 0, "error": "file_too_large"}

        with open(resolved, "rb") as f:
            raw = f.read()

        try:
            username = import_payload(self._db, raw)
        except ImportError as exc:
            log.warning("Import rejected: %s", exc)
            return {"imported": 0, "error": str(exc)}
        return {"imported": 1, "username": username}

    def sync_drive(self) -> dict:
        """Upload export to Google Drive and download peer exports."""
        if not self._drive_sync:
            return {"status": "unavailable", "errors": {}}

        session = self._db.get_latest_session()
        if not session:
            return {"status": "no_session", "errors": {}}

        status, errors = self._drive_sync.sync(session["id"])
        return {"status": status, "errors": errors}

    def get_sync_config(self) -> dict:
        """Return the current sync configuration."""
        config = self._db.get_sync_config()
        authenticated = (
            self._drive_sync.is_authenticated() if self._drive_sync else False
        )
        if not config:
            return {
                "local_username": "",
                "gdrive_folder_id": "",
                "export_privacy": "filename",
                "sync_enabled": False,
                "authenticated": authenticated,
            }
        return {
            "local_username": config["local_username"] or "",
            "gdrive_folder_id": config["gdrive_folder_id"] or "",
            "export_privacy": config["export_privacy"] or "filename",
            "sync_enabled": bool(config["sync_enabled"]),
            "authenticated": authenticated,
        }

    def save_sync_config(
        self, username: str, folder_id: str, privacy: str
    ) -> dict:
        """Validate and persist sync configuration.

        Returns ``{"ok": True}`` on success or
        ``{"ok": False, "error": "..."}`` on validation failure.
        """
        from data.export import validate_username
        from data.sync import validate_folder_id

        username = (username or "").strip()
        folder_id = (folder_id or "").strip()

        if not validate_username(username):
            return {
                "ok": False,
                "error": "invalid_username",
            }

        if folder_id and not validate_folder_id(folder_id):
            return {
                "ok": False,
                "error": "invalid_folder_id",
            }

        sync_enabled = 1 if folder_id else 0
        self._db.upsert_sync_config(
            local_username=username,
            gdrive_folder_id=folder_id or None,
            export_privacy=privacy,
            sync_enabled=sync_enabled,
        )
        return {"ok": True}

    def authenticate_drive(self) -> dict:
        """Run OAuth2 authentication flow for Google Drive.

        Returns ``{"ok": True}`` on success or
        ``{"ok": False, "error": "..."}`` on failure.
        """
        if not self._drive_sync:
            return {"ok": False, "error": "Drive sync not available"}
        ok, msg = self._drive_sync.authenticate()
        return {"ok": ok, "error": msg}

    def remove_peer(self, username: str) -> None:
        """Remove a synced peer and all their data."""
        if self._drive_sync:
            self._drive_sync.remove_peer(username)
        else:
            self._db.delete_remote_peer(username)

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
        """Return a file:// URL for the thumbnail.

        Only returns URLs for paths that resolve inside the thumbnail
        directory to prevent referencing arbitrary files.
        """
        if not thumb_path:
            return ""
        if not self._is_safe_thumb_path(thumb_path):
            log.warning("Blocked thumbnail URL outside thumb_dir: %s", thumb_path)
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
        """Update a single configuration value.

        Validates key membership and value types before writing to DB.
        """
        if not isinstance(key, str):
            return
        ALLOWED_TYPES: dict[str, type | tuple[type, ...]] = {
            "language": str,
            "theme": str,
            "max_scan_workers": (int, float),
            "perf_logging": (bool, int),
            "scan_delay_ms": (int, float),
        }
        if key not in ALLOWED_TYPES:
            return
        if not isinstance(value, ALLOWED_TYPES[key]):
            log.warning("set_app_config: invalid type for %s: %s", key, type(value).__name__)
            return
        if key == "scan_delay_ms":
            self._db.upsert_sync_config(scan_delay_ms=int(value))
        else:
            self._db.upsert_app_config(**{key: value})

    # ── File Dialogs ───────────────────────────────────────────────

    def select_folders(self) -> list[str]:
        """Open a native folder selection dialog."""
        raise NotImplementedError("select_folders: to be implemented with tauri-plugin-dialog in Step 5")
