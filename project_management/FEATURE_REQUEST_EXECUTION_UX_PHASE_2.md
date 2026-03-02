# Feature Request Execution: UX Redesign — Phase 2: Soft-Delete & Plan Review

## Overview

Build the safety infrastructure (soft-delete to `.dejaview_trash`) and the Plan Review screen — the "final gate" before any file system changes.

## Task Log

### Stage 2: Soft-Delete & Plan Review

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Create `core/trash.py` — Soft-delete module | ✅ Done | `soft_delete()`, `recover()`, `purge_expired()` — filesystem ops only module (~120 lines) |
| 2.2 | Add `soft_deletes` table + CRUD to `data/db.py` | ✅ Done | DDL + migration + `record_soft_delete`, `record_recovery`, `get_active_soft_deletes`, `get_expired_soft_deletes` |
| 2.3 | Add `db.get_plan_summary()` | ✅ Done | Returns delete_count, delete_bytes, keep_count, ignore_count, folder_delete_count. Also added `get_delete_actions_with_paths()` |
| 2.4 | Create `ui/plan_review.py` — Two-column review screen | ✅ Done | `PlanReviewScreen` with deletion tree (folder-grouped), request placeholder, impact totals, Apply Changes button (~260 lines) |
| 2.5 | Wire PlanningPanel review button → Plan Review | ✅ Done | `review_requested` signal bubbled: PlanningPanel → CleanupScreen → MainWindow → NavigationController |
| 2.6 | Register plan_review screen in MainWindow | ✅ Done | Registered as "plan_review" screen, session_id propagated, back/commit/clear handlers |
| 2.7 | Add i18n strings (EN + HU) | ✅ Done | PlanReviewScreen context (17 strings), MainWindow Phase 2 strings (8 strings), fixed Phase 1 mismatch (`"Google sign-in failed: {0}"`) |
| 2.8 | Write tests — trash + plan review + DB | ✅ Done | `test_trash.py` (12 tests), `test_plan_review.py` (12 tests for DB CRUD + plan summary + delete actions) |

## Test Results

```
237 passed, 10 skipped in 5.61s
```

All pre-existing tests (213) continue to pass. 24 new tests added (12 trash + 12 DB/plan).

## Artifacts

| File | Type | Lines |
|------|------|-------|
| `core/trash.py` | NEW | ~120 |
| `ui/plan_review.py` | NEW | ~260 |
| `data/db.py` | MODIFIED | +95 lines (soft_deletes table, migration, 6 new methods) |
| `ui/cleanup_screen.py` | MODIFIED | +3 lines (review_requested signal + wiring) |
| `ui/main_window.py` | MODIFIED | +30 lines (plan_review registration, 4 nav handlers) |
| `resources/i18n/app.ts` | MODIFIED | +1 context (17 strings), MainWindow fixes |
| `resources/i18n/app_hu.ts` | MODIFIED | +1 context (17 strings), MainWindow fixes |
| `tests/unit/test_trash.py` | NEW | 12 tests |
| `tests/unit/test_plan_review.py` | NEW | 12 tests |

## Notes

- Fixed Phase 1 i18n mismatch: `"Google sign-in failed."` → `"Google sign-in failed: {0}"` (source string changed in Phase 1 rewrite but HU translation was not updated)
- Added missing `"Unknown error"` string to both .ts files
- Also added Phase 1 deferred MainWindow strings: `"Welcome to DejaView."`, `"Family Discovery — coming soon."`, `"Request Approval — coming soon."`, `"Last scan: ..."` variants
