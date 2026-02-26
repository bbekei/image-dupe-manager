# Feature Request — Simplification: Remove Duplicate-Action Functionality

## Goal

Strip all image-manipulation actions (keep, delete, rename, batch rules) from the application. Refocus on the core use case: **scanning directories, finding duplicates, storing hash data, and sharing scan results with others.** The CompareView is retained as a **read-only viewer** (thumbnails + metadata side-by-side, no action buttons).

A future **"ignore" capability** (mark a duplicate group as intentionally kept) is noted for later implementation.

## Motivation

The app's strongest value is its scanning/hashing engine and cross-library sharing. The keep/delete/rename workflow adds complexity without being the primary use case. Removing it simplifies the codebase, reduces maintenance burden, and sharpens the product focus.

---

## Overall: 0% complete (0/7 layers done)

## Layers Checklist

| Layer | Status | Scope | Files Affected |
|-------|--------|-------|----------------|
| **1 — Data layer** | ⬜ Pending | Remove `actions` table + 4 methods from `db.py` | `data/db.py` |
| **2 — CompareView simplification** | ⬜ Pending | Remove action classes/methods/buttons; keep read-only viewer | `ui/compare_view.py` |
| **3 — MainWindow cleanup** | ⬜ Pending | Remove `_on_actions_confirmed` + signal connection | `ui/main_window.py` |
| **4 — ResultsPanel** | ⬜ Pending | No changes needed (double-click still opens read-only CompareView) | `ui/results_panel.py` |
| **5 — Tests** | ⬜ Pending | Remove/update action-related tests across 5 files | `tests/` (5 files) |
| **6 — i18n** | ⬜ Pending | Remove/trim 4 translation contexts | `resources/i18n/` |
| **7 — Documentation** | ⬜ Pending | Update user guides to reflect read-only comparison | `resources/help/` |

---

## Layer 1: Data Layer (`data/db.py`) — Detailed Breakdown

| # | Task | Status | Detail |
|---|------|--------|--------|
| 1.1 | Remove `actions` table DDL | ⬜ Pending | Lines 66-75 — `CREATE TABLE IF NOT EXISTS actions (...)` |
| 1.2 | Remove `idx_actions_file` index | ⬜ Pending | Line 121 — `CREATE INDEX IF NOT EXISTS idx_actions_file ON actions(file_id)` |
| 1.3 | Remove `stage_action()` | ⬜ Pending | Lines ~362-370 — inserts into actions table |
| 1.4 | Remove `confirm_action()` | ⬜ Pending | Lines ~372-380 — updates action status to 'confirmed' |
| 1.5 | Remove `get_staged_actions()` | ⬜ Pending | Lines ~382-391 — joins actions + files for session |
| 1.6 | Remove `get_action()` | ⬜ Pending | Lines ~393-396 — single action lookup |

### What to KEEP in `db.py`

| Method/Object | Why Keep |
|---------------|----------|
| `update_file_status()` | Used by `folder_panel.py:91` (deactivation) and export test fixtures |
| `deactivate_files_under_folder()` | Used by `folder_panel.py:91` when removing a scan folder |
| `duplicate_groups` VIEW | Used by `results_panel.py` for duplicate detection display |
| `cleanup_orphaned_thumbnails()` | Thumbnails still generated for read-only CompareView |
| All sync/export tables & methods | Core sharing functionality — untouched |

### Backward Compatibility Note

Existing `library.db` files will still contain the `actions` table. Since the DDL uses `CREATE TABLE IF NOT EXISTS`, removing it from DDL simply means the table persists but is never read or written. **No migration needed** — the orphaned table is harmless.

---

## Layer 2: CompareView Simplification (`ui/compare_view.py`) — Detailed Breakdown

| # | Task | Status | Detail |
|---|------|--------|--------|
| 2.1 | Delete `_BatchRulesDialog` class | ⬜ Pending | Lines ~237-270 — "keep oldest / keep largest" modal |
| 2.2 | Delete `_ConfirmDialog` class | ⬜ Pending | Lines ~276-312 — staged action review modal |
| 2.3 | Simplify `_FileTile` | ⬜ Pending | Remove KEEP/DEL/Rename buttons + signals; keep thumbnail, path, size, date labels; keep peer/remote badge |
| 2.4 | Simplify `CompareView` | ⬜ Pending | See detail below |
| 2.5 | Remove `actions_confirmed` signal | ⬜ Pending | No actions to confirm |

### 2.4 `CompareView` — Methods to Remove vs. Keep

| Remove | Keep |
|--------|------|
| `_on_keep(file_id)` | Header with file count + SHA prefix |
| `_on_delete(file_id)` | Scrollable horizontal tile layout |
| `_on_rename(file_id, new_name)` | Close button |
| `_on_apply_all()` | `closed` signal |
| `_on_batch_rules()` | `load_group(pixel_hash)` data loading |
| `_on_confirm()` | |
| `_execute_actions(action_list)` | |
| `_path_within_scope()` | |
| "Apply to all" button | |
| "Batch rules..." button | |
| "Review & Confirm" button | |

### `_FileTile` — Before vs. After

| Before | After |
|--------|-------|
| Thumbnail (240×240) | Thumbnail (240×240) — **unchanged** |
| Path, size, date labels | Path, size, date labels — **unchanged** |
| KEEP button (green highlight) | **Removed** |
| DEL button (red highlight) | **Removed** |
| Rename inline field | **Removed** |
| `keep_clicked`, `delete_clicked`, `rename_requested` signals | **Removed** |
| Peer/remote read-only badge | Peer/remote read-only badge — **unchanged** |

---

## Layer 3: MainWindow Cleanup (`ui/main_window.py`) — Detailed Breakdown

| # | Task | Status | Detail |
|---|------|--------|--------|
| 3.1 | Remove `_on_actions_confirmed()` method | ⬜ Pending | Slot that refreshes results after action execution |
| 3.2 | Remove `actions_confirmed` signal connection | ⬜ Pending | Line ~316: `self._compare_view.actions_confirmed.connect(...)` |

### What to KEEP in `main_window.py`

| Element | Why Keep |
|---------|----------|
| `from ui.compare_view import CompareView` | CompareView still exists as read-only viewer |
| `self._compare_view` instance variable | Still created on double-click |
| `_on_compare_requested()` method | Opens read-only CompareView |
| `_close_compare_view()` method | Restores results panel |
| `compare_view_requested` signal connection | Still needed |
| `closed` signal connection | Still needed |

---

## Layer 4: ResultsPanel (`ui/results_panel.py`) — No Changes

| Element | Status |
|---------|--------|
| `compare_view_requested` signal | **Keep** — still emitted on double-click |
| `_on_item_double_clicked()` | **Keep** — opens read-only CompareView |
| Tree view, filters, badges | **Keep** — untouched |
| Cross-library display | **Keep** — untouched |

---

## Layer 5: Tests — Detailed Breakdown

| # | Task | Status | Detail |
|---|------|--------|--------|
| 5.1 | Update `tests/ui/test_compare_view.py` | ⬜ Pending | Remove action-related tests; keep tile display, close, remote badge tests |
| 5.2 | Delete `tests/e2e/test_e2e_compare.py` | ⬜ Pending | Entire file tests action workflow end-to-end |
| 5.3 | Update `tests/unit/test_db.py` | ⬜ Pending | Remove 5 action tests (see list below) |
| 5.4 | Update `tests/integration/test_regression.py` | ⬜ Pending | Remove wf3 (action staging) + wf4 (remote tile actions) tests |
| 5.5 | Keep `tests/ui/test_results_panel.py` | ✅ No change | compare_view_requested signal still exists |

### 5.1 — `test_compare_view.py` Tests to Remove

Tests related to action buttons, staging, batch rules, confirmation, and execution:
- All tests for KEEP/DEL button clicks and tile highlighting
- All tests for `_BatchRulesDialog` (oldest/largest rules)
- All tests for `_ConfirmDialog` (action review)
- All tests for `_execute_actions` (file delete/rename)
- All tests for rename validation in action context

Tests to KEEP (read-only viewer behavior):
- Tile displays thumbnail + metadata
- Remote/peer tiles show read-only badge
- Close button emits `closed` signal
- Layout and header display

### 5.3 — `test_db.py` Tests to Remove

| Test | Line | Reason |
|------|------|--------|
| `test_stage_action_for_file` | ~262 | Tests `stage_action()` |
| `test_action_status_defaults_to_staged` | ~268 | Tests actions table default |
| `test_confirm_action_sets_performed_at` | ~276 | Tests `confirm_action()` |
| `test_list_staged_actions_for_session` | ~286 | Tests `get_staged_actions()` |
| `test_stage_rename_with_detail` | ~299 | Tests `stage_action()` with rename |

### 5.4 — `test_regression.py` Tests to Remove

| Test | Reason |
|------|--------|
| `test_regression_wf3_*` (action staging/confirmation) | References `stage_action()`, `get_action()`, CompareView `_execute_actions()` |
| `test_regression_wf4_remote_tile_has_no_actions` | Tests action button absence on remote tiles — moot when all tiles lack action buttons |

---

## Layer 6: i18n (`resources/i18n/`) — Detailed Breakdown

| # | Task | Status | Detail |
|---|------|--------|--------|
| 6.1 | Remove `_BatchRulesDialog` context | ⬜ Pending | `app_hu.ts` lines ~362-388 — batch rule strings |
| 6.2 | Remove `_ConfirmDialog` context | ⬜ Pending | `app_hu.ts` lines ~389-414 — confirmation strings |
| 6.3 | Trim `_FileTile` context | ⬜ Pending | Remove Keep/Delete/Rename button label translations |
| 6.4 | Trim `CompareView` context | ⬜ Pending | Remove "Apply to all", "Batch rules...", "Review & Confirm" translations |
| 6.5 | Update `app.ts` (English source) | ⬜ Pending | Remove matching entries if present |
| 6.6 | Recompile `app_hu.qm` | ⬜ Pending | `lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm` |

---

## Layer 7: Documentation — Detailed Breakdown

| # | Task | Status | Detail |
|---|------|--------|--------|
| 7.1 | Update `resources/help/USER_GUIDE.md` | ⬜ Pending | Remove keep/delete/rename/batch sections; describe CompareView as read-only duplicate viewer |
| 7.2 | Update `resources/help/USER_GUIDE_HU.md` | ⬜ Pending | Same changes in Hungarian |
| 7.3 | Update root `USER_GUIDE.md` | ⬜ Pending | If different from resources copy |
| 7.4 | Update root `USER_GUIDE_HU.md` | ⬜ Pending | If different from resources copy |

---

## Future: "Ignore" Capability (Not Implemented)

After simplification, add the ability to mark a duplicate group as "ignored" (intentionally kept duplicates).

**Potential design:**
- New DB table: `ignored_groups (session_id, pixel_hash, ignored_at, reason)`
- Or: flag column on the `duplicate_groups` concept (would require materializing the view)
- ResultsPanel: dimmed badge or separate "Ignored" filter
- CompareView: single "Ignore this group" button in read-only view
- Export: option to include/exclude ignored groups

---

## Verification Plan

| Step | Command / Action | Expected |
|------|-----------------|----------|
| 1 | `cd dejaview && python -m pytest tests/unit/ --no-cov -q` | All pass, no action-related tests |
| 2 | `cd dejaview && python -m pytest tests/integration/ --no-cov -q` | All pass, no regression tests for actions |
| 3 | `cd dejaview && python -m pytest tests/ui/ --no-cov -q` | All pass, compare_view tests cover read-only behavior only |
| 4 | Launch app, scan a folder with duplicates | Scan completes, duplicates shown with badges |
| 5 | Double-click a duplicate in results tree | Read-only CompareView opens with thumbnails + metadata, no action buttons |
| 6 | Click Close in CompareView | Returns to results panel |
| 7 | Use Share → Export/Import | Works unchanged |
| 8 | Open app with existing `library.db` that has `actions` table | Loads without error |

---

## Files Changed Summary

| Action | File | Scope |
|--------|------|-------|
| **Modify** | `dejaview/data/db.py` | Remove `actions` table DDL + index + 4 methods (~40 LOC removed) |
| **Modify** | `dejaview/ui/compare_view.py` | Remove 2 dialog classes, strip action buttons/methods (~400 LOC removed, ~280 LOC remaining) |
| **Modify** | `dejaview/ui/main_window.py` | Remove `_on_actions_confirmed` + 1 signal connection (~10 LOC removed) |
| **Modify** | `dejaview/tests/ui/test_compare_view.py` | Remove action-related tests (~20 tests removed, ~10 kept) |
| **Delete** | `dejaview/tests/e2e/test_e2e_compare.py` | Entire file — action workflow e2e |
| **Modify** | `dejaview/tests/unit/test_db.py` | Remove 5 action tests (~50 LOC removed) |
| **Modify** | `dejaview/tests/integration/test_regression.py` | Remove wf3 + wf4 tests (~50 LOC removed) |
| **Modify** | `dejaview/resources/i18n/app_hu.ts` | Remove 2 contexts, trim 2 contexts |
| **Modify** | `dejaview/resources/i18n/app.ts` | Remove matching entries |
| **Regenerate** | `dejaview/resources/i18n/app_hu.qm` | Recompile via `lrelease` |
| **Modify** | `dejaview/resources/help/USER_GUIDE.md` | Remove action sections, describe read-only CompareView |
| **Modify** | `dejaview/resources/help/USER_GUIDE_HU.md` | Same in Hungarian |
| **Modify** | `USER_GUIDE.md` (root) | If different from resources copy |
| **Modify** | `USER_GUIDE_HU.md` (root) | If different from resources copy |

**Estimated net removal:** ~550+ LOC of production code, ~120+ LOC of tests

---

## Untouched Components

These files/modules require **no changes**:

| Component | File | Reason |
|-----------|------|--------|
| Pixel hasher | `core/hasher.py` | Pure function, no action dependency |
| Two-pass scanner | `core/scanner.py` | No action dependency |
| Export/import | `data/export.py` | Shares scan data, no action dependency |
| Google Drive sync | `data/sync.py` | Syncs exports, no action dependency |
| Folder panel | `ui/folder_panel.py` | Folder selection, no action dependency |
| Scan control | `ui/scan_control.py` | Scan buttons/progress, no action dependency |
| Share dialog | `ui/share_dialog.py` | Sync configuration, no action dependency |
| Help dialog | `ui/help_dialog.py` | Documentation display, no action dependency |
| Entry point | `main.py` | App startup, no action dependency |
| Build files | `dejaview.spec`, `installer.iss` | Auto-collected; compare_view.py still exists |

---

## Local Commands

```bash
# Run unit tests (fast, no PyQt6 needed for most)
cd dejaview && python -m pytest tests/unit/ --no-cov -q

# Run all non-e2e tests
cd dejaview && python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q

# Recompile Hungarian translations after .ts changes
lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm
```
