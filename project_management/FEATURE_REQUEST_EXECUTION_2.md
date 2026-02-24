# Feature Request Execution — Simplification: Remove Duplicate-Action Functionality

## Overall: 100% complete (7/7 layers done)

## Layers Checklist

| Layer | Status | Notes/Blockers | Completed |
|-------|--------|----------------|-----------|
| **1 — Data layer** | ✅ Done | Removed `actions` table DDL, `idx_actions_file` index, and 4 methods from `db.py` (~40 LOC removed) | Layer 1 |
| **2 — CompareView simplification** | ✅ Done | Removed 2 dialog classes, action buttons/signals/methods (~400 LOC removed, ~270 LOC remaining) | Layer 2 |
| **3 — MainWindow cleanup** | ✅ Done | Removed `_on_actions_confirmed` method + `actions_confirmed` signal connection (~8 LOC removed) | Layer 3 |
| **4 — ResultsPanel** | ✅ No change | Double-click still opens read-only CompareView | N/A |
| **5 — Tests** | ✅ Done | Rewrote `test_compare_view.py` (31→12 tests), deleted `test_e2e_compare.py`, removed `TestActions` class from `test_db.py`, removed wf3+wf4 from `test_regression.py` | Layer 5 |
| **6 — i18n** | ✅ Done | Removed `_BatchRulesDialog` + `_ConfirmDialog` contexts, trimmed `_FileTile` + `CompareView` contexts (121→101 translations). Recompiled `app_hu.qm`. | Layer 6 |
| **7 — Documentation** | ✅ Done | Updated all 4 user guides (EN + HU, resources + root). Removed action sections, described read-only CompareView. | Layer 7 |

---

## Work Log

### Layer 1 — Data layer (`data/db.py`)
- Removed `actions` table DDL (CREATE TABLE IF NOT EXISTS actions)
- Removed `idx_actions_file` index
- Removed `stage_action()`, `confirm_action()`, `get_staged_actions()`, `get_action()` methods
- Kept: `update_file_status()`, `deactivate_files_under_folder()`, `duplicate_groups` VIEW, `cleanup_orphaned_thumbnails()`, all sync/export tables & methods

### Layer 2 — CompareView simplification (`ui/compare_view.py`)
- Deleted `_BatchRulesDialog` class, `_ConfirmDialog` class, `_validate_rename()` function
- Removed from `_FileTile`: `keep_clicked`, `delete_clicked`, `rename_requested` signals; KEEP/DEL/Rename buttons; inline rename field; `set_marked()`, `_toggle_rename()`, `_submit_rename()` methods
- Removed from `CompareView`: `actions_confirmed` signal; `_on_keep()`, `_on_delete()`, `_on_rename()`, `_on_apply_all()`, `_on_batch_rules()`, `_on_confirm()`, `_execute_actions()`, `_path_within_scope()`, `_clear_staged_for_group()` methods; Apply/Batch/Confirm buttons
- Removed unused imports: `re`, `datetime`, `Path`, `QDialog`, `QDialogButtonBox`, `QLineEdit`, `QListWidget`, `QListWidgetItem`, `QMessageBox`
- Kept: header, scrollable tile layout, Close button, `closed` signal, tile count helpers

### Layer 3 — MainWindow cleanup (`ui/main_window.py`)
- Removed `_on_actions_confirmed()` method (slot that refreshed results after action execution)
- Removed `actions_confirmed` signal connection from `_on_compare_requested()`
- Kept: CompareView import, `_compare_view` instance, `_on_compare_requested()`, `_close_compare_view()`, `closed` signal connection

### Layer 5 — Tests
- **5.1** `test_compare_view.py`: Rewrote from 31 tests to 12 tests. Removed all KEEP/DEL staging, batch rules, rename, confirmation, path scope, and action signal tests. Added `test_local_tile_has_no_action_buttons`. Kept tile rendering, remote badge, header, close signal, format_size, and tile property tests.
- **5.2** `test_e2e_compare.py`: Deleted entire file (7 e2e action workflow tests: P4-T01 through P4-T07).
- **5.3** `test_db.py`: Removed `TestActions` class (5 tests). Updated `TestSchema` to remove `actions` table and `idx_actions_file` index from expected sets.
- **5.4** `test_regression.py`: Removed `test_regression_wf3_stage_and_confirm_delete` and `test_regression_wf4_remote_tile_has_no_actions`. Cleaned up unused imports (`QLabel`, `QPushButton`, `CompareView`).
- **5.5** `test_results_panel.py`: No changes needed (compare_view_requested signal still exists).

### Layer 6 — i18n (`resources/i18n/`)
- Removed `_BatchRulesDialog` context entirely (5 strings: Batch Rules, Apply automatic rule, Keep oldest, Keep largest, Cancel)
- Removed `_ConfirmDialog` context entirely (5 strings: Confirm Actions, actions will be performed, DELETE, RENAME, KEEP)
- Trimmed `_FileTile` context: removed KEEP, DEL, Rename, New filename, Invalid filename strings (6 strings removed, 4 kept)
- Trimmed `CompareView` context: removed Apply to all, Batch rules, Review & Confirm, No actions, No actions staged, Path outside scope, Invalid rename target, Some actions failed strings (8 strings removed, 2 kept: Close + header)
- `app.ts` (English source): No changes needed — these contexts were never present
- Recompiled `app_hu.qm` via lrelease: 101 translations (down from 121)

### Layer 7 — Documentation
- Updated `dejaview/resources/help/USER_GUIDE.md`:
  - Changed app description from action tool to duplicate viewer
  - Renamed "Step 4 — Compare and Decide" → "Step 4 — Compare Duplicates"
  - Removed KEEP/DEL buttons from ASCII art, replaced with [Close]
  - Removed Actions per file, Batch Rules, Confirming Actions subsections
  - Updated Cross-Library section: all tiles are read-only
  - Removed "act on them" from Stop section
- Updated `dejaview/resources/help/USER_GUIDE_HU.md` with equivalent Hungarian changes
- Copied both to root `USER_GUIDE.md` and `USER_GUIDE_HU.md`

---

## Files Changed Summary

| Action | File | Scope |
|--------|------|-------|
| **Modify** | `dejaview/data/db.py` | Removed `actions` table DDL + index + 4 methods (~40 LOC removed) |
| **Modify** | `dejaview/ui/compare_view.py` | Removed 2 dialog classes, stripped action buttons/methods (~400 LOC removed, ~270 LOC remaining) |
| **Modify** | `dejaview/ui/main_window.py` | Removed `_on_actions_confirmed` + 1 signal connection (~8 LOC removed) |
| **Modify** | `dejaview/tests/ui/test_compare_view.py` | Rewrote: 31 tests → 12 tests (read-only viewer tests only) |
| **Delete** | `dejaview/tests/e2e/test_e2e_compare.py` | Entire file — action workflow e2e (7 tests) |
| **Modify** | `dejaview/tests/unit/test_db.py` | Removed TestActions class (5 tests), updated schema assertions |
| **Modify** | `dejaview/tests/integration/test_regression.py` | Removed wf3 + wf4 tests (~80 LOC removed), cleaned unused imports |
| **Modify** | `dejaview/resources/i18n/app_hu.ts` | Removed 2 contexts, trimmed 2 contexts (24 strings removed) |
| **Regenerate** | `dejaview/resources/i18n/app_hu.qm` | Recompiled: 121 → 101 translations |
| **Modify** | `dejaview/resources/help/USER_GUIDE.md` | Removed action sections, described read-only CompareView |
| **Modify** | `dejaview/resources/help/USER_GUIDE_HU.md` | Same in Hungarian |
| **Modify** | `USER_GUIDE.md` (root) | Copy of resources version |
| **Modify** | `USER_GUIDE_HU.md` (root) | Copy of resources version |

---

## Local Commands

```bash
# Run unit tests (fast)
cd dejaview && python -m pytest tests/unit/ --no-cov -q

# Run all non-e2e tests
cd dejaview && python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q
```
