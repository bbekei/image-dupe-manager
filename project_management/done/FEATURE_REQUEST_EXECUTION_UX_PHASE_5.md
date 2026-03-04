# Feature Request Execution: UX Redesign — Phase 5: Advanced Cleanup

## Overview

Advanced Cleanup adds a filtering sidebar, duplicate cluster grouping model, smart selection presets, batch actions, and a statistical header to the cleanup screen. Transforms the local cleanup experience for 100k+ image libraries by enabling SQL-level filtering, hash-grouped cluster views, and one-click selection presets.

## Task Log

### Stage 5: Advanced Cleanup — Filtering, Clusters, Smart Selection

| # | Task | Status | Details |
|---|------|--------|---------|
| 5.1 | DB: Filtered duplicate queries (`data/db.py`) | ✅ Done | `get_filtered_duplicate_groups()` with date range, extension, min copies, sort. `get_cluster_files()` for single hash. `get_full_dupe_folder_paths()` hybrid SQL+Python approach. |
| 5.2 | Smart Selection Engine (`core/selection.py`) | ✅ Done | `SelectionPreset` enum (4 presets), `identify_master_copy()`, `apply_preset()`, `get_master_copies()`. Safety: never marks last copy for deletion. |
| 5.3 | Cluster View Model (`ui/cluster_model.py`) | ✅ Done | Two-level `QAbstractItemModel`: cluster rows (pixel_hash) → file rows. 9 custom data roles. `load_from_db()` with full filter params + search_text. ~380 lines. |
| 5.4 | Filter Sidebar (`ui/filter_sidebar.py`) | ✅ Done | `FilterCriteria` dataclass, date range pickers, file type checkboxes, min copies spinner, sort combo, apply/reset. `filters_changed` signal. ~220 lines. |
| 5.5 | Batch Actions Toolbar (`ui/batch_actions.py`) | ✅ Done | Smart Select button → preset picker dialog. Select by Pattern button → glob pattern matching. `preset_applied` signal. Safety: never deletes last copy. |
| 5.6 | Results Panel & Model Enhancements | ✅ Done | `ROLE_IS_MASTER` role, master badge ("★ MASTER"), view toggle (Tree/Cluster), search bar, stats header, `apply_filter_criteria()`. |
| 5.7 | Cleanup Screen Integration | ✅ Done | 3-pane splitter (FolderPanel | FilterSidebar | ResultsPanel), batch actions toolbar above, filter/preset signal wiring, `toggle_filter_sidebar()`. |
| 5.8 | i18n (EN + HU) | ✅ Done | 4 new contexts: FilterSidebar (~18 strings), ClusterModel (~6 strings), BatchActions (~16 strings), ResultsPanel Phase 5 additions. 269 HU translations compiled. |
| 5.9 | Tests | ✅ Done | 57 new tests across 4 files. See breakdown below. |

## Test Results

```
304 passed, 10 skipped in 7.71s
```

All pre-existing tests (247) continue to pass. 57 new tests added. 10 skips are from `test_security.py` (Phases 4/5 security stubs, pre-existing).

### Test Breakdown

| File | Tests | Coverage |
|------|-------|----------|
| `tests/unit/test_selection.py` | 15 | `identify_master_copy` (6 cases), `apply_preset` (7 cases, all 4 presets), `get_master_copies` (2) |
| `tests/unit/test_cluster_model.py` | 11 | `load_from_db`, `rowCount`, `data()` roles, master copy, multiple groups, waste, search, min_copies, parent, columns, display |
| `tests/unit/test_filter_sidebar.py` | 14 | FilterCriteria defaults/custom/equality (4), `_expand_extensions` (5), widget tests with qtbot (5) |
| `tests/unit/test_db.py` (additions) | 17 | `get_filtered_duplicate_groups` (10), `get_cluster_files` (4), `get_full_dupe_folder_paths` (4) |

## Artifacts

| File | Type | Lines |
|------|------|-------|
| `core/selection.py` | NEW | ~120 |
| `ui/cluster_model.py` | NEW | ~380 |
| `ui/filter_sidebar.py` | NEW | ~220 |
| `ui/batch_actions.py` | NEW | ~150 |
| `data/db.py` | MODIFIED | +130 lines (3 new query methods) |
| `ui/results_model.py` | MODIFIED | +30 lines (ROLE_IS_MASTER, master badge, master tracking) |
| `ui/results_panel.py` | MODIFIED | +120 lines (view toggle, search, stats, cluster model) |
| `ui/cleanup_screen.py` | MODIFIED | +60 lines (filter sidebar, batch actions, signal wiring) |
| `resources/i18n/app.ts` | MODIFIED | +4 contexts (~50 strings) |
| `resources/i18n/app_hu.ts` | MODIFIED | +4 contexts (~50 strings, all translated) |
| `tests/unit/test_selection.py` | NEW | 15 tests |
| `tests/unit/test_cluster_model.py` | NEW | 11 tests |
| `tests/unit/test_filter_sidebar.py` | NEW | 14 tests |
| `tests/unit/test_db.py` | MODIFIED | +17 tests |

## Architecture Decisions

1. **Master Copy metric**: File size (largest = best quality). Adding resolution would cascade through hasher→scanner→DB. Size is a strong proxy; newest `modified_at` as tiebreaker.
2. **Cluster model**: New `QAbstractItemModel` (not proxy). Hash-grouped flat clusters are a fundamentally different data structure from the folder-based tree.
3. **Filter execution**: SQL-level parameterized WHERE clauses. DB returns only matching clusters — no in-memory post-filtering for the main data set.
4. **`get_full_dupe_folder_paths`**: Hybrid SQL+Python approach. SQL fetches duplicate hashes and file paths, Python groups by `pathlib.Path.parent` for cross-platform correctness.
5. **Selection safety**: `apply_preset()` skips groups with < 2 files. Batch pattern matching checks remaining copies before marking for deletion.
