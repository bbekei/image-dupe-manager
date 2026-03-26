"""Scan and session management commands."""

import logging
import os
from datetime import datetime, timezone

_EVT_SCAN_DISCOVERY = "scan:discovery_progress"
_EVT_SCAN_STATUS = "scan:status"

log = logging.getLogger(__name__)


class ScanCommandsMixin:
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
        log.info("start_scan called: folders=%r, similarity=%s", folders, enable_similarity)
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

        # Verify folders were persisted before spawning scanner thread
        saved = self._db.get_session_folders(session_id)
        log.info("start_scan: session=%d, saved folders=%r", session_id, saved)

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
        self._connect_scanner_signals(scanner)
        scanner.start()
        return session_id

    def _connect_scanner_signals(self, scanner) -> None:
        """Wire Scanner signals to in-memory progress state + event forwarding."""

        def on_progress(c, t):
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
            self._scan_message = message
            self._emit(_EVT_SCAN_STATUS, {"status": "info", "message": message})

        scanner.progress_updated.connect(on_progress)
        scanner.file_discovered.connect(on_file_discovered)
        scanner.duplicate_found.connect(on_duplicate_found)
        scanner.similarity_progress.connect(on_similarity_progress)
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
                session_id = self._scanner._session_id
                self._db.update_session_status(session_id, "stopped")
                self._scan_phase = "stopped"
                self._emit("scan:status", {"status": "stopped", "message": "Scan stopped"})

    def get_sessions(self) -> list[dict]:
        """Return all scan sessions."""
        sessions = []
        latest = self._db.get_latest_session()
        if latest:
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
        recoverable = 0
        for group in dupe_groups:
            group_files = self._db.get_files_by_pixel_hash(
                session_id, group["pixel_hash"]
            )
            if len(group_files) > 1:
                sizes = sorted(
                    [f["size"] for f in group_files if f["size"]], reverse=True
                )
                recoverable += sum(sizes[1:])

        return {
            "session_id": session_id,
            "total_files": len(files),
            "total_groups": len(dupe_groups),
            "total_duplicates": total_dupe_files,
            "recoverable_bytes": recoverable,
            "similarity_group_count": sim_count,
        }
