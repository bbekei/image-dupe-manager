"""
core/scanner.py — Two-pass image scanner (plan §Two-pass scan and file-size pre-filter).

Module ownership rules (plan §Architecture):
- QThread worker: disk walker + session state via db.py; calls hasher.py per file.
- Emits Qt signals for progress and badge updates.
- No direct UI access.

Two-pass scan (plan §Two-pass scan and file-size pre-filter):
  Pass 1 — Discovery: walk all folders, insert file rows with pixel_hash = NULL.
  Pass 2 — Hashing: hash only files whose size appears >= 2 times in the session.
             Uses a sliding-window pipeline over a ThreadPoolExecutor for
             multi-core parallelism (Pillow/hashlib release the GIL).
             Candidates are grouped by parent directory and submitted in
             leaf-first order (deepest subdirectories first), but files from
             multiple directories are in flight simultaneously to keep all
             worker threads busy.  When all files in a directory complete,
             the directory_hashed signal fires so the UI can flush pending
             updates and recompute folder-level duplication badges, enabling
             incremental browsing of completed directories mid-scan.

Pause/resume state machine (plan §Pause/resume state machine):
  PASS1         → walks folders, inserts files with pixel_hash=NULL
  PASS2         → hashes size-duplicate candidates only
  pause()       → sets flag; QThread exits after current file completes
  set_resuming  → skips Pass 1, skips already-hashed files in Pass 2
  stop()        → sets flag; marks session 'stopped'

Security (plan §Security):
  - Symlink/junction guard: os.path.islink() + reparse-point check for Windows junctions.
  - Network path probe before Pass 1 (5-second timeout).
  - Permission errors caught per-file; scan continues for remaining files.
"""

import concurrent.futures
import logging
import os
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.hasher import HashError, hash_file
from data.db import Database

log = logging.getLogger(__name__)

# Image extensions to consider during discovery (case-insensitive).
# Limited to formats actually produced by digital cameras (DSLR, iPhone, Android).
# Number of futures per worker to keep in flight for pipeline efficiency.
# Doubling the worker count provides a backpressure buffer so threads
# never idle waiting for the next submission.
_PIPELINE_BUFFER_FACTOR = 2

_IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".heic", ".heif",
})


def _is_symlink_or_junction(path: str) -> bool:
    """Return True if *path* is a symlink or a Windows directory junction.

    os.path.islink() only detects symlinks on Windows, not junctions created
    with ``mklink /J``.  Junctions are reparse points, so we fall back to
    checking the FILE_ATTRIBUTE_REPARSE_POINT flag on st_file_attributes.
    """
    if os.path.islink(path):
        return True
    try:
        st = os.lstat(path)
        if hasattr(st, "st_file_attributes"):
            return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        pass
    return False


def _is_reachable(path: str, timeout_s: float = 5.0) -> bool:
    """
    Probe whether a path is accessible within timeout_s seconds.
    Plan §Security — network drive resilience / timeout for network paths.
    """
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(os.stat, path).result(timeout=timeout_s)
        return True
    except (concurrent.futures.TimeoutError, OSError):
        return False


class Scanner(QThread):
    """
    Two-pass image scanner (plan §Two-pass scan and file-size pre-filter).

    Usage:
        scanner = Scanner(db, session_id, thumb_dir)
        scanner.start()                      # Pass 1 (discovery) -> Pass 2 (hashing)
        scanner.pause()                      # request pause after current file
        scanner.set_resuming(True)
        scanner.start()                      # resume a paused session
        scanner.stop()                       # stop permanently
    """

    # ── Signals ──────────────────────────────────────────────────────────
    file_discovered  = pyqtSignal(int, str)   # file_id, path
    hash_complete    = pyqtSignal(int, str)   # file_id, pixel_hash
    duplicate_found  = pyqtSignal(list)       # [file_id, ...]
    progress_updated = pyqtSignal(int, int)   # current, total
    scan_started     = pyqtSignal()
    scan_paused      = pyqtSignal()
    scan_resumed     = pyqtSignal()
    scan_stopped     = pyqtSignal()
    scan_complete    = pyqtSignal()
    scan_error       = pyqtSignal(str, str)   # path, message
    status_message   = pyqtSignal(str)        # for the status bar
    directory_hashed = pyqtSignal(str)        # directory path, after all files in it are hashed

    def __init__(
        self,
        db: Database,
        session_id: int,
        thumb_dir: str | Path,
        parent=None,
        max_workers: int | None = None,
    ):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id
        self._thumb_dir = Path(thumb_dir)
        self._pause_requested = False
        self._stop_requested = False
        self._is_resuming = False
        self._max_workers = max_workers or min(os.cpu_count() or 1, 8)

    # ── Public control API ───────────────────────────────────────────────

    def pause(self) -> None:
        """Request a pause; takes effect after the current file finishes."""
        self._pause_requested = True

    def stop(self) -> None:
        """Request a stop; takes effect after the current file finishes."""
        self._stop_requested = True

    def set_resuming(self, value: bool) -> None:
        """Tell the scanner to skip Pass 1 (resuming an existing session)."""
        self._is_resuming = value

    # ── QThread entry point ──────────────────────────────────────────────

    def run(self) -> None:
        # Plan §Resource Usage — CPU throttling: yield to foreground processes.
        self.setPriority(QThread.Priority.LowPriority)

        # Read scan delay once at scan start (plan §Resource throttling design).
        scan_delay_ms = self._db.get_scan_delay_ms()

        folders = self._db.get_session_folders(self._session_id)
        if not folders:
            log.warning("Scanner: no folders in session %d", self._session_id)
            self._db.update_session_status(self._session_id, "complete")
            self.scan_complete.emit()
            return

        # ── Pass 1: Discovery ─────────────────────────────────────────────
        if not self._is_resuming:
            self.scan_started.emit()
            self._run_pass1(folders)
        else:
            self.scan_resumed.emit()

        if self._stop_requested:
            self._db.update_session_status(self._session_id, "stopped")
            self.scan_stopped.emit()
            return

        # ── Pass 2: Hashing ───────────────────────────────────────────────
        self._run_pass2(scan_delay_ms)

        if self._stop_requested:
            self._db.update_session_status(self._session_id, "stopped")
            self.scan_stopped.emit()
            return

        if self._pause_requested:
            self._db.update_session_status(self._session_id, "paused")
            self.scan_paused.emit()
            return

        self._db.update_session_status(self._session_id, "complete")
        self.scan_complete.emit()

    # ── Pass 1: Discovery ────────────────────────────────────────────────

    def _run_pass1(self, folders: list[str]) -> None:
        self.status_message.emit(self.tr("Discovering files\u2026"))
        now = datetime.now(timezone.utc).isoformat()
        batch: list[tuple] = []

        for folder in folders:
            # Network reachability probe (plan §Security — network drive resilience).
            if not _is_reachable(folder):
                msg = self.tr("Folder unreachable, skipping: {0}").format(folder)
                log.warning("Scanner: %s", msg)
                self.status_message.emit(msg)
                continue

            try:
                for dir_path, dir_names, file_names in os.walk(
                    folder, topdown=True
                ):
                    if self._stop_requested:
                        break

                    # Symlink/junction guard (plan §Security — symlink guard).
                    dir_names[:] = [
                        d for d in dir_names
                        if not _is_symlink_or_junction(os.path.join(dir_path, d))
                    ]

                    for filename in file_names:
                        if self._stop_requested:
                            break

                        if Path(filename).suffix.lower() not in _IMAGE_EXTENSIONS:
                            continue

                        full_path = os.path.join(dir_path, filename)
                        try:
                            st = os.stat(full_path)
                            mtime = datetime.fromtimestamp(
                                st.st_mtime, tz=timezone.utc
                            ).isoformat()
                            batch.append(
                                (self._session_id, full_path, st.st_size, mtime, now)
                            )
                            if len(batch) >= 100:
                                self._flush_batch(batch)
                                batch = []
                        except PermissionError as exc:
                            log.warning(
                                "Scanner: permission denied: %s: %s", full_path, exc
                            )
                            self.scan_error.emit(full_path, str(exc))
                        except OSError as exc:
                            log.warning(
                                "Scanner: cannot stat %s: %s", full_path, exc
                            )
                            self.scan_error.emit(full_path, str(exc))

            except OSError as exc:
                log.warning("Scanner: cannot walk %s: %s", folder, exc)
                self.scan_error.emit(folder, str(exc))

        if batch and not self._stop_requested:
            self._flush_batch(batch)

    def _flush_batch(self, batch: list[tuple]) -> None:
        """Insert a batch of discovered files and emit file_discovered signals."""
        self._db.insert_files_batch(batch)
        # Emit file_discovered per file so ResultsPanel (Phase 3) can populate
        # the tree incrementally as Pass 1 runs.
        for session_id, path, *_ in batch:
            try:
                row = self._db.conn.execute(
                    "SELECT id FROM files WHERE session_id = ? AND path = ?",
                    (session_id, path),
                ).fetchone()
                if row:
                    self.file_discovered.emit(row["id"], path)
            except Exception as exc:
                log.warning(
                    "Scanner: failed to fetch file id for %s: %s", path, exc
                )

    # ── Pass 2: Hashing ──────────────────────────────────────────────────

    def _run_pass2(self, scan_delay_ms: int) -> None:
        candidates = self._db.get_unhashed_files_grouped_by_size(self._session_id)
        total = len(candidates)
        current = 0

        self.progress_updated.emit(0, total)
        self.status_message.emit(
            self.tr("Hashing {0} candidate(s)\u2026").format(total)
        )

        if total == 0:
            return

        # ── Group candidates by parent directory ──────────────────────────
        dir_groups: dict[str, list] = {}
        for file_row in candidates:
            dir_path = os.path.dirname(file_row["path"])
            dir_groups.setdefault(dir_path, []).append(file_row)

        # Sort directories leaf-first (deepest first) for incremental
        # browsing: complete the deepest subdirectories before their parents.
        sorted_dirs = sorted(
            dir_groups.keys(),
            key=lambda d: (-d.count(os.sep), d),
        )

        # Fall back to serial mode when throttling is requested.
        workers = 1 if scan_delay_ms > 0 else self._max_workers
        db_lock = threading.Lock()

        # ── Sliding-window pipeline ───────────────────────────────────────
        # Submit files from multiple directories simultaneously to keep all
        # worker threads busy.  Track per-directory completion to emit
        # directory_hashed at the right time.

        def _candidate_iter():
            """Yield (dir_path, file_row) tuples in leaf-first order."""
            for d in sorted_dirs:
                for fr in dir_groups[d]:
                    yield d, fr

        candidate_it = _candidate_iter()
        window_size = workers * _PIPELINE_BUFFER_FACTOR

        # active: future → (file_row, dir_path)
        active: dict[concurrent.futures.Future, tuple] = {}
        # dir_pending: directory → number of unfinished futures
        dir_pending: dict[str, int] = {}

        def _submit_next() -> bool:
            """Submit the next candidate. Returns False if exhausted or stopped."""
            if self._stop_requested or self._pause_requested:
                return False
            try:
                d, fr = next(candidate_it)
            except StopIteration:
                return False
            f = executor.submit(hash_file, fr["path"], self._thumb_dir)
            active[f] = (fr, d)
            dir_pending[d] = dir_pending.get(d, 0) + 1
            return True

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            # Seed the window.
            for _ in range(window_size):
                if not _submit_next():
                    break

            # Drain completions one at a time for responsive pause/stop.
            while active:
                if self._stop_requested or self._pause_requested:
                    for f in list(active):
                        f.cancel()
                    break

                # Wait for exactly one future to complete.
                for future in concurrent.futures.as_completed(list(active)):
                    file_row, dir_path = active.pop(future)
                    file_id = file_row["id"]
                    path = file_row["path"]

                    try:
                        pixel_hash, thumb_path = future.result()
                        with db_lock:
                            self._db.update_pixel_hash(
                                file_id, pixel_hash, thumb_path
                            )
                            self.hash_complete.emit(file_id, pixel_hash)

                            dupes = self._db.get_files_by_pixel_hash(
                                self._session_id, pixel_hash
                            )
                            if len(dupes) > 1:
                                self.duplicate_found.emit(
                                    [r["id"] for r in dupes]
                                )

                    except (HashError, Exception) as exc:
                        log.warning("Scanner: cannot hash %s: %s", path, exc)
                        self.scan_error.emit(path, str(exc))

                    current += 1
                    self.progress_updated.emit(current, total)

                    if scan_delay_ms > 0:
                        time.sleep(scan_delay_ms / 1000.0)

                    # Directory complete?
                    dir_pending[dir_path] -= 1
                    if dir_pending[dir_path] == 0:
                        del dir_pending[dir_path]
                        if not self._stop_requested and not self._pause_requested:
                            self.directory_hashed.emit(dir_path)

                    # Refill the window.
                    _submit_next()

                    # Process one future per outer-loop iteration so we
                    # re-check pause/stop after every completion.
                    break
