# DejaView — End-to-End Test Plan

**Status:** TODO (implementation not started)
**Last updated:** 2026-02-19

---

## 1. Purpose

This document defines the end-to-end (E2E) test suite for the DejaView application.
E2E tests exercise the **compiled PyInstaller binary** (`dist/DejaView/DejaView.exe`)
by automating it through the Windows UI Automation (UIA) API and asserting outcomes via
the file system and SQLite database. They run after all unit, integration, and UI tests
pass.

---

## 2. Requirements

### 2.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-01 | The build pipeline (lrelease + PyInstaller) must succeed and produce a launchable binary |
| FR-02 | The application window must appear within 5 seconds of launch |
| FR-03 | The UI must display English strings by default |
| FR-04 | The UI must display Hungarian strings when the system locale is `hu_HU` |
| FR-05 | Adding a folder and starting a scan must discover all JPEG/HEIC files in that folder |
| FR-06 | After scanning two identical images, they must appear as a duplicate group in the results tree |
| FR-07 | The "Duplicates Only" filter must hide non-duplicate files from the results tree |
| FR-08 | The "Cross-Library" filter must show only files that match a previously imported peer export |
| FR-09 | Clicking a duplicate group must open the Compare View showing all files in the group |
| FR-10 | Marking a file KEEP must auto-stage DELETE for all other files in the same group |
| FR-11 | Confirming staged DELETE actions must remove files from disk and update DB status to 'deleted' |
| FR-12 | Confirming a staged RENAME action must rename the file on disk and update its path in the DB |
| FR-13 | The "Keep oldest" batch rule must mark the newest files for deletion |
| FR-14 | The "Keep largest" batch rule must mark the smaller files for deletion |
| FR-15 | Pausing a scan must stop file processing and update button state accordingly |
| FR-16 | Resuming a paused scan must continue from where it left off |
| FR-17 | Stopping a scan must mark the session 'stopped'; restarting must create a new session |
| FR-18 | A paused session must be offered for restoration when the app restarts |
| FR-19 | File → Share → Export must produce a valid JSON file at the user-chosen path |
| FR-20 | File → Share → Import must load a peer JSON and enable the Cross-Library filter |
| FR-21 | Removing a peer must clear their files from the Cross-Library filter |
| FR-22 | Changing the scan delay in Settings must persist after app restart |
| FR-23 | Scanning a folder that contains corrupt images must not crash the application |
| FR-24 | Attempting to scan an empty folder must complete without error |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | Each test must be isolated — a separate `APPDATA` directory per test; no shared state |
| NFR-02 | Destructive file operations (delete, rename) are enabled by default in E2E tests |
| NFR-03 | No real Google Drive API calls; Drive sync is excluded from the E2E scope |
| NFR-04 | The compiled binary must be built once per pytest session (not per test) |
| NFR-05 | Each test must terminate the app process within 5 seconds in teardown |
| NFR-06 | Tests must not modify the developer's real `%APPDATA%\DejaView` data |
| NFR-07 | Build tools (`lrelease`, `pyinstaller`) must be on PATH for the suite to run |
| NFR-08 | All E2E tests carry the `@pytest.mark.e2e` marker and run separately from unit tests |

---

## 3. Architecture

### 3.1 Tools

| Tool | Purpose |
|------|---------|
| `pywinauto` (UIA backend) | Locate and click Qt widgets via Windows UI Automation |
| `subprocess` | Launch/terminate the compiled binary |
| `sqlite3` | Open the app DB directly for post-action assertions |
| `Pillow` | Create synthetic JPEG/PNG test images |
| `pytest` | Test runner, fixtures, markers |

### 3.2 Directory Layout

```
dejaview/tests/e2e/
├── __init__.py
├── conftest.py            # session-scoped build fixture + per-test app fixtures
├── test_e2e_build.py      # Phase 0
├── test_e2e_launch.py     # Phase 1
├── test_e2e_scan.py       # Phase 2
├── test_e2e_pause.py      # Phase 3
├── test_e2e_compare.py    # Phase 4
├── test_e2e_filters.py    # Phase 5
├── test_e2e_sharing.py    # Phase 6
└── test_e2e_settings.py   # Phase 7
```

### 3.3 Key Fixtures (conftest.py)

- **`built_binary`** *(session-scoped)*: Runs `lrelease` + `pyinstaller`. Returns path to
  `dist/DejaView/DejaView.exe`. Skips all tests if build tools are not on PATH.
- **`app_env(tmp_path)`** *(function-scoped)*: Creates `<tmp_path>/AppData/` and returns
  `(env_dict, appdata_path)`.
- **`launched_app(built_binary, app_env)`** *(function-scoped)*: Launches the binary with
  injected `APPDATA`, connects pywinauto, yields `(proc, pwa_app, main_win, appdata_path)`,
  then kills the process on teardown.
- **`open_test_db(appdata)`**: Helper function that opens `<appdata>/DejaView/library.db`
  via `sqlite3` and returns a connection for assertions.

### 3.4 Run Commands

```bash
# Step 0: Ensure all unit/integration/UI tests pass
cd "c:\Users\bekei\My Python stuff\image-dupe-manager\dejaview"
python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q

# Step 1: Run the E2E suite (builds binary inside the suite)
python -m pytest tests/e2e/ -v --no-cov

# Step 2: (Optional) Run a single phase
python -m pytest tests/e2e/test_e2e_scan.py -v --no-cov
```

### 3.5 Test Isolation Pattern

```python
# Each test that needs the running app follows this pattern:
proc, app, win, appdata = launched_app  # fixture
# ... interact with UI ...
# ... assert via open_test_db(appdata) or file-system checks ...
```

---

## 4. Phases and Tasks

> **Status key:** `TODO` | `IN PROGRESS` | `DONE` | `SKIP`

---

### Phase 0: Build Pipeline

**Goal:** Verify the build pipeline (lrelease + PyInstaller) succeeds and produces a
working binary.

**File:** `test_e2e_build.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P0-T01 | `lrelease` compiles `app_hu.ts` → `app_hu.qm` without error; output file exists and is non-empty | TODO |
| P0-T02 | `pyinstaller dejaview.spec --noconfirm` completes without error; `dist/DejaView/DejaView.exe` exists | TODO |
| P0-T03 | Binary smoke test: launch binary, assert main window appears within 5 s, then close | TODO |

---

### Phase 1: App Launch & UI Strings

**Goal:** Verify the application starts correctly and renders translated strings.

**File:** `test_e2e_launch.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P1-T01 | App window title is "DejaView" | TODO |
| P1-T02 | English UI: "Add Folder" button / menu item is visible | TODO |
| P1-T03 | Hungarian locale: launch with `LANG=hu_HU` env; "Mappa hozzáadása" (or equivalent translated string) is visible | TODO |

---

### Phase 2: Scan Workflow

**Goal:** Verify the full folder-scan lifecycle from add folder to duplicate detection.

**File:** `test_e2e_scan.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P2-T01 | Add a single folder via "Add Folder" menu; folder path appears in the left panel | TODO |
| P2-T02 | Start scan on a folder containing 2 identical images + 1 unique; progress bar moves; scan completes | TODO |
| P2-T03 | After scan completes: DB `sessions` table has status='complete'; `files` table has 3 rows | TODO |
| P2-T04 | After scan: the results tree shows both duplicate images with a duplicate badge (the unique file has no badge) | TODO |
| P2-T05 | Scan an empty folder: scan completes without crash; session status='complete'; 0 files in DB | TODO |
| P2-T06 | Scan a folder that contains one corrupt JPEG alongside valid images: scan completes; valid images are indexed; corrupt file has no pixel_hash | TODO |

---

### Phase 3: Pause / Resume / Stop

**Goal:** Verify the scanner state machine works end-to-end through the UI buttons.

**File:** `test_e2e_pause.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P3-T01 | Start scan → click Pause → Start button re-enables (shows "Resume"); click Resume → scan completes | TODO |
| P3-T02 | Start scan → click Stop → session status in DB = 'stopped'; Start button re-enables for a new scan | TODO |
| P3-T03 | Create a paused session, close the app, relaunch → a "Resume" prompt / pre-loaded session is offered | TODO |

---

### Phase 4: Compare View & File Actions

**Goal:** Verify the duplicate comparison view and all file action workflows.

**File:** `test_e2e_compare.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P4-T01 | After scanning 2 duplicates, click the duplicate group in results tree → Compare View opens with 2 tiles | TODO |
| P4-T02 | Click KEEP on tile A → tile B is auto-marked DEL; "Review & Confirm" button becomes active | TODO |
| P4-T03 | Click "Review & Confirm" → confirmation dialog lists the DELETE action → click OK → tile B's file is deleted from disk; DB status = 'deleted' | TODO |
| P4-T04 | Rename workflow: click Rename on tile A, enter new filename, confirm → file renamed on disk; DB path updated | TODO |
| P4-T05 | Batch rules "Keep oldest": the newer file is auto-marked DEL after applying | TODO |
| P4-T06 | Batch rules "Keep largest": the smaller file is auto-marked DEL after applying | TODO |
| P4-T07 | Click Close on Compare View → results tree panel is restored (Compare View hidden) | TODO |

---

### Phase 5: Results Filtering

**Goal:** Verify all three filter modes in the results panel.

**File:** `test_e2e_filters.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P5-T01 | "All" filter: tree shows the unique file and the duplicate pair (3 items) | TODO |
| P5-T02 | "Duplicates Only" filter: tree shows only the 2 duplicate files (unique file hidden) | TODO |
| P5-T03 | "Cross-Library" filter: after importing a peer export that matches one local hash, the filter shows exactly those matching files; before import the filter is disabled | TODO |

---

### Phase 6: Export / Import (Manual Sharing)

**Goal:** Verify file-based peer export/import workflows end-to-end.

**File:** `test_e2e_sharing.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P6-T01 | File → Share → Export: username prompt, privacy combo, save-file dialog → JSON file created at chosen path; JSON contains expected `username` and `files` keys | TODO |
| P6-T02 | Export at each privacy level (hash_only, filename, full_path): verify the JSON `files` entries contain the expected fields for that privacy level | TODO |
| P6-T03 | File → Share → Import: select a pre-written peer JSON → "Cross-Library" filter radio button becomes enabled; correct matches visible | TODO |
| P6-T04 | Remove peer via Share → Manage Peers → Remove → Cross-Library filter is disabled (no matches); remote_files rows for that peer are deleted from DB | TODO |

---

### Phase 7: Settings & Configuration

**Goal:** Verify that settings changes persist across application restarts.

**File:** `test_e2e_settings.py`

| Task ID | Description | Status |
|---------|-------------|--------|
| P7-T01 | Open File → Settings, change scan delay to 10 ms, save → close app → relaunch → Settings dialog shows 10 ms | TODO |
| P7-T02 | Open Share → Configure Sync dialog → fields are visible and Save/Cancel buttons work | TODO |

---

## 5. Verification Checklist

Before marking the E2E suite as complete:

- [ ] `python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q` → 288 passed, ≤10 skipped
- [ ] `python -m pytest tests/e2e/ -v --no-cov` → all Phase 0–7 tests pass (or skip with documented reason)
- [ ] No test leaves files in the developer's real `%APPDATA%\DejaView`
- [ ] No test leaves orphaned `DejaView.exe` processes after the session
- [ ] `pywinauto` added to `requirements-dev.txt`
- [ ] `e2e` pytest marker registered in `pytest.ini`

---

## 6. Known Constraints & Decisions

| Topic | Decision |
|-------|----------|
| Google Drive sync | Excluded from E2E scope; covered by unit/integration mocks |
| Test isolation | `APPDATA` env injection; real developer data is never touched |
| Build caching | PyInstaller build is session-scoped; rebuilt only when `--no-cov` E2E session starts |
| Destructive ops | File deletes/renames enabled by default (no env-var gate); test images live in `tmp_path` |
| pywinauto backend | UIA (not `win32`); required for modern Qt6 apps on Windows |
| Locale test (P1-T03) | Sets `LANG` env var; skip if the Qt locale files for `hu` are not bundled |
| Build tools | Skip Phase 0 and raise `pytest.skip` if `lrelease` or `pyinstaller` not on PATH |
