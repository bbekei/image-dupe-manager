# Telemetry & Debug Mode — Implementation Plan

## Hypothesis Report

### Why the UI Hangs ("Not Responding")

The root cause is **signal storm during Pass 1 `_flush_batch()`** ([scanner.py:324-340](dejaview/core/scanner.py#L324-L340)).

After every 100-file batch insert, the scanner performs **100 sequential SELECT queries** (one per file to fetch its `id`) and emits **100 `file_discovered` signals** — all on the QThread with no yield. Each signal crosses the thread boundary via Qt's queued connection and lands in the main thread's event queue. The main thread must:

1. Receive and dispatch each signal
2. For each `on_file_discovered`: append to `_pending_file_ids` and possibly start the debounce timer
3. Every 200ms: call `_flush_pending()` which does **another DB query per file** (`get_file(file_id)`) plus tree model mutations

For 30k files, Pass 1 emits **30,000 `file_discovered` signals** in rapid succession. Even though ResultsPanel debounces at 200ms, the Qt event loop must still **dequeue and dispatch** every signal object. During the debounce flush, `_flush_pending()` runs **on the main thread** and calls `self._db.get_file(file_id)` for each pending ID — this is a **main-thread DB read competing with scanner-thread DB writes** on the same `sqlite3.Connection` (which uses `check_same_thread=False` but still serializes internally via Python's GIL + SQLite's own mutex).

**The hang occurs when the main thread is blocked** processing a large backlog of queued signals + DB reads while the scanner thread simultaneously holds the connection for batch writes.

### Why the CPU Shows a "Sawtooth" Pattern

The sawtooth is caused by the **two-phase nature within Pass 2 itself**, not Pass 1 vs Pass 2:

| Phase | CPU | Duration | What's happening |
|-------|-----|----------|-----------------|
| **Valley (10-19%)** | I/O bound | Minutes | Workers are loading images from disk (HDD seek-bound). The locality-aware buffering limits inflight directories to `max(2, workers//2)`, which on HDD means most workers idle waiting for disk. |
| **Spike (50-60%)** | CPU bound | Seconds | A batch of images finishes loading simultaneously. Workers decode pixels + compute xxHash in parallel. Then DB batch write fires (32 files), which serializes briefly on `db_lock`. |

The `concurrent.futures.wait(timeout=0.1)` drain loop at [scanner.py:472-476](dejaview/core/scanner.py#L472-L476) collects all completed futures every 100ms. When disk I/O is slow, `done` is empty for many cycles (valley). When several files complete at once (burst from OS read-ahead cache), all workers suddenly become CPU-active (spike).

**Contributing factor:** The `time.sleep(scan_delay_ms / 1000.0)` at [scanner.py:528-529](dejaview/core/scanner.py#L528-L529) runs on the **scanner QThread** (not worker threads), which stalls the drain loop and causes futures to pile up, producing larger bursts when they finally drain.

---

## PerformanceMonitor Design

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                  PerformanceMonitor                  │
│                (standalone module)                   │
├─────────────────────────────────────────────────────┤
│ Metric collectors:                                  │
│   StageTimer     — monotonic wall-clock per stage   │
│   LockTracker    — wrapper around threading.Lock    │
│   QueueTracker   — periodic executor._work_queue    │
│   SignalTracker  — count + rate of signal emissions │
├─────────────────────────────────────────────────────┤
│ Output:                                             │
│   CSV file at %APPDATA%/DejaView/perf_<timestamp>   │
│   One row per sample (1-second interval)            │
│   Summary row at scan completion                    │
└─────────────────────────────────────────────────────┘
```

### Activation

- **Off by default.** Enabled via environment variable `DEJAVIEW_PERF=1` or a `--perf` CLI flag.
- Zero overhead when disabled — all instrumentation points check a module-level `_ENABLED` bool before doing any work.

### CSV Schema

```csv
timestamp,stage,elapsed_s,lock_wait_ms,lock_hold_ms,lock_acquires,executor_queue_depth,active_futures,signals_emitted,signals_per_sec,pending_file_ids,pending_hash_ids,db_batch_ms,files_hashed_total,workers
```

---

## Implementation Steps

### Step 1: Create `core/perf_monitor.py`

New file with ~150 lines. No changes to existing modules yet.

```python
class PerformanceMonitor:
    """Lightweight telemetry collector for scan diagnostics."""

    def __init__(self, output_dir: Path, enabled: bool = False):
        self._enabled = enabled
        # CSV writer, opened lazily on first record
        ...

    # ── Stage timing ──
    def stage_begin(self, name: str) -> None: ...
    def stage_end(self, name: str) -> None: ...

    # ── Lock tracking ──
    def tracked_lock(self) -> "_TrackedLock": ...
    # Returns a threading.Lock-compatible wrapper that records:
    #   - wait_time: monotonic delta between acquire() call and lock obtained
    #   - hold_time: monotonic delta between acquire obtained and release()
    #   - acquire_count: total number of acquisitions

    # ── Queue pressure ──
    def record_queue_state(
        self,
        executor_queue_depth: int,  # len(executor._work_queue)
        active_futures: int,        # len(active dict)
        pending_updates: int,       # len(pending_updates list)
    ) -> None: ...

    # ── Signal tracking ──
    def record_signal(self, signal_name: str) -> None: ...
    # Increments counter; rate computed at flush time

    # ── UI-side tracking ──
    def record_ui_backlog(
        self,
        pending_file_ids: int,
        pending_hash_ids: int,
    ) -> None: ...

    # ── Periodic flush ──
    def flush_row(self) -> None: ...
    # Writes one CSV row with all accumulated metrics, resets counters.
    # Called every 1 second from the scanner drain loop.

    # ── Summary ──
    def finalize(self) -> dict: ...
    # Writes summary row, closes CSV, returns dict of totals.
```

**`_TrackedLock` inner class:**
```python
class _TrackedLock:
    """Drop-in replacement for threading.Lock() that records contention."""

    def __init__(self, monitor: PerformanceMonitor): ...

    def acquire(self, blocking=True, timeout=-1) -> bool:
        t0 = time.monotonic()
        result = self._lock.acquire(blocking, timeout)
        wait = time.monotonic() - t0
        self._monitor._lock_wait_total += wait
        self._monitor._lock_acquires += 1
        self._acquire_time = time.monotonic()
        return result

    def release(self) -> None:
        hold = time.monotonic() - self._acquire_time
        self._monitor._lock_hold_total += hold
        self._lock.release()

    def __enter__(self): self.acquire(); return self
    def __exit__(self, *a): self.release()
```

### Step 2: Instrument `core/scanner.py` (minimal changes)

All instrumentation is **conditional on `perf_monitor._enabled`**. Changes are additive only — no logic refactoring.

**2a. Accept optional PerformanceMonitor in constructor:**
```python
# scanner.py line ~177
def __init__(self, ..., perf_monitor=None):
    ...
    self._perf = perf_monitor  # None = no-op
```

**2b. Stage timing in `run()` (~line 231, 244):**
```python
if self._perf: self._perf.stage_begin("discovery")
self._run_pass1(folders)
if self._perf: self._perf.stage_end("discovery")

if self._perf: self._perf.stage_begin("hashing")
self._run_pass2(scan_delay_ms)
if self._perf: self._perf.stage_end("hashing")
```

**2c. Replace `db_lock = threading.Lock()` with tracked lock (~line 377):**
```python
db_lock = self._perf.tracked_lock() if self._perf else threading.Lock()
```

**2d. Record queue pressure in drain loop (~line 466, inside `while active`):**
```python
if self._perf:
    try:
        q_depth = executor._work_queue.qsize()
    except Exception:
        q_depth = -1
    self._perf.record_queue_state(q_depth, len(active), len(pending_updates))
```

**2e. Record signal emissions (~line 336, 510, 521):**
```python
# In _flush_batch, after file_discovered.emit:
if self._perf: self._perf.record_signal("file_discovered")

# In _run_pass2, after hash_complete.emit:
if self._perf: self._perf.record_signal("hash_complete")

# After progress_updated.emit:
if self._perf: self._perf.record_signal("progress_updated")
```

**2f. Periodic flush (1-second interval, ~line 466):**
```python
# Add a monotonic timestamp tracker in the drain loop
if self._perf and (time.monotonic() - _last_perf_flush) >= 1.0:
    self._perf.flush_row()
    _last_perf_flush = time.monotonic()
```

**2g. DB batch timing (~line 498-504):**
```python
if self._perf:
    t0 = time.monotonic()
with db_lock:
    self._db.update_pixel_hashes_batch(pending_updates)
if self._perf:
    self._perf.record_db_batch_ms((time.monotonic() - t0) * 1000)
```

### Step 3: Instrument `ui/results_panel.py` (2 lines)

Record UI-side backlog in `_flush_pending()` at [results_panel.py:379](dejaview/ui/results_panel.py#L379):

```python
def _flush_pending(self) -> None:
    if self._perf:
        self._perf.record_ui_backlog(
            len(self._pending_file_ids), len(self._pending_hash_ids)
        )
    # ... rest unchanged
```

This requires passing the `perf_monitor` reference through to ResultsPanel (one constructor arg).

### Step 4: Wire up in `main_window.py`

```python
# In _start_scan or wherever Scanner is instantiated:
perf = None
if os.environ.get("DEJAVIEW_PERF"):
    from core.perf_monitor import PerformanceMonitor
    perf = PerformanceMonitor(output_dir=appdata_dir, enabled=True)

scanner = Scanner(db, session_id, thumb_dir, perf_monitor=perf)
```

### Step 5: Add `--perf` flag to `main.py` entry point

```python
parser.add_argument("--perf", action="store_true", help="Enable performance telemetry CSV")
```

Set `os.environ["DEJAVIEW_PERF"] = "1"` if flag is present.

---

## Files Changed

| File | Nature of change |
|------|-----------------|
| `core/perf_monitor.py` | **NEW** — PerformanceMonitor class (~150 lines) |
| `core/scanner.py` | ~20 lines of conditional instrumentation |
| `ui/results_panel.py` | ~5 lines (constructor arg + backlog recording) |
| `ui/main_window.py` | ~8 lines (instantiate monitor, pass to scanner + panel) |
| `main.py` | ~3 lines (CLI flag) |

**Total:** ~185 new lines, ~0 existing lines removed.

---

## What the CSV Will Reveal

After running a scan with `DEJAVIEW_PERF=1`, the CSV answers every diagnostic question:

| Question | Column(s) to check |
|----------|-------------------|
| How long is Discovery vs Hashing? | `stage` + `elapsed_s` |
| Is the lock contended? | `lock_wait_ms` — if >10ms per acquire, contention is real |
| Is the executor starved? | `executor_queue_depth` — 0 means workers are idle waiting for submissions |
| Are signals flooding the UI? | `signals_per_sec` — if >500/s during Pass 1, that's the hang cause |
| Is the UI backlog growing? | `pending_file_ids`, `pending_hash_ids` — monotonically growing = main thread can't keep up |
| What causes the CPU sawtooth? | `active_futures` + `db_batch_ms` — correlate spikes with batch flushes |

---

## Expected Findings (Predictions)

Based on code analysis, the telemetry will likely confirm:

1. **Pass 1 signal rate is ~1000-3000/s** (100-file batches with 100 SELECT queries each take ~30-100ms, so ~10-30 batches/s × 100 signals = 1000-3000 signals/s). This exceeds what the Qt event loop can dispatch without stalling.

2. **Lock contention is negligible** (<1ms per acquire) because `update_pixel_hashes_batch` is fast (32-row `executemany` + commit ≈ 1-5ms on SSD).

3. **Executor queue depth oscillates between 0 and `window_size`**, confirming the sawtooth is I/O-driven bursts, not DB-caused.

4. **`pending_file_ids` grows unboundedly during Pass 1** because the main thread can't flush 200ms worth of accumulated IDs (each requiring a `get_file()` DB call) before the next 200ms batch arrives.
