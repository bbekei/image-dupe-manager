"""
core/scanner.py — Multi-pass image scanner (plan §Two-pass scan and file-size pre-filter).

Module ownership rules (plan §Architecture):
- QThread worker: disk walker + session state via db.py; calls hasher.py per file.
- Emits Qt signals for progress and badge updates.
- No direct UI access.

Multi-pass scan:
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

             Duplicate detection is deferred: instead of querying for
             duplicates after each file, a bulk query runs periodically
             (every _DUPE_CHECK_INTERVAL files) and once after all hashing
             completes.  Progress signals are emitted once per DB batch
             (not per file) and the ETA display is driven by a 1-second
             QTimer decoupled from signal rate.

             Throttling via scan_delay_ms is proportional: 0 ms = full
             workers, 1-5 ms = half workers (min 2), 6-20 ms = quarter
             workers (min 1).
  Pass 3 — Similarity (opt-in, plan §S2):
       3a: Dual hashing — ALL files that lack perceptual_hash.
           Computes pixel_hash + pHash + thumbnail for files the size
           pre-filter skipped; adds only pHash for already-hashed files.
       3b: Post-hash duplicate refresh — re-runs exact-duplicate detection
           on newly pixel-hashed files (may discover additional exact
           duplicates that the size pre-filter missed).
       3c: Similarity grouping — Union-Find transitive closure on pHash.

Pause/resume state machine (plan §Pause/resume state machine):
  PASS1         → walks folders, inserts files with pixel_hash=NULL
  PASS2         → hashes size-duplicate candidates only
  PASS3         → dual-hash + similarity grouping (when similarity_enabled)
  pause()       → sets flag; QThread exits after current file completes
  set_resuming  → skips Pass 1, skips already-hashed files in Pass 2/3
  stop()        → sets flag; marks session 'stopped'

Security (plan §Security):
  - Symlink/junction guard: os.path.islink() + reparse-point check for Windows junctions.
  - Network path probe before Pass 1 (5-second timeout).
  - Permission errors caught per-file; scan continues for remaining files.
"""

import concurrent.futures
import ctypes
import logging
import os
import stat
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.hasher import HashError, compute_phash_only, hash_file
from core.perf_monitor import ENABLED as _PERF_ENABLED
from data.db import Database

log = logging.getLogger(__name__)

# Image extensions to consider during discovery (case-insensitive).
# Limited to formats actually produced by digital cameras (DSLR, iPhone, Android).
# Number of futures per worker to keep in flight for pipeline efficiency.
# Doubling the worker count provides a backpressure buffer so threads
# never idle waiting for the next submission.
_PIPELINE_BUFFER_FACTOR = 4
_DB_BATCH_SIZE = 128

_IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".heic", ".heif",
})

# R3: Estimated peak memory per worker for 24 MP images (MB).
_MEMORY_PER_WORKER_MB = 150
# R3: Reserve this much RAM for OS + app + Qt (MB).
_MEMORY_RESERVE_MB = 2048
# R3: Maximum number of distinct directories with in-flight futures (HDD locality).
_MAX_INFLIGHT_DIR_FACTOR = 2  # workers // this value


def _memory_worker_cap() -> int:
    """Return the max workers that fit in available RAM, or 16 as fallback."""
    try:
        if sys.platform == "win32":
            # MEMORYSTATUSEX structure
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            avail_mb = stat.ullAvailPhys // (1024 * 1024)
        else:
            # POSIX: read from /proc/meminfo or use os.sysconf
            pages = os.sysconf("SC_AVPHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            avail_mb = (pages * page_size) // (1024 * 1024)

        usable_mb = max(0, avail_mb - _MEMORY_RESERVE_MB)
        return max(2, usable_mb // _MEMORY_PER_WORKER_MB)
    except Exception:
        return 16  # Fallback: let CPU cap prevail


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
    hash_complete_batch = pyqtSignal(list)    # [(file_id, pixel_hash), ...]
    duplicate_found  = pyqtSignal(str, list)   # pixel_hash, [file_id, ...]
    progress_updated = pyqtSignal(int, int)   # current, total
    scan_started     = pyqtSignal()
    scan_paused      = pyqtSignal()
    scan_resumed     = pyqtSignal()
    scan_stopped     = pyqtSignal()
    scan_complete    = pyqtSignal()
    scan_error       = pyqtSignal(str, str)   # path, message
    status_message   = pyqtSignal(str)        # for the status bar
    directory_hashed = pyqtSignal(str)        # directory path, after all files in it are hashed
    directories_hashed = pyqtSignal(list)     # [dir_path, ...] batch of completed directories
    similarity_progress = pyqtSignal(int, int)         # current, total (Pass 3a)
    similarity_grouping_complete = pyqtSignal(int)     # group_count (Pass 3c)

    def __init__(
        self,
        db: Database,
        session_id: int,
        thumb_dir: str | Path,
        parent=None,
        max_workers: int | None = None,
        perf_monitor=None,
        similarity_enabled: bool = False,
    ):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id
        self._thumb_dir = Path(thumb_dir)
        self._pause_requested = False
        self._stop_requested = False
        self._is_resuming = False
        self._perf = perf_monitor  # None = no telemetry overhead
        self._similarity_enabled = similarity_enabled
        # R3: cap workers by core count, user setting, and available RAM.
        cpu_cap = min(os.cpu_count() or 4, 16)
        user_cap = max_workers or db.get_max_scan_workers() or 0
        if user_cap > 0:
            self._max_workers = min(cpu_cap, user_cap)
        else:
            mem_cap = _memory_worker_cap()
            self._max_workers = min(cpu_cap, mem_cap)

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
        self.setPriority(QThread.Priority.NormalPriority)

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
            if self._perf:
                self._perf.stage_begin("discovery")
            self._run_pass1(folders)
            if self._perf:
                self._perf.stage_end("discovery")
        else:
            self.scan_resumed.emit()

        if self._stop_requested:
            self._db.update_session_status(self._session_id, "stopped")
            self.scan_stopped.emit()
            if self._perf:
                self._perf.finalize()
            return

        # ── Pass 2: Hashing ───────────────────────────────────────────────
        if self._perf:
            self._perf.stage_begin("hashing")
        self._run_pass2(scan_delay_ms)
        if self._perf:
            self._perf.stage_end("hashing")

        if self._stop_requested:
            self._db.update_session_status(self._session_id, "stopped")
            self.scan_stopped.emit()
            if self._perf:
                self._perf.finalize()
            return

        if self._pause_requested:
            self._db.update_session_status(self._session_id, "paused")
            self.scan_paused.emit()
            if self._perf:
                self._perf.finalize()
            return

        # ── Pass 3: Similarity (opt-in) ─────────────────────────────────
        if self._similarity_enabled:
            if self._perf:
                self._perf.stage_begin("similarity_hashing")
            self._run_pass3(scan_delay_ms)
            if self._perf:
                self._perf.stage_end("similarity_hashing")

            if self._stop_requested:
                self._db.update_session_status(self._session_id, "stopped")
                self.scan_stopped.emit()
                if self._perf:
                    self._perf.finalize()
                return

            if self._pause_requested:
                self._db.update_session_status(self._session_id, "paused")
                self.scan_paused.emit()
                if self._perf:
                    self._perf.finalize()
                return

            # Pass 3b: post-hash duplicate refresh
            self._run_pass3b()

            # Pass 3c: similarity grouping
            if self._perf:
                self._perf.stage_begin("similarity_grouping")
            self._run_pass3c()
            if self._perf:
                self._perf.stage_end("similarity_grouping")

        self._db.update_session_status(self._session_id, "complete")
        self.scan_complete.emit()
        if self._perf:
            self._perf.finalize()

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
                    if self._perf:
                        self._perf.record_signal("file_discovered")
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

        # Proportional throttling: scale workers down instead of forcing 1.
        if scan_delay_ms <= 0:
            workers = self._max_workers
        elif scan_delay_ms <= 5:
            workers = max(2, self._max_workers // 2)
        else:
            workers = max(1, self._max_workers // 4)
        db_lock = self._perf.tracked_lock() if self._perf else threading.Lock()

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

        # R3: locality-aware submission — cap inflight directories to reduce
        # random seek thrashing on HDD.  On SSD the limit is generous enough
        # that it has no practical effect.
        max_inflight_dirs = max(2, workers // _MAX_INFLIGHT_DIR_FACTOR)
        _deferred: list[tuple[str, dict]] = []  # buffer for locality overflow

        def _submit_next() -> bool:
            """Submit the next candidate. Returns False if exhausted or stopped."""
            if self._stop_requested or self._pause_requested:
                return False

            # Try deferred items first (from directories already in-flight).
            while _deferred:
                d, fr = _deferred[0]
                if d in dir_pending:
                    _deferred.pop(0)
                    f = executor.submit(hash_file, fr["path"], self._thumb_dir)
                    active[f] = (fr, d)
                    dir_pending[d] += 1
                    return True
                break  # deferred item's dir not in-flight; try fresh candidate

            # Pull from main iterator.
            try:
                d, fr = next(candidate_it)
            except StopIteration:
                # Drain any remaining deferred items regardless of locality.
                # IMPORTANT: submit directly and return — do NOT fall through
                # to the locality gate, which would re-defer the item and
                # create an infinite submission cycle (RCA3).
                if _deferred:
                    d, fr = _deferred.pop(0)
                    f = executor.submit(hash_file, fr["path"], self._thumb_dir)
                    active[f] = (fr, d)
                    dir_pending[d] = dir_pending.get(d, 0) + 1
                    return True
                return False

            # Locality gate: if this file's directory is new and we're at the
            # inflight-dir cap, try to swap with a file from a known dir.
            # The original is only deferred if a swap is found; otherwise
            # it is submitted directly (locality is best-effort).  RCA3 fix:
            # never append-then-submit, which caused infinite re-deferring.
            if d not in dir_pending and len(dir_pending) >= max_inflight_dirs:
                for _ in range(64):  # bounded retry
                    try:
                        d2, fr2 = next(candidate_it)
                    except StopIteration:
                        break
                    if d2 in dir_pending:
                        _deferred.append((d, fr))  # defer original
                        d, fr = d2, fr2
                        break
                    _deferred.append((d2, fr2))
                # If no swap found, submit the original (d, fr unchanged).
                # Locality is best-effort; don't defer indefinitely.

            f = executor.submit(hash_file, fr["path"], self._thumb_dir)
            active[f] = (fr, d)
            dir_pending[d] = dir_pending.get(d, 0) + 1
            return True

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            # Seed the window.
            for _ in range(window_size):
                if not _submit_next():
                    break

            # Drain completions in batches for throughput; check
            # pause/stop once per drain cycle (~100 ms worst-case).
            pending_updates: list[tuple[int, str, str]] = []  # (file_id, hash, thumb)
            # Parallel list for post-commit signal emission.
            pending_signals: list[tuple[int, str, str]] = []  # (file_id, hash, dir)
            # Incremental duplicate detection: track hash→[file_ids] in memory.
            hash_to_ids: dict[str, list[int]] = {}
            known_dup_hashes: set[str] = set()
            _overshoot_logged = False

            while active:
                if self._stop_requested or self._pause_requested:
                    for f in list(active):
                        f.cancel()
                    break

                # ── Telemetry: queue pressure snapshot ─────────────────
                if self._perf:
                    try:
                        q_depth = executor._work_queue.qsize()
                    except Exception:
                        q_depth = -1
                    self._perf.record_queue_state(
                        q_depth, len(active), len(pending_updates)
                    )

                done, _ = concurrent.futures.wait(
                    list(active),
                    timeout=0.1,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    continue

                for future in done:
                    file_row, dir_path = active.pop(future)
                    file_id = file_row["id"]
                    path = file_row["path"]

                    try:
                        pixel_hash, thumb_path, *_ = future.result()
                        pending_updates.append((file_id, pixel_hash, thumb_path))
                        pending_signals.append((file_id, pixel_hash, dir_path))
                    except (HashError, Exception) as exc:
                        log.warning("Scanner: cannot hash %s: %s", path, exc)
                        self.scan_error.emit(path, str(exc))

                    current += 1

                    if current > total and not _overshoot_logged:
                        _overshoot_logged = True
                        log.warning(
                            "Scanner: current (%d) exceeded total (%d) — "
                            "possible deferred-queue bug",
                            current, total,
                        )

                    # Refill the window immediately.
                    _submit_next()

                # Flush batch to DB when large enough or no more active work.
                if pending_updates and (
                    len(pending_updates) >= _DB_BATCH_SIZE or not active
                ):
                    _db_t0 = time.monotonic()
                    with db_lock:
                        self._db.update_pixel_hashes_batch(pending_updates)
                    if self._perf:
                        self._perf.record_db_batch_ms(
                            (time.monotonic() - _db_t0) * 1000
                        )
                        self._perf.record_files_hashed(len(pending_updates))
                    pending_updates.clear()

                    # Emit batch signal for all hash completions at once,
                    # plus per-file signals, duplicate detection, and directory tracking.
                    batch_hash_updates: list[tuple[int, str]] = []
                    completed_dirs: list[str] = []

                    for file_id, pixel_hash, dir_path in pending_signals:
                        batch_hash_updates.append((file_id, pixel_hash))
                        self.hash_complete.emit(file_id, pixel_hash)
                        if self._perf:
                            self._perf.record_signal("hash_complete")

                        # Incremental duplicate detection: O(1) per file.
                        ids = hash_to_ids.setdefault(pixel_hash, [])
                        ids.append(file_id)
                        if len(ids) == 2:
                            known_dup_hashes.add(pixel_hash)
                            self.duplicate_found.emit(pixel_hash, list(ids))
                            if self._perf:
                                self._perf.record_signal("duplicate_found")

                        dir_pending[dir_path] -= 1
                        if dir_pending[dir_path] == 0:
                            del dir_pending[dir_path]
                            if not self._stop_requested and not self._pause_requested:
                                completed_dirs.append(dir_path)
                                self.directory_hashed.emit(dir_path)
                                if self._perf:
                                    self._perf.record_signal("directory_hashed")

                    # Batch signals: one cross-thread event per batch.
                    if batch_hash_updates:
                        self.hash_complete_batch.emit(batch_hash_updates)
                    if completed_dirs:
                        self.directories_hashed.emit(completed_dirs)

                    pending_signals.clear()

                    # Batched progress: one signal per batch, not per file.
                    self.progress_updated.emit(current, total)
                    if self._perf:
                        self._perf.record_signal("progress_updated")

                    if scan_delay_ms > 0:
                        time.sleep(scan_delay_ms / 1000.0)

        # No final duplicate detection needed — duplicates are detected
        # incrementally as each hash completes (O(1) per file).

    # ── Pass 3a: Dual hashing (similarity) ────────────────────────────

    def _run_pass3(self, scan_delay_ms: int) -> None:
        """Hash ALL files that lack a perceptual_hash (plan §S2.2).

        For files already pixel-hashed in Pass 2: compute only pHash.
        For files skipped by the size pre-filter: compute pixel_hash +
        thumbnail + pHash (dual-hash).
        """
        candidates = self._db.get_files_needing_hashes(self._session_id)
        total = len(candidates)
        current = 0

        self.similarity_progress.emit(0, total)
        self.status_message.emit(
            self.tr("Similarity hashing {0} file(s)\u2026").format(total)
        )

        if total == 0:
            return

        # Proportional throttling (same as Pass 2).
        if scan_delay_ms <= 0:
            workers = self._max_workers
        elif scan_delay_ms <= 5:
            workers = max(2, self._max_workers // 2)
        else:
            workers = max(1, self._max_workers // 4)

        db_lock = self._perf.tracked_lock() if self._perf else threading.Lock()

        # Pending DB updates, split by type.
        pending_phash_only: list[tuple[int, str, int, int]] = []  # (fid, phash, w, h)
        pending_dual: list[tuple[int, str, str, str, int, int]] = []  # (fid, pixhash, thumb, phash, w, h)

        window_size = workers * _PIPELINE_BUFFER_FACTOR
        candidate_it = iter(candidates)
        active: dict[concurrent.futures.Future, dict] = {}

        def _submit_next() -> bool:
            if self._stop_requested or self._pause_requested:
                return False
            try:
                file_row = next(candidate_it)
            except StopIteration:
                return False
            row_dict = dict(file_row)
            has_pixel_hash = row_dict.get("pixel_hash") is not None
            if has_pixel_hash:
                # Already pixel-hashed in Pass 2 — compute only pHash.
                f = executor.submit(compute_phash_only, row_dict["path"])
            else:
                # Size-filter skipped — need full pixel_hash + thumbnail + pHash.
                f = executor.submit(
                    hash_file, row_dict["path"], self._thumb_dir,
                    compute_phash=True,
                )
            row_dict["_phash_only"] = has_pixel_hash
            active[f] = row_dict
            return True

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            for _ in range(window_size):
                if not _submit_next():
                    break

            while active:
                if self._stop_requested or self._pause_requested:
                    for f in list(active):
                        f.cancel()
                    break

                done, _ = concurrent.futures.wait(
                    list(active),
                    timeout=0.1,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    continue

                for future in done:
                    file_row = active.pop(future)
                    file_id = file_row["id"]
                    path = file_row["path"]
                    phash_only = file_row.get("_phash_only", False)

                    try:
                        if phash_only:
                            phash, w, h = future.result()
                            pending_phash_only.append((file_id, phash, w, h))
                        else:
                            pixel_hash, thumb_path, phash, w, h = future.result()
                            pending_dual.append(
                                (file_id, pixel_hash, thumb_path, phash, w, h)
                            )
                    except (HashError, Exception) as exc:
                        log.warning("Scanner Pass 3: cannot hash %s: %s", path, exc)
                        self.scan_error.emit(path, str(exc))

                    current += 1
                    _submit_next()

                # Flush batches.
                batch_ready = (
                    len(pending_phash_only) + len(pending_dual) >= _DB_BATCH_SIZE
                    or not active
                )
                if batch_ready and (pending_phash_only or pending_dual):
                    with db_lock:
                        if pending_phash_only:
                            self._db.update_perceptual_hashes_batch(pending_phash_only)
                            pending_phash_only.clear()
                        if pending_dual:
                            self._db.update_dual_hashes_batch(pending_dual)
                            pending_dual.clear()

                    self.similarity_progress.emit(current, total)

                    if scan_delay_ms > 0:
                        time.sleep(scan_delay_ms / 1000.0)

    # ── Pass 3b: Post-hash duplicate refresh ──────────────────────────

    def _run_pass3b(self) -> None:
        """Find new exact-duplicate groups from files pixel-hashed in Pass 3.

        Files that were skipped by the size pre-filter in Pass 2 now have
        pixel_hashes.  Check if any of them form new exact-duplicate groups
        and emit duplicate_found signals (plan §S2.3).
        """
        self.status_message.emit(self.tr("Checking for new exact duplicates\u2026"))

        # Query: find pixel_hashes with >=2 files that were NOT detected
        # as duplicates before (i.e. they were size-filtered, so they got
        # pixel_hash only in Pass 3).
        rows = self._db.conn.execute(
            """
            SELECT pixel_hash, GROUP_CONCAT(id) AS file_ids
            FROM files
            WHERE session_id = ? AND pixel_hash IS NOT NULL
                  AND status = 'active'
            GROUP BY pixel_hash
            HAVING COUNT(*) >= 2
            """,
            (self._session_id,),
        ).fetchall()

        for row in rows:
            pixel_hash = row["pixel_hash"]
            file_ids = [int(x) for x in row["file_ids"].split(",")]
            self.duplicate_found.emit(pixel_hash, file_ids)

    # ── Pass 3c: Similarity grouping ──────────────────────────────────

    def _run_pass3c(self) -> None:
        """Build similarity groups from perceptual hashes (plan §S2.5).

        Calls build_similarity_groups() on all files with pHash, persists
        groups to DB, and emits similarity_grouping_complete.
        """
        from core.similarity import build_similarity_groups

        self.status_message.emit(self.tr("Grouping similar images\u2026"))

        # Fetch all files with pHash for this session.
        file_rows = self._db.get_files_with_phash(self._session_id)
        files = [dict(r) for r in file_rows]

        # Clear previous groups (idempotent on resume).
        self._db.clear_similarity_groups(self._session_id)

        groups = build_similarity_groups(files)

        now = datetime.now(timezone.utc).isoformat()
        for group_files in groups:
            if not group_files:
                continue
            # Representative = first file (largest in group could be chosen
            # later by the recommendation engine).
            representative_id = group_files[0]["id"]
            gid = self._db.create_similarity_group(
                self._session_id, now, representative_id,
                member_count=len(group_files),
            )
            member_rows: list[tuple[int, int, int]] = []
            rep_phash = group_files[0].get("perceptual_hash", "")
            for f in group_files:
                f_phash = f.get("perceptual_hash", "")
                if rep_phash and f_phash:
                    from core.similarity import hamming_distance
                    dist = hamming_distance(rep_phash, f_phash)
                else:
                    dist = 0
                member_rows.append((gid, f["id"], dist))
            self._db.add_similarity_group_members_batch(member_rows)

        group_count = len(groups)
        self.similarity_grouping_complete.emit(group_count)
        self.status_message.emit(
            self.tr("Found {0} similarity group(s)").format(group_count)
        )
