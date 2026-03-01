# Fix: Progressive Scan Slowdown — Execution Log

**Date:** 2026-02-28
**RCA:** RCA_PROGRESSIVE_SCAN_SLOWDOWN.md
**Status:** COMPLETE

---

## Telemetry Analysis

Analyzed `perf_20260228_075820.csv` (27,023 rows, 8-hour scan of 70k files). Key findings:

- **RC#1 (tree lookups) NOT confirmed** — `pending_hash_ids` peaks decrease over time (331→13), UI keeps up
- **RC#2 (folder recompute) partially confirmed** — 1.76x directory gap growth
- **RC#3 (DB cost) STRONGLY confirmed** — `db_batch_ms` grows 4.43x (173ms→767ms), matching 4x throughput drop (33→8 files/sec)

Original RCA priority was inverted: RC#3 (ranked P2) is the actual primary bottleneck.

---

## Changes

### Modified: `data/db.py` (+3 lines)
- Added composite index `idx_files_session_hash_status ON files(session_id, pixel_hash, status)` to DDL
- Covers `duplicate_groups` view, `get_all_duplicate_file_ids()`, and all session-scoped file queries
- Applied via `executescript` with `IF NOT EXISTS` — existing databases get it on next open, no migration needed

### Modified: `core/scanner.py` (~30 lines changed)
- Removed `_DUPE_CHECK_INTERVAL` constant (no longer needed)
- Removed `_emit_deferred_duplicates()` method and all calls to it
- Removed `last_dupe_check` counter from `_run_pass2()`
- Added `hash_to_ids: dict[str, list[int]]` and `known_dup_hashes: set[str]` in `_run_pass2()`
- Inline incremental duplicate detection: when a hash's file count reaches 2, emit `duplicate_found`; subsequent copies emit with the full list
- Detection is O(1) per file instead of O(N) every 500 files

### Modified: `ui/results_panel.py` (~60 lines changed)
- Added `_file_id_to_item: dict[int, QStandardItem]` — O(1) file lookup replacing O(N) recursive tree search
  - Populated in `_add_file_to_tree()`, cleared in `reload()`
  - `_find_file_item()` reduced to single dict.get() call
  - Removed `_find_file_item_recursive()` method entirely
- Added `ROLE_FOLDER_DUP_COUNT` data role for caching per-folder duplicate counts
- Replaced `_needs_folder_recompute: bool` with `_pending_folder_recomputes: list[str]`
- `on_directory_hashed()` now queues specific dir_path instead of setting a global flag
- `_flush_pending()` calls `_recompute_folder_chain(dir_path)` per completed directory
- Added `_recompute_folder_chain()` — walks only the target folder + parent chain using cached subtotals
- Added `_compute_folder_dup_single()` — computes one folder's totals from direct children (files + cached subfolder data)
- Updated `_compute_folder_dup_recursive()` to also set `ROLE_FOLDER_DUP_COUNT` (used by `reload()`)

### Updated: `RCA_PROGRESSIVE_SCAN_SLOWDOWN.md`
- Added telemetry validation section with CSV evidence
- Corrected priority ordering: DB cost (P0) > folder recompute (P1) > tree lookups (P1 preventive)
- Marked fixes as applied

---

## Complexity Improvements

| Operation | Before | After |
|-----------|--------|-------|
| Duplicate detection (per scan) | O(N) every 500 files × ~60 invocations | O(1) per file, inline |
| File item lookup | O(N) recursive tree walk per badge update | O(1) dict lookup |
| Folder duplication recompute | O(total_tree) per directory boundary | O(folder_size + depth) per directory |
| DB duplicate query (per invocation) | Full table scan (no composite index) | Composite index covers all columns |

---

## Verification

- [ ] `python -m pytest tests/unit/ --no-cov -q` — unit tests pass
- [ ] Scan 1k+ files with telemetry: `db_batch_ms` stays flat, throughput stable
- [ ] Folder duplication badges display correctly
