# DejaView — Feature Request Plan: Scanner Throughput Optimization (Round 2)

## Overview

Raise CPU utilization from 11-18% to 50%+ on large image libraries by eliminating drain-loop bottlenecks in Pass 2. The previous throughput round (batched DB writes, raised caps, sliding window) unlocked multi-threading but the drain loop still serializes per-file duplicate queries that starve worker threads.

## Problem

On an 8-core/16-thread machine scanning small JPEGs from a SATA3 SSD, CPU sits at 11-18% and disk I/O at 4-5% — neither resource is saturated. Root causes:

1. **Per-file duplicate queries in drain loop** (scanner.py:398-408) — after each 32-file batch commit, the scanner thread runs `get_files_by_pixel_hash()` for every completed file (up to 32 SELECT queries, ~16-64ms total). During this time no new futures are submitted and completed futures pile up, starving workers.

2. **Per-file signal emission** (scanner.py:399-400) — `hash_complete` and `progress_updated` emitted for every file. Qt cross-thread signal emission involves mutex + event posting overhead, ~3-10ms per 32-file batch.

3. **`scan_delay_ms > 0` forces `workers = 1`** (scanner.py:309) — any non-zero throttle kills all parallelism instead of scaling proportionally.

4. **ETA tied to progress signals** (scan_control.py:134-178) — ETA display only updates when `progress_updated` fires. With batched signals or stalled drain, the display freezes.

## Solution

### 1. Remove per-file duplicate queries from drain loop (`core/scanner.py`)

Delete the `get_files_by_pixel_hash()` call and `duplicate_found` emission from the inner drain loop. Replace with deferred bulk detection:

- After the `while active:` loop ends, call `_emit_deferred_duplicates()`.
- For very large scans (10k+ images), also call it periodically every 500 completed files so the UI gets incremental duplicate updates.

New method `_emit_deferred_duplicates()` uses a single bulk query instead of N per-hash queries.

### 2. Add bulk duplicate query (`data/db.py`)

New method `get_all_duplicate_file_ids(session_id) -> dict[str, list[int]]`:
```sql
SELECT f.id, f.pixel_hash FROM files f
WHERE f.session_id = ? AND f.pixel_hash IS NOT NULL AND f.status = 'active'
  AND f.pixel_hash IN (SELECT pixel_hash FROM duplicate_groups WHERE session_id = ?)
ORDER BY f.pixel_hash
```
Returns `{pixel_hash: [file_id, ...]}` in one query — replaces N sequential `get_files_by_pixel_hash()` calls.

### 3. Batch signal emission (`core/scanner.py`)

- Emit `progress_updated` **once per batch** (not per file) — the UI debounces at 200ms anyway.
- Keep `hash_complete` per-file (ResultsPanel needs individual file_ids for tree updates) but emit them without interleaved DB queries.
- Keep `directory_hashed` as-is (already fires only on directory boundary).

### 4. Proportional scan_delay_ms throttling (`core/scanner.py`)

Replace the binary `workers = 1 if scan_delay_ms > 0` with proportional scaling:
- `scan_delay_ms` 1-5: `max(2, max_workers // 2)` workers
- `scan_delay_ms` 6-20: `max(1, max_workers // 4)` workers
- `scan_delay_ms` 0: full `max_workers`

The per-batch sleep stays as-is.

### 5. Decouple ETA from progress signals (`ui/scan_control.py`)

Add a 1-second `QTimer` that updates the ETA display independently:
- `on_progress_updated` stores `current`/`total` and updates the progress bar, but ETA text is computed by the timer.
- Timer starts on first progress signal, stops on completion/pause/stop.
- Guarantees the ETA updates every second regardless of signal batching.

## Files to Modify

| File | Change |
|------|--------|
| `dejaview/core/scanner.py` | Remove per-file dupe queries from drain loop; add `_emit_deferred_duplicates()`; batch `progress_updated` emission; proportional `scan_delay_ms` throttling |
| `dejaview/data/db.py` | Add `get_all_duplicate_file_ids()` bulk query method |
| `dejaview/ui/scan_control.py` | Add 1-second `QTimer` for ETA display; decouple from `progress_updated` signal rate |
| `dejaview/tests/unit/test_db.py` | Add test for `get_all_duplicate_file_ids()` |

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add `get_all_duplicate_file_ids()` to `db.py` | ⬜ | Single bulk query returning `{hash: [ids]}` |
| 2 | Add unit test for new method in `test_db.py` | ⬜ | Verify groups returned correctly, singletons excluded |
| 3 | Remove per-file dupe queries from drain loop | ⬜ | Delete `get_files_by_pixel_hash` + `duplicate_found` from inner loop |
| 4 | Add `_emit_deferred_duplicates()` to Scanner | ⬜ | Called after drain loop + periodically every 500 files |
| 5 | Batch `progress_updated` emission (once per batch) | ⬜ | Single emit after batch commit instead of per-file |
| 6 | Proportional `scan_delay_ms` throttling | ⬜ | Replace binary workers=1 with scaled worker count |
| 7 | Decouple ETA with 1-second QTimer in `scan_control.py` | ⬜ | Store current/total, timer computes + displays ETA |
| 8 | Run unit + integration tests | ⬜ | `python -m pytest tests/unit/ tests/integration/ --no-cov` |
| 9 | Manual large-library verification | ⬜ | Check CPU >50%, ETA updates every second, app responsive |

## Verification

```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q
python -m pytest tests/unit/ tests/integration/ --no-cov
```

Manual test:
1. Scan a large folder (1000+ images) on internal SSD
2. Task Manager: CPU should reach 50%+ (vs. 11-18% before)
3. ETA label updates every second without freezing
4. App remains responsive — no "Not Responding" in title bar
5. Pause/resume responds promptly (<500ms)
6. Duplicate badges appear after periodic checks and at scan completion
7. Scan with `scan_delay_ms > 0` — verify multi-worker throttling (not single-worker)
8. Scan from USB drive — verify adaptive behavior, app stays responsive
