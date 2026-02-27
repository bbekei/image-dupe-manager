# Feature Request Execution: Scanner Throughput Optimization (Round 2)

## Overview

Eliminated drain-loop bottlenecks in Pass 2 to raise CPU utilization from 11-18% toward 50%+. Deferred duplicate detection, batched signal emission, proportional throttling, and decoupled ETA display.

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add `get_all_duplicate_file_ids()` to `db.py` | ✅ Done | Single bulk SQL query returning `{pixel_hash: [file_id, ...]}`, excludes singletons via `duplicate_groups` view subquery |
| 2 | Add unit tests for new method in `test_db.py` | ✅ Done | `test_get_all_duplicate_file_ids` (groups returned, singletons excluded) + `test_get_all_duplicate_file_ids_excludes_deleted` (deleted files filtered) |
| 3 | Remove per-file dupe queries from drain loop | ✅ Done | Deleted `get_files_by_pixel_hash()` call and `duplicate_found` emit from inner signal loop (scanner.py:404-414 old) |
| 4 | Add `_emit_deferred_duplicates()` to Scanner | ✅ Done | New method uses bulk query; called after drain loop completes + periodically every 500 files (`_DUPE_CHECK_INTERVAL`) |
| 5 | Batch `progress_updated` emission | ✅ Done | Single `progress_updated.emit(current, total)` per batch instead of per-file; moved outside signal loop |
| 6 | Proportional `scan_delay_ms` throttling | ✅ Done | 0ms → full workers; 1-5ms → half workers (min 2); 6-20ms → quarter workers (min 1) |
| 7 | Decouple ETA with 1-second QTimer | ✅ Done | `_eta_timer` fires every 1s, computes rate/remaining independently; stopped on pause/stop/complete; `on_progress_updated` stores current/total only |
| 8 | Run unit + integration tests | ✅ Done | 154 passed (unit), 191 passed (unit+integration), 10 skipped |
| 9 | Update documentation artifacts | ✅ Done | Updated scanner.py module docstring (deferred dupes, batched signals, proportional throttling); updated USER_GUIDE.md and USER_GUIDE_HU.md (both resources/help/ and root copies) — Stage 2 description now reflects periodic dupe badges, multi-core usage, and 1-second ETA updates |
| 10 | Manual large-library verification | ⬜ | Pending user verification |
