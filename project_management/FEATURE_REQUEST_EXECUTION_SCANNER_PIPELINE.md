# Feature Request Execution: Scanner Pipeline & UI Responsiveness

## Overview

Rewrote Pass 2 hashing from a sequential per-directory loop to a sliding-window pipeline that keeps all worker threads busy across directory boundaries. Decoupled the expensive `_compute_folder_duplication()` tree walk from the 200ms debounce timer so it only runs at directory boundaries, eliminating mid-scan UI freezes.

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add `_needs_folder_recompute` flag to `ResultsPanel` | ✅ Done | Added `self._needs_folder_recompute: bool = False` in `__init__`; set `True` in `on_directory_hashed` before `_flush_pending()`; guarded `_compute_folder_duplication()` in `_flush_pending()` with `if hash_ids and self._needs_folder_recompute:` + reset. File: `ui/results_panel.py` |
| 2 | Add `_PIPELINE_BUFFER_FACTOR` constant to scanner.py | ✅ Done | `_PIPELINE_BUFFER_FACTOR = 2` at module level near `_IMAGE_EXTENSIONS`. File: `core/scanner.py` |
| 3 | Rewrite `_run_pass2()` with sliding-window pipeline | ✅ Done | Replaced per-directory submit-wait loop with: flat `_candidate_iter()` in leaf-first order → seed `window_size = workers * _PIPELINE_BUFFER_FACTOR` futures → drain via `as_completed` one at a time → decrement `dir_pending` counter → emit `directory_hashed` when counter reaches 0 → refill window with `_submit_next()`. File: `core/scanner.py` |
| 4 | Update leaf-first test for nondeterministic completion | ✅ Done | Changed `test_directories_processed_leaf_first` from strict ordering assertion to set-equality (both dirs hashed, order nondeterministic with pipeline). File: `tests/integration/test_scanner_pass2.py` |
| 5 | Add pipeline concurrency test | ✅ Done | Added `test_pipeline_hashes_multiple_directories_concurrently`: 4 dirs × 2 files, asserts all 4 `directory_hashed` signals emitted and 0 unhashed files remain. File: `tests/integration/test_scanner_pass2.py` |
| 6 | Update module docstring in scanner.py | ✅ Done | Reflects sliding-window pipeline architecture and cross-directory parallelism |
| 7 | Run full test suite | ✅ Done | 188 passed, 10 skipped (UI tests, expected) |
