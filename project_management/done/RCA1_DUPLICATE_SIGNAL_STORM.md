# RCA1: Duplicate Signal Storm Causing UI Freezes

**Date:** 2026-02-28
**Telemetry:** `perf_20260228_191114.csv` (570 rows, ~9.4 min, 26,599 files hashed)
**Symptom:** Progressive UI freezes — functional until ~3,500 files, short freezes at ~4,000, multi-minute freezes at ~7,700, effectively frozen by ~11,000. Thumbnails keep generating (CPU 60%, memory stable, disk 10%).

---

## Telemetry Analysis

| Metric | Value | Interpretation |
|--------|-------|----------------|
| `db_batch_ms` | Stable 15-47ms | Round 1 DB fix is working |
| `signal_duplicate_found` | **13,784 total** | 51.8% of files trigger duplicate signal |
| `pending_hash_ids` first 100 avg | 46.7 | Starting backpressure |
| `pending_hash_ids` last 100 avg | 177.3 | **280% growth** — UI can't keep up |
| `signals_per_sec` first 100 avg | 81.5 | Healthy throughput |
| `signals_per_sec` last 100 avg | 49.9 | **39% degradation** |
| Zero-signal window | elapsed 334-365s | **30-second complete UI stall** |
| `lock_wait_ms` | Always 0 | No thread contention |
| Executor queue/futures | 48/64 constant | Workers fully saturated — not the bottleneck |

### Comparison with rca0 (pre-Round 1)

| Metric | rca0 (8h scan) | rca1 (9.4min scan) |
|--------|---------------|-------------------|
| `db_batch_ms` growth | 4.43x (173→767ms) | Stable (~30ms) — **fixed** |
| `duplicate_found` signals | ~60 total | 13,784 — **regression** |
| `get_duplicate_groups()` calls | ~60 | 13,784 — **regression** |
| `pending_hash_ids` trend | Decreasing (331→13) | Increasing 280% — **regression** |
| UI freeze pattern | Gradual slowdown over 8h | Hard freeze at ~7,700 files in minutes |

---

## Root Cause: Incremental Detection Over-Signaling

The Round 1 fix replaced the periodic `_emit_deferred_duplicates()` (every 500 files, ~60 calls total) with inline per-file detection. This introduced two compounding problems:

### 1. Signal volume explosion
The scanner emits `duplicate_found` for **every file** that matches an existing duplicate hash, not just when a hash first becomes a duplicate. For 51.8% duplicate rate across 26,599 files, this generates 13,784 signals instead of the original ~60.

### 2. O(N²) UI work per duplicate group
Each `duplicate_found` signal triggers `on_duplicate_found()` on the main thread which:
- Calls `get_duplicate_groups()` → full `GROUP BY ... HAVING` VIEW query on the `files` table (13,784 times)
- Calls `self._pending_hash_ids.extend(file_ids)` where `file_ids` is the growing list for that hash

For a hash with N copies, the emissions send lists of sizes 2, 3, 4, ..., N:
- Total items queued = N(N+1)/2 - 1
- A hash with 50 copies queues 1,274 redundant badge update ids

### Why the freeze is progressive
As more files are hashed, more hashes become "known duplicates." Each subsequent file matching any known hash triggers the full signal → VIEW query → extend cycle. The probability of matching a known duplicate increases with scan progress, creating an accelerating feedback loop.

---

## Fixes Applied

### Fix 1 (P0): Emit `duplicate_found` only once per group
**File:** `core/scanner.py`
- Removed the `elif pixel_hash in known_dup_hashes` branch that emitted for every subsequent copy
- Now only emits when `len(ids) == 2` (hash first becomes a duplicate)
- Subsequent copies are handled by `hash_complete` → `_update_file_badge()` path

### Fix 2 (P0): Pass pixel_hash in signal, eliminate VIEW query
**File:** `core/scanner.py`, `ui/results_panel.py`
- Changed `duplicate_found` signal from `pyqtSignal(list)` to `pyqtSignal(str, list)` — `(pixel_hash, [file_id, ...])`
- `on_duplicate_found()` now does `self._duplicate_hashes.add(pixel_hash)` — O(1), no DB query
- Eliminated all `get_duplicate_groups()` calls from the live scan path

### Fix 3 (P1): Deduplicate `pending_hash_ids` queue
**File:** `ui/results_panel.py`
- `_flush_pending()` now deduplicates `_pending_hash_ids` via `dict.fromkeys()` before processing
- Prevents redundant badge updates for the same file_id in a single flush cycle

---

## Expected Impact

| Metric | rca1 (before) | Expected (after) |
|--------|--------------|-----------------|
| `duplicate_found` signals | 13,784 | ~num_unique_dup_hashes (much smaller) |
| `get_duplicate_groups()` calls | 13,784 | 0 (eliminated) |
| `pending_hash_ids` growth | 280% | Flat (deduplicated) |
| UI freezes | Hard freeze at ~7,700 | None expected |
