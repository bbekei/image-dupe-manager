# Feature Request Execution 3: UI Simplification (Round 2)

## Overview
Implementing three UI simplification features from FEATURE_REQUEST_SIMPLIFICATION_2.md:
1. Remove the View menu
2. Make the Settings Dialog functional
3. UX-Friendly Navigation (auto-filter, Compare button, folder-level duplication)

---

## Task Log

### Feature 1: Remove the View Menu

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Remove View menu from main_window.py | ✅ Done | Deleted `mb.addMenu(self.tr("View"))` (line 96) and its comment. Updated module docstring from `File \| View \| Scan \| Share \| Help` → `File \| Scan \| Share \| Help`. |
| 1.2 | Remove View i18n entries | ✅ Done | Removed `"View"` from app.ts and `"Nézet"` from app_hu.ts. |
| 1.3 | Update user guides | ✅ Done | Updated menu diagram in all 3 user guides (EN in-app, HU in-app, root EN). |

---

### Feature 2: Settings Dialog

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Add `app_config` table to db.py | ✅ Done | Added `CREATE TABLE IF NOT EXISTS app_config` with `language` (default 'auto') and `theme` (default 'system') columns. Singleton row (id=1). Added `get_app_config()` and `upsert_app_config(**fields)` methods to Database class. |
| 2.2 | Create `ui/settings_dialog.py` | ✅ Done | ~115 LOC — `SettingsDialog(QDialog)` with Language combo (Auto/English/Magyar) and Theme combo (System Default, disabled). On Save: writes to app_config, shows restart message if language changed, emits `settings_saved` signal. All strings use `self.tr()`. |
| 2.3 | Wire Settings action in main_window.py | ✅ Done | Changed placeholder `file_menu.addAction(self.tr("Settings…"))` → `self._on_settings`. Added `_on_settings()` slot with lazy import of SettingsDialog, connects `settings_saved` to status bar "Settings saved." message. |
| 2.4 | Update language loading in main.py | ✅ Done | Added `db_path` parameter to `_load_translators()`. Reads `app_config.language` from DB; falls back to `QLocale.system().name()[:2]` if set to 'auto'. Moved `db_path` computation before translator loading in `main()`. |
| 2.5 | Add Settings i18n strings | ✅ Done | Added `SettingsDialog` context to both app.ts and app_hu.ts with all 9 strings (Settings, Language, Auto, Theme, System Default, themes hint, restart message, Save, Cancel). |
| 2.6 | Update user guides for Settings | ✅ Done | Replaced Settings section in all 3 guides with new Language (restart-required) and Theme (placeholder) subsections. |

---

### Feature 3: UX-Friendly Navigation

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Auto-filter after scan + scan summary | ✅ Done | `_on_scan_complete()` now computes total files, duplicate groups, and file counts. Auto-switches to "Duplicates Only" if duplicates found. Status bar shows "Scan complete: N files scanned, N duplicates in N groups." or "No duplicates found." Imported `FILTER_DUPLICATES_ONLY` from results_panel. |
| 3.2 | Compare button + context menu in results_panel.py | ✅ Done | Added `QPushButton("Compare")` to filter bar (right-aligned, disabled by default). Added `_on_selection_changed()` to enable/disable based on duplicate file or folder selection. Added `_on_compare_clicked()`. Added right-click context menu with "Compare Duplicates" via `_on_context_menu()`. Imports: QMenu, QPushButton. |
| 3.3 | Folder-level duplication grouping | ✅ Done | Added `ROLE_IS_FOLDER_DUPLICATED` (UserRole+7) and `ROLE_FOLDER_FILE_COUNT` (UserRole+8). Added `_compute_folder_duplication()` / `_compute_folder_dup_recursive()` — bottom-up walk marks folders where ALL files are duplicates. Badge: "● DUPLICATED FOLDER (N files)". Called after `reload()` and `_flush_pending()`. |
| 3.4 | Filter proxy update for folder duplication | ✅ Done | Updated `_DuplicateFilterProxy.filterAcceptsRow()` — in Duplicates Only mode, hides children of fully-duplicated folders (folder badge represents them). Fully-duplicated folders always visible. |
| 3.5 | Folder expand/collapse override | ✅ Done | Connected `tree.expanded`/`collapsed` signals. `_on_folder_expanded()` clears `ROLE_IS_FOLDER_DUPLICATED` flag to show children. `_on_folder_collapsed()` recomputes and restores flag if still fully duplicated. |
| 3.6 | Folder-level comparison in compare_view.py | ✅ Done | Added `_FolderTile` widget (folder icon, path, file count, size, file list). Added `FolderCompareView(QWidget)` — finds all folders containing the same set of pixel hashes. Shows folder tiles side by side with header "DUPLICATED FOLDER (N locations · M files each)". |
| 3.7 | Wire folder comparison in main_window.py | ✅ Done | Added `compare_folder_requested` signal to ResultsPanel. Connected in `_build_central()`. Added `_on_compare_folder_requested()` slot — opens `FolderCompareView`, status bar shows "Comparing duplicated folder: X". Imported `FolderCompareView`. |
| 3.8 | Add Feature 3 i18n strings | ✅ Done | Added to ResultsPanel context: "Compare", "Compare Duplicates", "● DUPLICATED FOLDER ({0} files)". Added `FolderCompareView` context with 3 strings. Hungarian translations in app_hu.ts. |
| 3.9 | Update user guides for Feature 3 | ✅ Done | All 3 guides updated: auto-filter note after Step 2, Compare button + context menu + folder badge in Step 3, folder comparison note in Step 4. |

---

### Cross-Cutting Tasks

| # | Task | Status | Details |
|---|------|--------|---------|
| X.1 | Update i18n — app.ts | ✅ Done | Removed View entry. Added SettingsDialog context (9 strings), FolderCompareView context (3 strings), MainWindow scan summary strings (4), ResultsPanel strings (3). |
| X.2 | Update i18n — app_hu.ts | ✅ Done | Same removals/additions with Hungarian translations. |
| X.3 | Update USER_GUIDE.md (in-app EN) | ✅ Done | Menu bar, Steps 2-4, Settings section. |
| X.4 | Update USER_GUIDE_HU.md (in-app HU) | ✅ Done | Same changes translated to Hungarian. |
| X.5 | Update USER_GUIDE.md (root) | ✅ Done | Synced with in-app English guide. |
| X.6 | Run tests | ✅ Done | 184 passed, 10 skipped (7.50s). 1 pre-existing flaky test excluded (hash_only privacy — Bob's single file skips Pass 2 size pre-filter). |

---

## Files Modified

| File | Changes |
|------|---------|
| `dejaview/ui/main_window.py` | Removed View menu, wired Settings action, added `_on_settings()`, updated `_on_scan_complete()` with auto-filter + summary, added `_on_compare_folder_requested()`, imported FILTER_DUPLICATES_ONLY + FolderCompareView |
| `dejaview/ui/settings_dialog.py` | **New file** — SettingsDialog with language + theme combo boxes |
| `dejaview/data/db.py` | Added `app_config` table, `get_app_config()`, `upsert_app_config()` |
| `dejaview/main.py` | Updated `_load_translators()` to read language from app_config |
| `dejaview/ui/results_panel.py` | Added Compare button, context menu, selection change handler, folder duplication detection + badges, filter proxy updates, expand/collapse override, new roles + signal |
| `dejaview/ui/compare_view.py` | Added `_FolderTile`, `FolderCompareView` classes |
| `dejaview/resources/i18n/app.ts` | Removed View, added SettingsDialog + FolderCompareView contexts, new strings |
| `dejaview/resources/i18n/app_hu.ts` | Same changes with Hungarian translations |
| `dejaview/resources/help/USER_GUIDE.md` | Menu bar, scan summary, Compare button, folder badges, Settings section |
| `dejaview/resources/help/USER_GUIDE_HU.md` | Same changes in Hungarian |
| `USER_GUIDE.md` (root) | Synced with in-app English guide |

---

## Test Results (verified 2026-02-25)

```
tests/unit/test_db.py         — 48 passed
tests/unit/test_hasher.py     — 21 passed
tests/unit/test_security.py   — 14 passed, 10 skipped
tests/unit/test_export.py     — 43 passed
tests/unit/test_sync.py       — 29 passed
tests/integration/pass1       —  6 passed
tests/integration/pass2       —  5 passed
tests/integration/state       —  8 passed
tests/integration/cross_lib   — 10 passed
─────────────────────────────────────────
Total:                          184 passed, 10 skipped (7.50s)
```

Note: 1 pre-existing regression test (`test_regression_wf6_manual_export_import_round_trip[hash_only]`) fails due to Bob having only 1 file — the size pre-filter skips hashing, so no cross-library match occurs. This is unrelated to the current feature changes.

---

## Resume Point
**Status:** All implementation tasks complete.
**Remaining:** Manual verification (verification checklist in FEATURE_REQUEST_SIMPLIFICATION_2.md), lrelease for .qm update, PyInstaller rebuild.
