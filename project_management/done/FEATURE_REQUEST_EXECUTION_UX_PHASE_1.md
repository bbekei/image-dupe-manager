# Feature Request Execution: UX Redesign — Phase 1: Navigation Shell & Dashboard

## Overview

Replace the ad-hoc splitter-swap navigation in MainWindow with a structured QStackedWidget + NavigationController. Add a Dashboard as the app's entry point. Extract the existing scan/results flow into a self-contained CleanupScreen container.

## Task Log

### Stage 1: Navigation Shell & Dashboard

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.5 | Update `ui/workflow.py` — Add DASHBOARD, FAMILY_DISCOVERY | ✅ Done | Added two new enum members to `WorkflowPhase` |
| 1.1 | Create `ui/navigation.py` — NavigationController | ✅ Done | QObject wrapping QStackedWidget with back-stack, `register_screen`, `navigate_to`, `go_back`, `screen_changed` signal (~100 lines) |
| 1.6 | Add `db.get_family_treasure_count()` | ✅ Done | SQL: COUNT(DISTINCT remote hashes) NOT IN local active files |
| 1.2 | Create `ui/dashboard.py` — Status cards + sync row | ✅ Done | `_StatusCard` QFrame + `Dashboard` QWidget with 3 cards, sync row, quick actions, `refresh()` from DB (~240 lines) |
| 1.3 | Create `ui/cleanup_screen.py` — Extract scan/results flow | ✅ Done | Self-contained container absorbing FolderPanel + ResultsPanel + panel-swap logic from MainWindow (~280 lines) |
| 1.4 | Refactor `ui/main_window.py` — Thin navigation shell | ✅ Done | Replaced QSplitter central area with NavigationController + QStackedWidget. Registered dashboard + cleanup screens. ScanControl contextual. ~500 lines (down from 886) |
| 1.8 | Write tests — navigation + dashboard + DB | ✅ Done | `test_navigation.py` (14 tests), `test_dashboard.py` (5 DB tests for `get_family_treasure_count`) |
| 1.7 | Add i18n strings (EN + HU) | ✅ Done | Added `Dashboard` context (15 strings) and `CleanupScreen` context (4 strings) to both `app.ts` and `app_hu.ts` |

## Test Results

```
213 passed, 10 skipped in 5.52s
```

All pre-existing tests (196) continue to pass. 17 new tests added (14 navigation + 3 dashboard DB).

## Artifacts

| File | Type | Lines |
|------|------|-------|
| `ui/navigation.py` | NEW | ~100 |
| `ui/dashboard.py` | NEW | ~240 |
| `ui/cleanup_screen.py` | NEW | ~280 |
| `ui/main_window.py` | REWRITTEN | ~500 (was 886) |
| `ui/workflow.py` | MODIFIED | +2 enum members |
| `data/db.py` | MODIFIED | +15 lines (new method) |
| `resources/i18n/app.ts` | MODIFIED | +2 contexts (19 strings) |
| `resources/i18n/app_hu.ts` | MODIFIED | +2 contexts (19 strings) |
| `tests/unit/test_navigation.py` | NEW | 14 tests |
| `tests/unit/test_dashboard.py` | NEW | 5 tests |
