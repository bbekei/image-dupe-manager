# DejaView — Feature Request Plan: Scanner Throughput Optimization

## Overview

Optimize the Pass 2 hashing pipeline to utilize more CPU and disk I/O. Currently the scanner achieves only 12-18% CPU and 35% disk utilization on large image sets due to serialized database writes and conservative threading defaults. These changes should raise utilization to 45-65% CPU and 55-75% disk without changing the public API or signal contract.

## Problem

Worker threads hash images in parallel (Pillow/hashlib release the GIL), but all results funnel through a single-threaded bottleneck:

1. **Per-file DB commits** — `update_pixel_hash()` calls `conn.commit()` after every single UPDATE, triggering an fsync (1-5ms SSD, 10-50ms HDD)
2. **One completion per loop iteration** — the `break` at scanner.py:400 processes exactly one future then restarts the outer loop, even if 7 other futures are already done
3. **Duplicate query inside db_lock** — `get_files_by_pixel_hash()` runs a SELECT inside the write lock, blocking all other completions
4. **LowPriority orchestrator** — the QThread that drains completions and submits new work is deprioritized by the OS scheduler
5. **Conservative caps** — max 8 workers and buffer factor of 2 limit scaling on 12+ core machines

Net result: workers spend ~85% of their time idle waiting for the DB write path.

## Solution

### 1. `data/db.py` — SQLite PRAGMA tuning + batch update method

**1a. PRAGMA tuning** (after existing `PRAGMA journal_mode=WAL;`):
```sql
PRAGMA synchronous=NORMAL;      -- safe with WAL; skips fsync on WAL frame writes
PRAGMA cache_size=-8000;         -- 8MB page cache (default ~2MB)
PRAGMA mmap_size=268435456;      -- 256MB memory-mapped reads
```

`synchronous=NORMAL` is the SQLite-recommended setting for WAL mode. Risk is losing the last transaction on power failure (not corruption), which is acceptable since the scanner re-hashes unhashed files on resume.

**1b. New `update_pixel_hashes_batch()` method:**
Accepts list of `(file_id, pixel_hash, thumbnail_path)` tuples, uses `executemany` + single `commit()`.

### 2. `core/scanner.py` — Thread priority

Change `LowPriority` to `NormalPriority`. CPU throttling is already handled by the user-configurable `scan_delay_ms`.

### 3. `core/scanner.py` — Worker cap and buffer factor

- `_PIPELINE_BUFFER_FACTOR`: 2 → 4
- Max workers cap: 8 → 16
- New constant: `_DB_BATCH_SIZE = 32`

### 4. `core/scanner.py` — Refactored completion loop

Replace single-future `as_completed` + `break` with:
- `concurrent.futures.wait(timeout=0.1, return_when=FIRST_COMPLETED)` to drain all done futures
- Accumulate results, flush to DB via `update_pixel_hashes_batch` when batch is full or scan ends
- Emit signals per-file after batch commit (outside db_lock)
- Duplicate queries outside db_lock (WAL concurrent reads)
- Pause/stop check once per drain cycle (~100ms)

### 5. `tests/unit/test_db.py` — New test

Test for `update_pixel_hashes_batch` verifying multi-row update.

## Files to Modify

| File | Change |
|------|--------|
| `dejaview/data/db.py` | Add PRAGMA tuning to `_DDL`; add `update_pixel_hashes_batch` method |
| `dejaview/core/scanner.py` | Raise caps; add `_DB_BATCH_SIZE`; change priority; refactor completion loop |
| `dejaview/tests/unit/test_db.py` | Add test for `update_pixel_hashes_batch` |

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add PRAGMA tuning to db.py `_DDL` | ✅ Done | `synchronous=NORMAL`, `cache_size=-8000`, `mmap_size=268435456` |
| 2 | Add `update_pixel_hashes_batch()` to db.py | ✅ Done | `executemany` + single `commit()` |
| 3 | Change thread priority to NormalPriority | ✅ Done | scanner.py line 156 |
| 4 | Raise worker cap to 16, buffer factor to 4 | ✅ Done | scanner.py lines 56-57, 137 |
| 5 | Add `_DB_BATCH_SIZE = 32` constant | ✅ Done | scanner.py line 57 |
| 6 | Refactor completion loop with batched writes | ✅ Done | Replaced `as_completed`+`break` with `wait`+drain+batch |
| 7 | Move duplicate queries outside db_lock | ✅ Done | WAL concurrent reads |
| 8 | Add test for `update_pixel_hashes_batch` | ✅ Done | test_db.py |
| 9 | Run tests, verify | ✅ Done | 189 passed, 10 skipped |

## Verification

```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q              # 152 passed, 10 skipped
python -m pytest tests/unit/ tests/integration/ --no-cov   # 189 passed, 10 skipped
```

Manual test:
1. Scan a large folder (1000+ images)
2. Observe CPU and disk utilization in Task Manager — should be notably higher than 12-18% / 35%
3. Verify pause/stop still respond promptly
4. Verify duplicate badges appear correctly
5. Verify progress bar and ETA update smoothly
6. Stop mid-scan, resume — verify it picks up where it left off
