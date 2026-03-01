"""
core/perf_monitor.py — Lightweight telemetry collector for scan diagnostics.

Activated by environment variable DEJAVIEW_PERF=1, --perf CLI flag,
or the Settings > Diagnostics checkbox.
Zero overhead when disabled — all instrumentation points check _enabled
before doing any work.

Output: CSV file at %APPDATA%/DejaView/perf_<timestamp>.csv
Rows are written continuously every 1 second by a background daemon thread,
so data is available even if the scanner thread is blocked or the app
becomes unresponsive mid-scan.  A summary row is appended on finalize().
"""

import csv
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

# Module-level fast check so callers can skip instrumentation entirely.
ENABLED = bool(os.environ.get("DEJAVIEW_PERF"))

# Background flush interval in seconds.
_FLUSH_INTERVAL = 1.0

_CSV_COLUMNS = [
    "timestamp",
    "wall_clock",
    "stage",
    "elapsed_s",
    "lock_wait_ms",
    "lock_hold_ms",
    "lock_acquires",
    "executor_queue_depth",
    "active_futures",
    "pending_db_updates",
    "signals_emitted",
    "signals_per_sec",
    "signal_file_discovered",
    "signal_hash_complete",
    "signal_progress_updated",
    "signal_duplicate_found",
    "signal_directory_hashed",
    "pending_file_ids",
    "pending_hash_ids",
    "db_batch_ms",
    "db_batch_count",
    "files_hashed_total",
    "workers",
]


class _TrackedLock:
    """Drop-in replacement for threading.Lock() that records contention metrics."""

    def __init__(self, monitor: "PerformanceMonitor"):
        self._lock = threading.Lock()
        self._monitor = monitor
        self._acquire_time: float = 0.0

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        t0 = time.monotonic()
        result = self._lock.acquire(blocking, timeout)
        if result:
            wait = time.monotonic() - t0
            self._monitor._lock_wait_total += wait
            self._monitor._lock_acquires += 1
            self._acquire_time = time.monotonic()
        return result

    def release(self) -> None:
        hold = time.monotonic() - self._acquire_time
        self._monitor._lock_hold_total += hold
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class PerformanceMonitor:
    """Collects scan performance metrics and writes them to a CSV file.

    A background daemon thread flushes one CSV row every second, ensuring
    data is written continuously even if the scanner thread is blocked or
    the app becomes unresponsive.  The daemon thread exits automatically
    when finalize() is called or when the process exits.

    Usage:
        perf = PerformanceMonitor(output_dir, enabled=True)
        perf.stage_begin("discovery")
        ...
        perf.stage_end("discovery")
        perf.finalize()
    """

    def __init__(self, output_dir: Path, enabled: bool = False, workers: int = 0):
        self._enabled = enabled
        self._workers = workers
        self._output_dir = Path(output_dir)
        self._csv_path: Path | None = None
        self._csv_file = None
        self._csv_writer = None
        self._csv_lock = threading.Lock()  # protects CSV writes

        # Stage timing
        self._stages: dict[str, dict] = {}
        self._current_stage: str = ""

        # Lock contention (written by _TrackedLock from worker threads)
        self._lock_wait_total: float = 0.0
        self._lock_hold_total: float = 0.0
        self._lock_acquires: int = 0

        # Snapshot values for per-interval deltas
        self._prev_lock_wait: float = 0.0
        self._prev_lock_hold: float = 0.0
        self._prev_lock_acquires: int = 0

        # Queue pressure (latest snapshot)
        self._executor_queue_depth: int = 0
        self._active_futures: int = 0
        self._pending_db_updates: int = 0

        # Signal counters
        self._signal_counts: dict[str, int] = {}
        self._prev_signal_total: int = 0

        # UI backlog (latest snapshot)
        self._pending_file_ids: int = 0
        self._pending_hash_ids: int = 0

        # DB batch timing
        self._db_batch_ms_accum: float = 0.0
        self._db_batch_count: int = 0

        # Overall counters
        self._files_hashed_total: int = 0
        self._scan_start: float = time.monotonic()
        self._last_flush: float = self._scan_start

        # Background flush timer
        self._timer_stop = threading.Event()
        self._timer_thread: threading.Thread | None = None

        if enabled:
            self._open_csv()
            self._start_timer()

    # ── Background timer ─────────────────────────────────────────────────

    def _start_timer(self) -> None:
        """Start a daemon thread that calls flush_row() every second."""
        self._timer_stop.clear()
        self._timer_thread = threading.Thread(
            target=self._timer_loop, name="perf-flush", daemon=True
        )
        self._timer_thread.start()

    def _stop_timer(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._timer_stop.set()
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=3.0)
        self._timer_thread = None

    def _timer_loop(self) -> None:
        """Background loop: flush one CSV row every _FLUSH_INTERVAL seconds."""
        while not self._timer_stop.wait(timeout=_FLUSH_INTERVAL):
            try:
                self.flush_row()
            except Exception:
                pass  # never crash the timer thread

    # ── CSV lifecycle ────────────────────────────────────────────────────

    def _open_csv(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._csv_path = self._output_dir / f"perf_{ts}.csv"
        self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=_CSV_COLUMNS)
        self._csv_writer.writeheader()
        self._csv_file.flush()
        log.info("Performance telemetry → %s", self._csv_path)

    # ── Stage timing ─────────────────────────────────────────────────────

    def stage_begin(self, name: str) -> None:
        if not self._enabled:
            return
        self._current_stage = name
        self._stages[name] = {"start": time.monotonic(), "end": None, "elapsed": 0.0}

    def stage_end(self, name: str) -> None:
        if not self._enabled or name not in self._stages:
            return
        s = self._stages[name]
        s["end"] = time.monotonic()
        s["elapsed"] = s["end"] - s["start"]
        if self._current_stage == name:
            self._current_stage = ""

    # ── Lock tracking ────────────────────────────────────────────────────

    def tracked_lock(self) -> _TrackedLock:
        """Return a Lock-compatible object that records contention metrics."""
        return _TrackedLock(self)

    # ── Queue pressure ───────────────────────────────────────────────────

    def record_queue_state(
        self,
        executor_queue_depth: int,
        active_futures: int,
        pending_db_updates: int,
    ) -> None:
        if not self._enabled:
            return
        self._executor_queue_depth = executor_queue_depth
        self._active_futures = active_futures
        self._pending_db_updates = pending_db_updates

    # ── Signal tracking ──────────────────────────────────────────────────

    def record_signal(self, signal_name: str) -> None:
        if not self._enabled:
            return
        self._signal_counts[signal_name] = self._signal_counts.get(signal_name, 0) + 1

    # ── UI backlog ───────────────────────────────────────────────────────

    def record_ui_backlog(self, pending_file_ids: int, pending_hash_ids: int) -> None:
        if not self._enabled:
            return
        self._pending_file_ids = pending_file_ids
        self._pending_hash_ids = pending_hash_ids

    # ── DB batch timing ──────────────────────────────────────────────────

    def record_db_batch_ms(self, ms: float) -> None:
        if not self._enabled:
            return
        self._db_batch_ms_accum += ms
        self._db_batch_count += 1

    # ── Files hashed counter ─────────────────────────────────────────────

    def record_files_hashed(self, count: int) -> None:
        if not self._enabled:
            return
        self._files_hashed_total += count

    # ── Periodic flush ───────────────────────────────────────────────────

    def flush_row(self) -> None:
        """Write one CSV row with current metrics.

        Called automatically by the background timer every second.
        Thread-safe — can also be called manually from the scanner thread.
        """
        if not self._enabled:
            return

        with self._csv_lock:
            if not self._csv_writer:
                return

            now = time.monotonic()
            interval = now - self._last_flush
            if interval <= 0:
                interval = 0.001  # avoid division by zero

            # Compute interval deltas for lock metrics
            lock_wait_interval = (self._lock_wait_total - self._prev_lock_wait) * 1000
            lock_hold_interval = (self._lock_hold_total - self._prev_lock_hold) * 1000
            lock_acquires_interval = self._lock_acquires - self._prev_lock_acquires
            self._prev_lock_wait = self._lock_wait_total
            self._prev_lock_hold = self._lock_hold_total
            self._prev_lock_acquires = self._lock_acquires

            # Signal rate
            signal_total = sum(self._signal_counts.values())
            signals_this_interval = signal_total - self._prev_signal_total
            signals_per_sec = signals_this_interval / interval
            self._prev_signal_total = signal_total

            # Current stage elapsed
            stage_elapsed = 0.0
            if self._current_stage and self._current_stage in self._stages:
                s = self._stages[self._current_stage]
                stage_elapsed = now - s["start"]

            row = {
                "timestamp": time.strftime("%H:%M:%S"),
                "wall_clock": f"{now - self._scan_start:.1f}",
                "stage": self._current_stage,
                "elapsed_s": f"{stage_elapsed:.1f}",
                "lock_wait_ms": f"{lock_wait_interval:.2f}",
                "lock_hold_ms": f"{lock_hold_interval:.2f}",
                "lock_acquires": lock_acquires_interval,
                "executor_queue_depth": self._executor_queue_depth,
                "active_futures": self._active_futures,
                "pending_db_updates": self._pending_db_updates,
                "signals_emitted": signals_this_interval,
                "signals_per_sec": f"{signals_per_sec:.0f}",
                "signal_file_discovered": self._signal_counts.get("file_discovered", 0),
                "signal_hash_complete": self._signal_counts.get("hash_complete", 0),
                "signal_progress_updated": self._signal_counts.get("progress_updated", 0),
                "signal_duplicate_found": self._signal_counts.get("duplicate_found", 0),
                "signal_directory_hashed": self._signal_counts.get("directory_hashed", 0),
                "pending_file_ids": self._pending_file_ids,
                "pending_hash_ids": self._pending_hash_ids,
                "db_batch_ms": f"{self._db_batch_ms_accum:.1f}",
                "db_batch_count": self._db_batch_count,
                "files_hashed_total": self._files_hashed_total,
                "workers": self._workers,
            }

            self._csv_writer.writerow(row)
            self._csv_file.flush()

            # Reset per-interval accumulators
            self._db_batch_ms_accum = 0.0
            self._db_batch_count = 0
            self._last_flush = now

    # ── Finalize ─────────────────────────────────────────────────────────

    def finalize(self) -> dict:
        """Stop the background timer, write summary, close CSV, return totals."""
        if not self._enabled:
            return {}

        # Stop the background timer first so it doesn't race with close.
        self._stop_timer()

        # Flush final row
        self.flush_row()

        total_elapsed = time.monotonic() - self._scan_start
        signal_total = sum(self._signal_counts.values())

        summary = {
            "total_elapsed_s": round(total_elapsed, 1),
            "stages": {
                name: round(s["elapsed"], 1)
                for name, s in self._stages.items()
            },
            "lock_wait_total_ms": round(self._lock_wait_total * 1000, 1),
            "lock_hold_total_ms": round(self._lock_hold_total * 1000, 1),
            "lock_acquires_total": self._lock_acquires,
            "signals_total": signal_total,
            "signal_breakdown": dict(self._signal_counts),
            "files_hashed": self._files_hashed_total,
            "csv_path": str(self._csv_path),
        }

        # Write summary as a comment row
        with self._csv_lock:
            if self._csv_file:
                self._csv_file.write(f"\n# SUMMARY: {summary}\n")
                self._csv_file.close()
                self._csv_file = None
                self._csv_writer = None

        log.info("Performance summary: %s", summary)
        return summary
