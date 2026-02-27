# Feature Request Execution: Scanner Throughput Optimization

## Overview

Optimized the Pass 2 hashing pipeline to better utilize available CPU and disk I/O by eliminating per-file DB commits, batching completions, tuning SQLite PRAGMAs, raising threading caps, and removing artificial thread priority throttling.

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add PRAGMA tuning to db.py `_DDL` | ✅ Done | Added `synchronous=NORMAL`, `cache_size=-8000`, `mmap_size=268435456` after `journal_mode=WAL` in `dejaview/data/db.py` |
| 2 | Add `update_pixel_hashes_batch()` to db.py | ✅ Done | New method using `executemany` + single `commit()`, added after existing `update_pixel_hash` in `dejaview/data/db.py` |
| 3 | Change thread priority to NormalPriority | ✅ Done | Changed `LowPriority` → `NormalPriority` at `dejaview/core/scanner.py:156` |
| 4 | Raise worker cap to 16, buffer factor to 4 | ✅ Done | `_PIPELINE_BUFFER_FACTOR` 2→4, max_workers cap 8→16 in `dejaview/core/scanner.py` |
| 5 | Add `_DB_BATCH_SIZE = 32` constant | ✅ Done | New constant at `dejaview/core/scanner.py:57` |
| 6 | Refactor completion loop with batched writes | ✅ Done | Replaced `as_completed`+`break` with `concurrent.futures.wait(timeout=0.1)`+drain+batch pattern in `dejaview/core/scanner.py:349-418` |
| 7 | Move duplicate queries outside db_lock | ✅ Done | Signal emission and `get_files_by_pixel_hash` now run outside `db_lock` (WAL concurrent reads) |
| 8 | Add test for `update_pixel_hashes_batch` | ✅ Done | `test_update_pixel_hashes_batch` in `dejaview/tests/unit/test_db.py` — verifies 4-row batch update |
| 9 | Run tests, verify | ✅ Done | 189 passed, 10 skipped (unit + integration) |
