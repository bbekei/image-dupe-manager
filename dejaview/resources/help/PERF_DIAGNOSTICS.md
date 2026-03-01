# Performance Telemetry — Diagnostic Interpretation Guide

## How to Collect Data

1. **Settings > Diagnostics > Enable performance telemetry** (checkbox), OR
2. Launch with `--perf` flag, OR
3. Set environment variable `DEJAVIEW_PERF=1`

Run a scan. On completion, the CSV is saved to `%APPDATA%\DejaView\perf_YYYYMMDD_HHMMSS.csv`.

Open it in Excel, LibreOffice Calc, or load it with pandas:
```python
import pandas as pd
df = pd.read_csv("perf_20260228_143012.csv", comment="#")
```

---

## Column Reference

| Column | Unit | What it measures |
|--------|------|-----------------|
| `timestamp` | HH:MM:SS | Wall-clock time of this sample |
| `wall_clock` | seconds | Seconds since scan started |
| `stage` | text | Current stage: `discovery` or `hashing` |
| `elapsed_s` | seconds | Time spent in the current stage so far |
| `lock_wait_ms` | ms | Time threads spent waiting to acquire the DB lock (this interval) |
| `lock_hold_ms` | ms | Time the DB lock was held (this interval) |
| `lock_acquires` | count | Number of lock acquisitions (this interval) |
| `executor_queue_depth` | count | Items waiting in ThreadPoolExecutor queue |
| `active_futures` | count | Futures currently in the sliding window |
| `pending_db_updates` | count | Hash results waiting to be flushed to DB |
| `signals_emitted` | count | Total Qt signals emitted (this interval) |
| `signals_per_sec` | rate | Signal emission rate |
| `signal_file_discovered` | cumulative | Total file_discovered signals emitted |
| `signal_hash_complete` | cumulative | Total hash_complete signals emitted |
| `signal_progress_updated` | cumulative | Total progress_updated signals emitted |
| `signal_duplicate_found` | cumulative | Total duplicate_found signals emitted |
| `signal_directory_hashed` | cumulative | Total directory_hashed signals emitted |
| `pending_file_ids` | count | UI-side: queued file discoveries awaiting flush |
| `pending_hash_ids` | count | UI-side: queued hash completions awaiting flush |
| `db_batch_ms` | ms | Total DB write time (this interval) |
| `db_batch_count` | count | Number of DB batch writes (this interval) |
| `files_hashed_total` | cumulative | Total files hashed so far |
| `workers` | count | Number of worker threads configured |

---

## Diagnostic Decision Tree

### Problem 1: UI Shows "Not Responding"

**Check `pending_file_ids` during the `discovery` stage.**

```
IF pending_file_ids grows continuously (e.g., 0 → 500 → 2000 → 5000):
  → DIAGNOSIS: Signal storm during Pass 1
  → The scanner emits file_discovered per file (up to 30k signals).
    The Qt main thread can't dequeue and process them fast enough.
  → FIX: Batch file_discovered emissions — emit once per 100-file
    batch instead of per file, or suppress during discovery entirely
    and do a single tree reload at Pass 1 completion.

IF pending_file_ids stays small but pending_hash_ids grows:
  → DIAGNOSIS: _flush_pending() is too slow during Pass 2
  → Each debounce tick calls get_file(id) per pending hash — these
    DB reads compete with scanner writes on the same connection.
  → FIX: Batch the badge updates, or cache file data in memory
    instead of re-querying the DB per file.

IF both stay small:
  → DIAGNOSIS: UI hang is caused by something else
  → Check if _compute_folder_duplication() is running too often
    (look at signal_directory_hashed rate — if >10/s, the O(N)
    tree walk fires too frequently).
```

### Problem 2: CPU Sawtooth (10-19% then spikes to 50-60%)

**Plot `active_futures` and `db_batch_ms` over `wall_clock`.**

```
IF active_futures oscillates between 0 and window_size:
  → DIAGNOSIS: I/O-bound bursts
  → Workers finish in bursts when the OS read-ahead cache delivers
    a cluster of files. Between bursts, all workers block on disk I/O.
  → EVIDENCE: Valleys in active_futures correlate with CPU valleys.
  → FIX: Increase max_inflight_dirs to allow more parallel I/O
    across directories, or detect SSD vs HDD and auto-tune.

IF active_futures stays near window_size but CPU still fluctuates:
  → DIAGNOSIS: DB batch writes cause CPU spikes
  → db_batch_ms spikes correlate with CPU spikes — the executemany +
    commit + signal emission burst happens in a tight loop.
  → FIX: Spread signal emission across time instead of emitting
    32 hash_complete signals in a tight loop after each DB batch.

IF executor_queue_depth stays at 0:
  → DIAGNOSIS: Workers are starving for work
  → The submission logic isn't keeping up — check if _deferred
    queue is growing (locality gate is too restrictive).
  → FIX: Relax max_inflight_dirs or remove the locality gate.
```

### Problem 3: Lock Contention

**Check `lock_wait_ms` per interval.**

```
IF lock_wait_ms > 50 ms per interval:
  → DIAGNOSIS: Real contention — multiple threads competing for DB lock
  → This shouldn't happen with the current design (only the scanner
    thread holds the lock, workers don't touch the DB directly).
  → INVESTIGATE: Is something else acquiring the lock?

IF lock_wait_ms < 5 ms per interval:
  → DIAGNOSIS: Lock contention is NOT the problem
  → The lock is fast (32-row executemany + commit ≈ 1-5ms on SSD).
  → Look elsewhere for the bottleneck.
```

### Problem 4: Slow Hashing Throughput

**Calculate files/second: `files_hashed_total / wall_clock`.**

```
IF rate < 10 files/sec with multiple workers:
  → DIAGNOSIS: I/O bottleneck (HDD or network drive)
  → Check executor_queue_depth — if consistently 0, workers are
    idle waiting for work. If consistently high, workers are busy
    but the images are very large.
  → FIX: For HDD, the locality-aware buffering helps but is limited.
    Consider pre-reading file data into memory before hashing.

IF rate is good (50+ files/sec) but scan takes too long:
  → DIAGNOSIS: Pass 1 discovery is the bottleneck
  → Check elapsed_s for the "discovery" stage vs "hashing" stage.
  → FIX: If discovery > 30% of total time, consider parallelizing
    os.walk() across root folders.
```

---

## Quick Analysis Script

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("perf_XXXXXXXX_XXXXXX.csv", comment="#")

fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)

# 1. Signal rate
axes[0].plot(df["wall_clock"], df["signals_per_sec"], label="signals/sec")
axes[0].set_ylabel("Signals/sec")
axes[0].legend()

# 2. UI backlog
axes[1].plot(df["wall_clock"], df["pending_file_ids"], label="pending_file_ids")
axes[1].plot(df["wall_clock"], df["pending_hash_ids"], label="pending_hash_ids")
axes[1].set_ylabel("UI Backlog")
axes[1].legend()

# 3. Queue pressure
axes[2].plot(df["wall_clock"], df["active_futures"], label="active_futures")
axes[2].plot(df["wall_clock"], df["executor_queue_depth"], label="queue_depth")
axes[2].set_ylabel("Executor")
axes[2].legend()

# 4. Lock + DB timing
axes[3].plot(df["wall_clock"], df["lock_wait_ms"], label="lock_wait_ms")
axes[3].plot(df["wall_clock"], df["db_batch_ms"], label="db_batch_ms")
axes[3].set_ylabel("ms")
axes[3].set_xlabel("Wall clock (seconds)")
axes[3].legend()

plt.suptitle("DejaView Scan Performance Telemetry")
plt.tight_layout()
plt.savefig("perf_analysis.png", dpi=150)
plt.show()
```

---

## Interpreting the Summary Row

The last line of the CSV (prefixed with `#`) contains a JSON summary:

```json
{
  "total_elapsed_s": 245.3,
  "stages": {"discovery": 12.1, "hashing": 233.2},
  "lock_wait_total_ms": 45.2,
  "lock_hold_total_ms": 890.1,
  "lock_acquires_total": 312,
  "signals_total": 45230,
  "signal_breakdown": {
    "file_discovered": 30000,
    "hash_complete": 15000,
    "progress_updated": 200,
    "duplicate_found": 25,
    "directory_hashed": 5
  },
  "files_hashed": 15000
}
```

**Red flags in summary:**
- `signals_total > 10000` during discovery → signal storm, needs batching
- `lock_wait_total_ms > 5000` → real contention, investigate threading
- `stages.discovery > stages.hashing * 0.3` → Pass 1 is bottleneck
- `lock_hold_total_ms / lock_acquires_total > 20` → DB writes are slow (per-batch avg > 20ms)
