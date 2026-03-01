# DejaView — Feature Request Plan: Performance RCA2 — DB Write & Main-Thread Query Storm

## Overview
Fix progressive UI freezing during large scans (70k+ files, high duplicate rate). The app becomes unresponsive around 20k files processed and completely frozen by 32k. Root cause is growing DB batch write times combined with excessive per-file DB reads and un-throttled signals on the main thread.

## Problem
After RCA1 fixed the duplicate signal storm, a 70,499-file scan (98% duplicates, 12,406 duplicate groups) reveals three compounding bottlenecks:

1. **DB batch writes slow as table grows** — `update_pixel_hashes_batch()` commits 32 rows per transaction. As the `files` table grows, UPDATE + index maintenance time climbs from <200ms to 1,800ms spikes. The scanner thread is blocked during these writes, but more critically the main thread is starved of signal processing time.

2. **~98k individual DB reads on the main thread** — `_update_file_badge(file_id)` calls `self._db.get_file(file_id)` (a full SELECT) for every hash completion, even though `on_hash_complete` already receives the `pixel_hash` in the signal. These reads contend with scanner writes on the WAL.

3. **`directory_hashed` bypasses debounce** — 71,153 `directory_hashed` signals each call `_flush_pending()` immediately, defeating the 200ms rate-limiter. Each also triggers `get_folder_file_counts()` (a COUNT + LIKE prefix scan) in `folder_panel`, adding another ~71k queries on the main thread.

**Key telemetry (perf_20260228_213319.csv):**
- Scan duration: 41 minutes (2,461s), 98,915 files hashed, 12,525 duplicates found
- `db_batch_ms` average: 468ms in final phase, spikes to 1,828ms
- Zero-signal seconds (complete UI stall): 5% of scan duration (127/2,416 seconds)
- Hashing throughput degradation: 74 files/s (start) → 40 files/s (steady state)

## Solution

### Fix 1 (P0): Eliminate per-file DB reads in `_update_file_badge`

The `hash_complete` signal already carries `pixel_hash`. Pass it through the queue instead of discarding it:

- Change `_pending_hash_ids: list[int]` → `_pending_hash_updates: list[tuple[int, str]]` storing `(file_id, pixel_hash)` pairs
- `on_hash_complete(file_id, pixel_hash)`: queue `(file_id, pixel_hash)`
- `on_duplicate_found(pixel_hash, file_ids)`: queue `(fid, pixel_hash)` for each fid
- `_update_file_badge(file_id, pixel_hash)`: use the passed-in hash directly — **zero DB reads**
- Update `_flush_pending()` to unpack tuples and pass both args

**Impact:** Eliminates ~98k `SELECT * FROM files WHERE id=?` on the main thread.

### Fix 2 (P0): Debounce `directory_hashed` instead of immediate flush

Currently `on_directory_hashed()` calls `_flush_pending()` directly. Change to queue-and-debounce:

- `on_directory_hashed`: append to `_pending_folder_recomputes` and call `_ensure_timer_running()` (same as other signals)
- Remove the direct `_flush_pending()` call

**Impact:** Reduces `_flush_pending()` calls from ~71k to ~scan_duration/0.2s (~12k).

### Fix 3 (P0): Throttle `folder_panel.on_directory_hashed` DB queries

Each of 71k signals triggers `get_folder_file_counts()`. Add a debounce:

- Add a `_folder_update_timer` (500ms interval, single-shot) to `FolderPanel`
- `on_directory_hashed`: just mark the root folder as dirty and start the timer
- On timer tick: update only dirty root folders, clear dirty set

**Impact:** Reduces folder COUNT queries from ~71k to ~scan_duration/0.5s (~5k).

### Fix 4 (P1): Increase DB batch size from 32 to 128

Larger batches amortize commit + fsync overhead. The scanner already buffers updates in `pending_updates`:

- Change `_DB_BATCH_SIZE = 32` → `_DB_BATCH_SIZE = 128`

**Impact:** 4x fewer commits (3,000 → 770), proportionally fewer signal bursts.

### Fix 5 (P1): Batch `hash_complete` signals

Currently emits `hash_complete` per file after each DB batch (up to 128 with Fix 4). Replace with a single batch signal:

- Add `hash_complete_batch = pyqtSignal(list)` to Scanner — emits list of `(file_id, pixel_hash)` tuples
- Add `on_hash_complete_batch(updates)` slot to ResultsPanel that extends `_pending_hash_updates`
- Emit one batch signal per DB batch instead of N individual signals
- Keep per-file `hash_complete` for backward compatibility (tests, other consumers) but stop wiring it in `main_window.py`

**Impact:** Reduces cross-thread Qt signal events from ~98k to ~770.

### Fix 6 (P2): Coalesce `directory_hashed` signals

Collect completed directories during the batch loop and emit them together:

- Add `directories_hashed = pyqtSignal(list)` batch signal to Scanner
- Collect dirs that complete during each batch cycle, emit once
- Update `results_panel` and `folder_panel` to handle the batch variant
- Keep per-directory signal for tests

**Impact:** Reduces directory signal cross-thread events from ~71k to ~770.

## Files to Modify

| File | Change |
|------|--------|
| `core/scanner.py` | Increase `_DB_BATCH_SIZE` to 128; add `hash_complete_batch` and `directories_hashed` batch signals; coalesce directory completions per batch |
| `ui/results_panel.py` | Change pending queue to carry `(file_id, pixel_hash)` tuples; eliminate `get_file()` calls in badge update; debounce `on_directory_hashed`; add batch signal slots |
| `ui/folder_panel.py` | Add 500ms debounce timer for `on_directory_hashed`; track dirty root folders |
| `ui/main_window.py` | Wire new batch signals (`hash_complete_batch`, `directories_hashed`) |
| `tests/integration/test_scanner_pass2.py` | Add tests for batch signals |
| `tests/ui/test_results_panel.py` | Update for `(file_id, pixel_hash)` queue format |

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Fix 1: Carry pixel_hash through results_panel queue, eliminate get_file() calls | ✅ Done | `_pending_hash_updates: list[tuple[int, str]]`, `_update_file_badge(file_id, pixel_hash)` — zero DB reads |
| 2 | Fix 2: Debounce directory_hashed in results_panel | ✅ Done | `on_directory_hashed` now queues + `_ensure_timer_running()` instead of immediate flush |
| 3 | Fix 3: Throttle folder_panel.on_directory_hashed | ✅ Done | 500ms debounce timer with dirty-folder tracking in folder_panel.py |
| 4 | Fix 4: Increase _DB_BATCH_SIZE to 128 | ✅ Done | `_DB_BATCH_SIZE = 128` in scanner.py |
| 5 | Fix 5: Add hash_complete_batch signal, wire in main_window | ✅ Done | `hash_complete_batch = pyqtSignal(list)`, wired in main_window; individual `hash_complete` still emitted for backward compat |
| 6 | Fix 6: Add directories_hashed batch signal, wire consumers | ✅ Done | `directories_hashed = pyqtSignal(list)`, wired in main_window; individual `directory_hashed` still emitted for backward compat |
| 7 | Update tests for new signal signatures and queue format | ✅ Done | test_scanner_pass2.py updated to use `directories_hashed` batch signal |
| 8 | Run full test suite and verify | ✅ Done | 292 tests pass (203 unit/integration + 89 UI), 10 skipped |

## Verification

1. Run unit tests: `cd dejaview && python -m pytest tests/unit/ --no-cov -q`
2. Run integration tests: `cd dejaview && python -m pytest tests/integration/ --no-cov -q`
3. Run UI tests: `cd dejaview && python -m pytest tests/ui/ --no-cov -q`
4. Manual scan of the 70k-file directory with perf logging enabled — confirm:
   - No UI freezes through entire scan
   - Status bar and progress updates remain responsive
   - `db_batch_ms` stays reasonable (reduced spike frequency)
   - No zero-signal gaps (main thread never fully stalled)
   - Duplicate detection produces correct results
