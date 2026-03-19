"""
core/executor.py — Plan execution engine for DejaView (UX Redesign Phase 3).

QThread that carries out the committed plan:
  Stage A — Local Cleanup: soft-delete files marked for deletion.
  Stage B — Cloud Sync: upload updated JSON export to Google Drive.

Follows the Scanner pattern: emits Qt signals for progress, log messages,
and completion.  Per-file errors are non-fatal — execution continues for
remaining files.

Module ownership:
  - Filesystem operations are delegated to core/trash.py (the ONLY module
    that does destructive file I/O).
  - DB writes go through data/db.py.
  - No direct UI access.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.trash import soft_delete
from data.db import Database

log = logging.getLogger(__name__)


class _Signal:
    """Lightweight replacement for pyqtSignal. Thread-safe via simple list."""
    def __init__(self):
        self._callbacks = []

    def connect(self, callback, *args, **kwargs):
        self._callbacks.append(callback)

    def emit(self, *args):
        for cb in self._callbacks:
            try:
                cb(*args)
            except Exception as exc:
                log.debug("Signal callback error: %s", exc)


class PlanExecutor(threading.Thread):
    """Execute the committed plan in a background thread.

    Signals:
        execution_started:  emitted once at the beginning
        progress_updated:   (current, total) — one per file
        log_message:        human-readable log line
        stage_changed:      "cleanup" or "sync"
        sync_substage:      substage key for Cloud Sync UI updates
        sync_peer_errors:   {peer_username: error_message} for corrupt peers
        execution_complete: (success_count, error_count)
        execution_error:    (path, message) — per-file errors
    """

    def __init__(
        self,
        db: Database,
        session_id: int,
        trash_root: str | Path,
        drive_sync=None,
        parent=None,
    ):
        super().__init__(daemon=True)
        # ── Signals (per-instance so callbacks don't bleed between instances) ─
        self.execution_started = _Signal()
        self.progress_updated = _Signal()
        self.log_message = _Signal()
        self.stage_changed = _Signal()
        self.sync_substage = _Signal()
        self.sync_peer_errors = _Signal()
        self.execution_complete = _Signal()
        self.execution_error = _Signal()
        self._db = db
        self._session_id = session_id
        self._trash_root = Path(trash_root)
        self._drive_sync = drive_sync
        self._stop_requested = False

    def stop(self) -> None:
        """Request a graceful stop after the current file finishes."""
        self._stop_requested = True

    def run(self) -> None:
        """Execute the plan: Stage A (cleanup) then Stage B (sync)."""
        self.execution_started.emit()
        success = 0
        errors = 0

        # ── Stage A: Local Cleanup ────────────────────────────────
        self.stage_changed.emit("cleanup")
        rows = self._db.get_delete_actions_with_paths(self._session_id)
        total = len(rows)

        if total == 0:
            self.log_message.emit("No files to delete.")
            self.execution_complete.emit(0, 0)
            return

        self.progress_updated.emit(0, total)
        self.log_message.emit(f"Deleting {total} files...")

        for i, row in enumerate(rows):
            if self._stop_requested:
                self.log_message.emit("Execution stopped by user.")
                break

            file_id = row["file_id"]
            path = row["path"]
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            expires_iso = (now + timedelta(days=30)).isoformat()

            try:
                trash_path = soft_delete(path, self._trash_root, self._session_id)
                self._db.record_soft_delete(
                    session_id=self._session_id,
                    file_id=file_id,
                    original_path=path,
                    trash_path=trash_path,
                    deleted_at=now_iso,
                    expires_at=expires_iso,
                )
                self._db.mark_file_action_executed(
                    self._session_id, file_id, now_iso
                )
                self._db.update_file_status(file_id, "deleted")
                success += 1
                self.log_message.emit(f"Deleted: {path}")
            except Exception as exc:
                errors += 1
                msg = str(exc)
                self.execution_error.emit(path, msg)
                self.log_message.emit(f"Error: {path} — {msg}")
                log.warning("Executor: cannot delete %s: %s", path, exc)

            self.progress_updated.emit(i + 1, total)

        # ── Stage B: Cloud Sync ───────────────────────────────────
        if not self._stop_requested and self._drive_sync is not None:
            self.stage_changed.emit("sync")
            self.log_message.emit("Syncing with Google Drive...")

            def _status_cb(substage: str) -> None:
                """Forward sync substage to UI via signal."""
                self.sync_substage.emit(substage)
                # Map substage keys to log messages
                if substage == "compressing":
                    self.log_message.emit("Compressing database...")
                elif substage.startswith("compressed:"):
                    parts = substage.split(":")
                    if len(parts) == 3:
                        from data.compression import format_compression_ratio
                        msg = format_compression_ratio(
                            int(parts[1]), int(parts[2])
                        )
                        if msg:
                            self.log_message.emit(msg)
                elif substage == "uploading":
                    self.log_message.emit("Uploading compressed data...")
                elif substage == "upload_skipped":
                    self.log_message.emit("Upload skipped — data unchanged.")
                elif substage.startswith("downloading:"):
                    peer = substage.split(":", 1)[1]
                    self.log_message.emit(f"Downloading peer data: {peer}...")
                elif substage.startswith("decompressing:"):
                    peer = substage.split(":", 1)[1]
                    self.log_message.emit(f"Decompressing peer data: {peer}...")

            try:
                config = self._db.get_sync_config()
                if config and config["sync_enabled"]:
                    status, peer_errors = self._drive_sync.sync(
                        session_id=self._session_id,
                        status_callback=_status_cb,
                    )
                    self.log_message.emit(f"Sync result: {status}")
                    if peer_errors:
                        self.sync_peer_errors.emit(peer_errors)
                        for peer, err in peer_errors.items():
                            self.log_message.emit(
                                f"Sync error for {peer}: {err}"
                            )
                else:
                    self.log_message.emit("Sync not enabled — skipped.")
            except Exception as exc:
                self.log_message.emit(f"Sync error: {exc}")
                log.warning("Executor: sync failed: %s", exc)

        self.execution_complete.emit(success, errors)
