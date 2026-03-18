# DejaView — Manual Verification Log

**Last updated:** 2026-03-17
**Environment:** Linux/WSL2 · Tauri v2 · Python sidecar · WebKitGTK

---

## Status Legend
| Symbol | Meaning |
|--------|---------|
| ✅ | Verified passing |
| 🔧 | Fix applied, not yet re-verified |
| ⬜ | Not yet tested |
| ❌ | Failing |

---

## Acceptance Criteria

| AC | Description | Status | Notes |
|----|-------------|--------|-------|
| AC-04 | Pause / Resume / Stop a running scan | ✅ | All three verified. See fixes below. |
| AC-41 | Browse duplicate groups, view thumbnails, set file actions, auto-keep | ✅ | Pass. Similarity action persistence fix applied mid-session. |
| AC-11 | Plan review → Execute → files move to bin | ✅ | Pass. |
| AC-46 | Bin restore / permanent delete / purge expired | ✅ | Pass. |
| AC-23 | Settings config round-trip (save + reload) | ✅ | Language persists. Theme persists (visual switching fix applied F18). Google login fails — needs `resources/client_secrets.json` from Google Cloud Console. |
| — | MigrationGate — Cancel path on migration dialog | ⬜ | Not yet tested. |
| — | Virtualised list — performance with large group set | ⬜ | Not yet tested. |
| — | Bin thumbnail toggle (new feature) | 🔧 | Just implemented, not yet verified. |

---

## Fixes Applied This Session

### Session 1 (previous) — Core scan flow
| # | File(s) | Fix |
|---|---------|-----|
| F1 | `frontend/src/hooks/usePyBridge.ts` | Added `camelizeKeys()` in `callBackend` — Tauri v2 silently drops params unless keys are camelCase. |
| F2 | `frontend/src/screens/Dashboard.tsx` | `handleStartScan` now calls single `select_and_start_scan` command — avoids GTK IPC drop after blocking folder dialog. |
| F3 | `frontend/vite.config.ts` | Added `usePolling: true, interval: 500` — inotify unreliable on WSL2 NTFS mounts. |
| F4 | `src-tauri/src/commands.rs` | Added `select_and_start_scan` command (combines async folder picker + sidecar call). |

### Session 2 (this session) — Scan state machine + UI

| # | File(s) | Fix |
|---|---------|-----|
| F5 | `data/db.py` — `create_session` | Now stores `similarity_enabled` column. Was always 0. |
| F6 | `backend/api.py` — `start_scan` | Passes `enable_similarity` to `create_session`. |
| F7 | `backend/api.py` — `resume_scan` | Reads `similarity_enabled` from DB session record and passes to new Scanner. Root cause of "resume immediately completes" — Pass 3 was always skipped on resume. |
| F8 | `core/scanner.py` — `_run_pass2` | Flushes `pending_updates` to DB before breaking on pause/stop, preventing hash loss. |
| F9 | `backend/api.py` — `stop_scan` | Handles dead scanner thread (paused state) by updating DB and emitting event directly. Previously stop did nothing when paused. |
| F10 | `core/scanner.py` — `_run_pass1` | Added `stop_requested` check at top of outer `for folder` loop. Previously only inner loops checked, so stop during discovery with multiple folders was ignored. |
| F11 | `core/scanner.py` — `_run_pass2` | Progress now starts from already-hashed count on resume instead of 0/remaining. Queries total candidate count and sets `current = total - remaining`. |
| F12 | `core/scanner.py` — `_run_pass3` | Same progress continuity fix as F11 for similarity hashing phase. |
| F13 | `frontend/src/screens/Dashboard.tsx` | Pause button hidden when `phase === 'paused'`; Stop button always shown when `isActive`. |
| F14 | `frontend/src/index.css` | Added `color-scheme: dark` to `:root` — native `<select>` dropdowns (CriteriaBuilder, Settings) now render with dark theme in WebKit. |
| F15 | `backend/api.py` — `get_similarity_group_detail` | Now populates `action` per member (mirroring `get_group_detail`). Root cause of "similarity actions not persisted": every `loadDetail` call reset local `fileActions` to `{}` because the API returned no action data, and re-clicking would toggle/clear the DB action. |
| F16 | `backend/api.py` — `get_bin_items` | Embeds `thumbnail_data` (base64) per item by joining with `files.thumbnail_path`. |
| F17 | `frontend/src/screens/DuplicatesBin.tsx` | Added "Thumbnails" toggle button; shows 48×48 px thumb inline when active. |
| F18 | `frontend/src/index.css`, `App.tsx`, `Settings.tsx`, `Layout.tsx` | Theme switching now works. Added `[data-theme="light"]` CSS overrides, `applyTheme()` function called on startup and on settings change, Toaster theme is reactive. |
| F19 | `tests/integration/test_scanner_pass3.py` | Updated `test_pass3_resume_skips_already_hashed` assertion to match F12 progress continuity change (total=N, current=N on full resume, not total=0). |
| F20 | `backend/api.py`, `frontend/src/screens/Execution.tsx` | Exec progress: log/stage events no longer overwrite current/total with 0. Frontend only updates counters when present in payload. Fixes "0 files processed" display. |
| F21 | `frontend/src/screens/PlanReview.tsx` | Execute button disabled when `delete_count === 0`. Prevents empty plan execution. |

---

## Remaining Work

### AC-23 — Settings Config Round-Trip ✅
- Language: persists across reload
- Theme: persists and now visually applies (F18)
- Google login: fails with missing `client_secrets.json` — this is expected until a Google Cloud OAuth client is configured. Place the file at `resources/client_secrets.json`.

### MigrationGate — Cancel Path
- Trigger migration dialog (downgrade DB schema version or run against an older DB)
- Click Cancel
- Verify app gracefully handles cancel (no crash, no partial migration)
- Verify backup file is present at the path shown

### Virtualised List — Large Group Set
- Scan a folder with thousands of duplicates (or mock large dataset)
- Browse duplicate/similarity list
- Verify scrolling is smooth and memory doesn't spike
- Check that virtual scroll loads pages correctly (PAGE_SIZE = 200 in SimilarityReview, see `loadSummaryPage`)

### Bin Thumbnail Toggle (F16/F17)
- Execute a plan so files land in the bin
- Open Duplicates Bin
- Click "Thumbnails" toggle — each row should show a 48×48 thumbnail
- Toggle off — thumbnails hide, row height returns to compact
- Verify items with no thumbnail show the placeholder icon

---

## Known Bugs / Deferred Fixes

| # | Screen | Description |
|---|--------|-------------|
| B1 | Plan Review | After a plan executes successfully, the plan screen still shows the "kept" files. The executed delete actions are correctly cleared, but keep/ignore actions remain, giving the false impression that the plan is not finished. Expected: plan should be fully empty after execution — all actions (keep, delete, ignore) should be cleared. Fix: call `clear_all_actions(session_id)` after `execute_plan` completes, or filter out non-delete actions from the post-execution plan view. |

---

## Known Architecture Notes (for context)
- **Tauri v2 camelCase:** All Rust command param names are camelCase in the JS IPC API. `callBackend` calls `camelizeKeys(params)` before `invoke`. Do NOT use `rename_all = "snake_case"` on command macros.
- **WSL2 Vite polling:** `vite.config.ts` must keep `server.watch.usePolling: true`. Kill old Vite process before restarting `cargo tauri dev`.
- **GTK IPC after dialog:** On Linux/WebKitGTK, `invoke()` silently drops after `pick_folders()` closes. Always use the combined `select_and_start_scan` command — never two separate IPC hops.
- **Log files:** Tauri app → `/home/vscode/.local/share/com.dejaview.app/logs/DejaView.log` · Sidecar → `/home/vscode/AppData/Roaming/DejaView/dejaview-sidecar.log`
- **Only sidecar restart needed** for Python changes (db.py, api.py, scanner.py, sidecar_main.py). Full `cargo tauri dev` rebuild only needed for Rust changes.
