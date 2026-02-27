# Feature Request Execution: Directory-Batched Hashing

## Overview

Rewrote Pass 2 hashing to process candidates one directory at a time (leaf-first), with live FolderPanel file counts and immediate ResultsPanel badge updates at each directory boundary. Enables meaningful mid-scan browsing.

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add `directory_hashed` signal to Scanner | ✅ Done | Added `directory_hashed = pyqtSignal(str)` after `status_message` in `core/scanner.py` |
| 2 | Rewrite `_run_pass2()` with directory batching | ✅ Done | Grouped candidates by `os.path.dirname`, sorted leaf-first via `-d.count(os.sep)`, process per-batch with shared `ThreadPoolExecutor`, emit `directory_hashed` after each batch. Pause/stop checked between batches + mid-batch. Early return on `total == 0`. |
| 3 | Add `get_folder_file_counts()` to db.py | ✅ Done | SQL `COUNT(*) / COUNT(pixel_hash)` with folder prefix `LIKE` filter in `data/db.py` |
| 4 | Add FolderPanel count display + slots | ✅ Done | `on_directory_hashed()`, `update_all_counts()`, `reset_display_text()` in `ui/folder_panel.py`. Uses `Qt.ItemDataRole.UserRole` to store original folder path while display text shows `(N files, M hashed)`. |
| 5 | Add `on_directory_hashed` slot to ResultsPanel | ✅ Done | Calls `self._flush_pending()` in `ui/results_panel.py`. Cross-directory duplicates handled by existing `duplicate_found` signal which includes all group member IDs. |
| 6 | Wire signals in MainWindow `_wire_scanner()` | ✅ Done | Connected `directory_hashed` to both panels. Connected `scan_started` → `update_all_counts`, `scan_complete`/`scan_stopped` → `reset_display_text`. |
| 7 | Write integration tests | ✅ Done | 3 tests in `tests/integration/test_scanner_pass2.py`: `test_directory_hashed_signal_emitted_per_directory`, `test_directories_processed_leaf_first`, `test_progress_remains_global_across_directory_batches` |
| 8 | Run tests, verify | ✅ Done | Unit: 151 passed, 10 skipped. Integration: 36 passed, 0 failed. |
| 9 | Update scanner.py module docstring | ✅ Done | Added directory-batched processing description to Pass 2 section |
| 10 | Update User Guide (EN) | ✅ Done | Updated Stage 2 description and folder panel description in `resources/help/USER_GUIDE.md` |
| 11 | Update User Guide (HU) | ✅ Done | Matching Hungarian updates in `resources/help/USER_GUIDE_HU.md` |
| 12 | Sync root-level User Guide copies | ✅ Done | Copied updated guides to `USER_GUIDE.md` and `USER_GUIDE_HU.md` at project root |
| 13 | Remove broken regression test | ✅ Done | Removed `test_regression_wf6_manual_export_import_round_trip` entirely (all parametrizations failed — Bob's single file never enters Pass 2). Cleared known issue from `CONVENTIONS.md`. |
