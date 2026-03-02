# Feature Request Execution: UX Redesign — Phase 3: Execution Screen & File Ops

## Overview

Implement the Execution screen (Screen 5) and the file operations engine that performs soft-deletes, completing the local cleanup end-to-end pipeline: Scan → Plan → Review → Execute → Dashboard.

## Task Log

### Stage 3: Execution Screen & File Operations Engine

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Add `db.mark_file_action_executed()` to `data/db.py` | ✅ Done | Single UPDATE query setting `executed_at` on `file_actions` |
| 3.2 | Create `core/executor.py` — PlanExecutor QThread | ✅ Done | Two-stage executor: Stage A (soft-delete loop) + Stage B (cloud sync). Follows Scanner signal pattern (~130 lines) |
| 3.3 | Create `ui/execution_screen.py` — Progress + log | ✅ Done | Two progress bars (Local Cleanup + Cloud Sync), collapsible log, ETA timer, Done button (~300 lines) |
| 3.4 | Create `ui/tray.py` — System tray icon | ✅ Done | Minimal QSystemTrayIcon with `show_progress()` and `notify_complete()` (~40 lines) |
| 3.5 | Wire Plan Review → Execution in `main_window.py` | ✅ Done | Confirmation dialog, executor creation, signal wiring, tray integration, closeEvent cleanup |
| 3.6 | Add startup trash purge in `main.py` | ✅ Done | `_startup_trash_purge()` calls `trash.purge_expired()` at app launch |
| 3.7 | Add i18n strings (EN + HU) | ✅ Done | New `ExecutionScreen` context (19 strings) + 5 MainWindow Phase 3 strings. Removed old Phase 3 placeholder. Recompiled with lrelease. |
| 3.8 | Write tests — `test_executor.py` | ✅ Done | 10 tests: DB method (2) + executor flow (8) — empty plan, delete, executed_at, soft_deletes, file status, missing files, stop, plan summary |

## Test Results

```
247 passed, 10 skipped in 5.79s
```

All pre-existing tests (237) continue to pass. 10 new tests added.

## Artifacts

| File | Type | Lines |
|------|------|-------|
| `core/executor.py` | NEW | ~130 |
| `ui/execution_screen.py` | NEW | ~300 |
| `ui/tray.py` | NEW | ~40 |
| `data/db.py` | MODIFIED | +12 lines (`mark_file_action_executed`) |
| `ui/main_window.py` | MODIFIED | +80 lines (execution wiring, tray, confirmation dialog) |
| `main.py` | MODIFIED | +12 lines (startup trash purge) |
| `resources/i18n/app.ts` | MODIFIED | +1 context (19 strings), MainWindow Phase 3 strings |
| `resources/i18n/app_hu.ts` | MODIFIED | +1 context (19 strings), MainWindow Phase 3 strings |
| `tests/unit/test_executor.py` | NEW | 10 tests |

## Notes

- Removed the old Phase 3 placeholder string `"Execution engine — coming in Phase 3."` from MainWindow
- PlanExecutor runs synchronously in tests (calling `run()` directly, no QThread event loop needed)
- Executor handles per-file errors non-fatally: emits `execution_error` and continues
- Cloud Sync (Stage B) is optional: only runs if `drive_sync` is provided and sync is enabled
