# App Progress Tracker

## Overall: 100% complete (7/7 phases done)

## Phases Checklist

| Phase | Status | Notes/Blockers | Completed By |
|-------|--------|----------------|--------------|
| **1 — Core Engine** | ✅ Done | All 11 tasks complete. 83 unit tests pass (21 hasher + 48 db +14 security). Scanner delivered. | Task #1.1–1.11 |
| **2 — Minimal UI** | ✅ Done | `main.py`, `folder_panel.py`, `scan_control.py`, `main_window.py` verified. 25 UI tests pass. PyQt6 6.7.1 installed. | Task #2.1–2.7 |
| **3 — Results View** | ✅ Done | `results_panel.py` + 17 UI tests. Tree view, filters, badges, 200ms debounce. | Task #3.1–3.4 |
| **4 — Comparison** | ✅ Done | `compare_view.py` (4.1), main_window integration (4.2), 31 UI tests (4.3) | Task #4.1–4.3 |
| **5 — Manual Sharing** | ✅ Done | `export.py`, Cross-Library filter, Share menu, 10 integration + 4 UI tests | Task #5.1–5.7 |
| **6 — Google Drive Sync** | ✅ Done | sync.py, share_dialog.py, main_window wiring, 29+26 tests | Task #6.1–6.5 |
| **7 — Distribution** | ✅ Done | lrelease → app_hu.qm (121 strings), qt_hu.qm bundled, PyInstaller 6.19.0 build (99 MB), Inno Setup .iss, user guides updated | Task #7.1 |

---

## Phase 1: Core Engine — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 1.1 | SQLite schema (`data/db.py`) | ✅ Done | 21 KB — 7 tables + VIEW + 6 indexes, WAL mode, parameterized queries |
| 1.2 | Pixel-hash + thumbnail (`core/hasher.py`) | ✅ Done | 3 KB — `exif_transpose → RGB → sha256`, `HashError`, idempotent thumbnails |
| 1.3 | Qt Linguist i18n setup | ✅ Done | `app.ts` (en) + `app_hu.ts` (hu) — 17 UI strings, 4 Qt contexts |
| 1.4 | Test infrastructure | ✅ Done | `conftest.py` (6.5 KB), `pytest.ini`, `.coveragerc`, requirements files |
| 1.5 | Unit tests — hasher | ✅ Done | 21 tests (14 KB) — hash pipeline, EXIF, thumbnails, error handling |
| 1.6 | Unit tests — db | ✅ Done | 48 tests (19 KB) — schema, CRUD, views, actions, sharing tables |
| 1.7 | Two-pass QThread scanner (`core/scanner.py`) | ✅ Done | 12 KB — Pass 1 discovery, Pass 2 hashing, symlink/junction guard, network probe |
| 1.8 | Integration tests — Pass 1 | ✅ Done | 6 tests (6.8 KB) — file insertion, path/size, symlink, signal ordering |
| 1.9 | Integration tests — Pass 2 | ✅ Done | 5 tests (6.6 KB) — size-filter, duplicate signals, thumbnails, progress |
| 1.10 | Integration tests — state machine | ✅ Done | 8 tests (9.6 KB) — pause/resume/stop/crash recovery |
| 1.11 | Security unit tests | ✅ Done | 14 active tests (13 KB) — symlink, SQL injection, hash validation |

### Fixture Images (8 files committed to VCS)

`gray_rgb.jpg`, `gray_rgba.png`, `gray_l.png`, `gray_exif_rot90.jpg`, `blue_rgb.jpg`, `pattern_rgb.jpg`, `pattern_exif_rot90.jpg`, `corrupt.jpg`

---

## Phase 2: Minimal UI — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 2.1 | Entry point (`main.py`) | ✅ Done | 108 LOC — locale load, DB init, sync stub |
| 2.2 | Main window (`ui/main_window.py`) | ✅ Done | 242 LOC — menu, toolbar, layout, sync lifecycle hooks |
| 2.3 | Folder panel (`ui/folder_panel.py`) | ✅ Done | 140 LOC — add/remove/browse scan folders |
| 2.4 | Scan control (`ui/scan_control.py`) | ✅ Done | 131 LOC — progress bar, pause/resume/stop |
| 2.5 | UI tests — folder panel | ✅ Done | 10 tests (111 LOC) |
| 2.6 | UI tests — scan control | ✅ Done | 15 tests (133 LOC) |
| 2.7 | Verify all tests pass with PyQt6 | ✅ Done | PyQt6 6.7.1 installed; 127 passed, 11 skipped |

### Bugs Fixed During Verification

- **Windows junction guard** — `os.path.islink()` does NOT detect `mklink /J` junctions on Windows. Added `_is_symlink_or_junction()` helper in `scanner.py` that checks `FILE_ATTRIBUTE_REPARSE_POINT` flag via `os.lstat()`.
- **Pass 1 test isolation** — `test_discovery_pass_inserts_all_files` created 5 same-size files, causing Pass 2 to hash them. Fixed by giving each file unique dimensions.
- **Stop/pause signal exclusivity** — `scan_stopped`/`scan_paused` and `scan_complete` are mutually exclusive. Fixed 3 tests that incorrectly used `waitSignals` expecting both.

---

## Phase 3: Results View — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 3.1 | `ui/results_panel.py` — tree model + filters + badges + debounce | ✅ Done | 310 LOC — QStandardItemModel, _DuplicateFilterProxy, 200ms QTimer debounce |
| 3.2 | Integrate into `main_window.py` + wire scanner signals | ✅ Done | Replaced placeholder label; wired file_discovered, hash_complete, duplicate_found |
| 3.3 | `tests/ui/test_results_panel.py` | ✅ Done | 17 tests — filters, badges, debounce, compare_view signal, tree structure |
| 3.4 | Verify all tests pass | ✅ Done | 144 passed, 11 skipped (3.98s) |

---

## Phase 4: Comparison — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 4.1 | `ui/compare_view.py` — full widget | ✅ Done | ~420 LOC — `_FileTile`, `CompareView`, `_BatchRulesDialog`, `_ConfirmDialog`, rename validation, path scope check, orphan cleanup |
| 4.2 | Integrate into `main_window.py` | ✅ Done | ~35 LOC diff — `_on_compare_requested`, `_on_actions_confirmed`, `_close_compare_view`; splitter swap pattern |
| 4.3 | `tests/ui/test_compare_view.py` + verify | ✅ Done | 31 tests — tiles, local/remote buttons, KEEP/DEL staging, batch rules, rename validation, confirmation, path scope, signals |

### Phase 4.1 Deliverables (compare_view.py)

| Component | Description |
|-----------|-------------|
| `_FileTile` | Per-file tile: 240×240 thumbnail, path/size/date labels, KEEP/DEL/Rename buttons (local) or peer label + read-only badge (remote) |
| `_validate_rename()` | Regex `^[^\\/:*?"<>\|.][^\\/:*?"<>\|]{0,253}$` — rejects path separators, leading dots, empty, >255 chars (plan §Security) |
| `CompareView` | Scrollable horizontal tile layout, header with file count + SHA prefix, group-level actions |
| `_on_keep` / `_on_delete` | Per-file staging via `db.stage_action()` with visual tile marking |
| `_on_rename` | Inline rename field → validate → stage with detail=new_name |
| `_on_apply_all` | Applies current KEEP/DEL markings across all tiles |
| `_on_batch_rules` | Opens `_BatchRulesDialog` — keep_oldest / keep_largest |
| `_on_confirm` | Opens `_ConfirmDialog` listing all staged actions → executes: `os.remove()` / `os.rename()` / DB updates |
| `_execute_actions` | Path scope validation, file ops, status updates, orphan thumbnail cleanup, error collection |
| `_path_within_scope` | Resolved-path check against session_folders roots (plan §Security — confirmed-delete path validation) |
| `actions_confirmed` signal | Emitted after confirmation so ResultsPanel can refresh |
| `closed` signal | Emitted on Close button so MainWindow can restore results view |

---

## Phase 5: Manual Sharing — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 5.1 | `data/export.py` — build_export_payload + import_payload | ✅ Done | ~200 LOC — privacy levels, username validation, security guards (10MB, 100k, hash validation, field truncation) |
| 5.2 | `tests/unit/test_export.py` | ✅ Done | 43 tests — username validation, privacy levels, round-trip, security guards, idempotency |
| 5.3 | Enable Cross-Library filter in `results_panel.py` | ✅ Done | ~50 LOC diff — `ROLE_IS_CROSS_LIBRARY`, `_cross_library_hashes` cache, filter logic, `update_cross_library_data()`, auto-enable radio |
| 5.4 | Wire Share menu (Export/Import) in `main_window.py` | ✅ Done | ~100 LOC diff — `_on_export()` (username prompt, privacy, save dialog), `_on_import()` (file read, import_payload, refresh) |
| 5.5 | `tests/integration/test_cross_library.py` | ✅ Done | 10 tests — export→import→match, hash_only privacy, no-match, multiple peers, remove peer, round-trip all privacy levels |
| 5.6 | Update results_panel UI tests for Cross-Library filter | ✅ Done | 4 new tests — radio enabled/disabled, filter shows only matches, update_cross_library_data() refresh |
| 5.7 | Verify all tests pass | ✅ Done | 232 passed, 11 skipped (6.89s) |

### Bug Fixed During Phase 5

- **`upsert_sync_config` NOT NULL crash** — `INSERT ... ON CONFLICT` with partial columns violated `local_username NOT NULL` even when the row already existed (SQLite validates constraints before ON CONFLICT). Fixed to use `UPDATE` when row exists, `INSERT` only for new rows.

---

## Phase 6: Google Drive Sync — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 6.1 | `data/sync.py` — DriveSync class | ✅ Done | ~290 LOC — OAuth2 desktop flow, upload (create/update), download peers (skip unchanged), full sync cycle, offline fallback, credential security (0o600), folder ID validation |
| 6.2 | `tests/unit/test_sync.py` | ✅ Done | 29 tests — folder ID validation, credentials, upload (update/create), download (skip unchanged/import changed), offline fallback, pending export, remove peer. Unskipped credential security test. |
| 6.3 | `ui/share_dialog.py` | ✅ Done | ~230 LOC — Configure Sync dialog: identity, sign-in, folder ID validation, privacy combo, peer list with remove, Sync Now, Save/Cancel; 26 UI tests |
| 6.4 | Wire sync into `main_window.py` + `main.py` | ✅ Done | ~130 LOC diff — DriveSync ctor param, _SyncWorker QThread, sync_on_start(), Configure Sync menu → ShareDialog, sign-in/peer-remove/sync-now slots, closeEvent final upload, i18n strings |
| 6.5 | Verify all tests pass | ✅ Done | 288 passed, 10 skipped (8.40s) — fixed flaky pause test (added scanner.wait()) |

### Phase 6.1 Deliverables (data/sync.py)

| Component | Description |
|-----------|-------------|
| `validate_folder_id()` | Regex `^[A-Za-z0-9_-]{25,50}$` (plan §Security — Drive folder ID validation) |
| `save_credentials()` | `os.open(..., 0o600)` before writing (plan §Security — OAuth2 token file creation) |
| `load_credentials()` | Reads token file via `Credentials.from_authorized_user_file()` |
| `DriveSync.__init__` | Accepts db, creds path, secrets path, optional service injection (testable) |
| `DriveSync.authenticate()` | Full OAuth2 desktop flow: load → refresh → InstalledAppFlow fallback |
| `DriveSync.upload()` | `files().update()` if gdrive_file_id exists, else `files().create()`; sets pending_export on failure |
| `DriveSync.download_peers()` | Lists JSON in shared folder, skips unchanged (file_mtime), imports via `import_payload()` |
| `DriveSync.sync()` | Full cycle: download → upload; catches all exceptions, never propagates |
| `DriveSync.remove_peer()` | Delegates to `db.delete_remote_peer()` (CASCADE clears remote_files) |

---

## Phase 7: Distribution — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 7.1 | lrelease → app_hu.qm | ✅ Done | 121 translations compiled (12.4 KB); previous .qm was stale (1.3 KB) |
| 7.2 | qt_hu.qm bundling | ✅ Done | Located at `PyQt6/Qt6/translations/qt_hu.qm`; bundled via .spec datas |
| 7.3 | PyInstaller frozen-mode support | ✅ Done | `_base_dir()` helper in main.py; `sys._MEIPASS` for translations + client_secrets |
| 7.4 | PyInstaller .spec file | ✅ Done | `dejaview.spec` — one-folder bundle, GUI mode, excludes test/science deps |
| 7.5 | PyInstaller build verified | ✅ Done | 99 MB dist/DejaView/ — both .qm files in _internal/resources/i18n/ |
| 7.6 | Inno Setup .iss script | ✅ Done | `installer.iss` — English + Hungarian, Win 10+, lowest privileges, desktop icon |
| 7.7 | User guides updated | ✅ Done | Installation + uninstall sections added to USER_GUIDE.md and USER_GUIDE_HU.md |

### Build Commands

```bash
# 1. Recompile Hungarian translations (if .ts changed)
lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm

# 2. Build with PyInstaller
cd dejaview
pyinstaller dejaview.spec --noconfirm

# 3. Build installer (requires Inno Setup 6)
iscc installer.iss
# Output: installer/DejaView_Setup.exe
```

### Notes

- Google API hidden imports warn at build time if google-api-python-client is not installed — harmless for builds without Drive sync
- `client_secrets.json` not yet created (requires Google Cloud Console project) — uncomment line in .spec when ready
- App icon (.ico) not yet created — uncomment icon lines in .spec and .iss when ready
- Code signing (plan §Distribution security) requires a certificate — add signtool step to build pipeline

---

## Pending Next

All 7 phases complete. Remaining optional items:
- Create app icon (`.ico`) for installer and taskbar
- Create `client_secrets.json` via Google Cloud Console
- Code-sign the installer with signtool.exe
- Set up CI/CD pipeline (GitHub Actions)

## Local Commands

```bash
# View this file
cat EXECUTION.md

# Run all tests (requires PyQt6)
cd dejaview && python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q

# Run unit tests only (fast)
cd dejaview && python -m pytest tests/unit/ --no-cov -q

# Resume with
CONTINUE
```

---

## Key Technical Decisions

- **Two-pass with size pre-filter** — `get_unhashed_files_grouped_by_size()` in `db.py` eliminates 70–90% of Pillow decode operations on typical photo libraries
- **Batch inserts in Pass 1** — `insert_files_batch()` commits in chunks of 100 rows
- **WAL mode** — concurrent UI reads during scanner writes
- **`HashError` wraps all Pillow exceptions** — scanner catches per-file and continues
- **`_is_symlink_or_junction()` helper** — checks both `os.path.islink()` and `FILE_ATTRIBUTE_REPARSE_POINT` for Windows junction detection
- **`validate_pixel_hash()` regex** — `^[0-9a-f]{64}$` — enforced before every `remote_files` insert
- **PyQt6 6.7.1** — PyQt6 6.10.x DLL load fails on Anaconda Python 3.12; pinned to 6.7.1

---

## Test Results (verified 2026-02-18, Phase 6 complete)

```
tests/unit/test_db.py         — 48 passed
tests/unit/test_hasher.py     — 21 passed
tests/unit/test_security.py   — 14 passed, 10 skipped (future phases)
tests/unit/test_export.py     — 43 passed
tests/unit/test_sync.py       — 29 passed
tests/integration/pass1       —  6 passed
tests/integration/pass2       —  5 passed
tests/integration/state       —  8 passed
tests/integration/cross_lib   — 10 passed
tests/ui/folder_panel         — 10 passed
tests/ui/scan_control         — 15 passed
tests/ui/results_panel        — 21 passed
tests/ui/compare_view         — 31 passed
tests/ui/share_dialog         — 26 passed
─────────────────────────────────────────
Total:                          288 passed, 10 skipped (8.40s)
```

---

## Progress Update
```diff
- Overall: 86% complete (6/7 phases done)
+ Overall: 100% complete (7/7 phases done — ALL PHASES COMPLETE!)
+ Phase 7: ✅ Done — lrelease (121 strings), PyInstaller (99 MB), Inno Setup .iss, user guides
+ New files: dejaview.spec, installer.iss
+ Modified: main.py (_base_dir() for frozen mode), USER_GUIDE.md, USER_GUIDE_HU.md
+ Pending: Optional — app icon, client_secrets.json, code signing, CI/CD
```
