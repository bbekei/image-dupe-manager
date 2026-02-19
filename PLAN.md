# DejaView Home Photo Manager — Project Plan

## Overview

A Windows desktop application that scans folders for duplicate images based on
visual content, and allows users to review and manage those duplicates. Scan
results are synchronized between trusted users (e.g. family members) via Google
Drive to find duplicate storage across multiple libraries.

---

## User Experience

### First Launch

The user installs the app and opens it for the first time. The window is empty: no folders, no results. The interface is split into two panes — a narrow folder panel on the left and a large results area on the right — with a scan control bar at the bottom. The app auto-detects the system language and displays in Hungarian or English accordingly.

A short status bar message reads "Add folders to get started." No dialogs appear automatically.

---

### Workflow 1: Scanning a Photo Library

**Step 1 — Add folders**

The user clicks **+ Add...** in the folder panel (or uses File > Add Folder). A standard Windows folder browser opens. The user selects a folder (e.g. `C:\Photos`). It appears in the folder list with a folder icon. They can add more folders from different drives, including network shares (`Z:\Family`). Folders can be removed individually.

**Step 2 — Start the scan**

The user clicks **▶ Start** in the scan control bar at the bottom. The scan runs in two passes:

1. **Discovery pass** — the app walks all folders and records every file's path and size. The results tree populates immediately with all discovered files (no badges yet). The progress bar shows `Discovering files...`.
2. **Hash pass** — only files that share a size with at least one other file are pixel-hashed. As files are hashed, duplicate badges appear in the tree in real time. The progress bar shows `0 / N` files and a percentage for this pass.

Each file in the tree shows:
- Filename
- A **● DUPLICATE** badge if it shares its visual content with another file in the scan
- No badge if it is unique or has not yet been hashed

**Step 3 — Pause and resume**

The user can click **⏸ Pause** at any time. The current file finishes hashing, then the scan stops. The progress bar freezes. The badge **PAUSED** appears next to the progress counter. The app can be closed — scan progress is saved to disk. On next open, the user clicks **▶ Resume** and scanning continues from where it left off. Files already hashed are not re-processed.

**Step 4 — Stop**

Clicking **⏹ Stop** ends the scan permanently. Partial results remain visible and actionable. The session is marked complete up to the point it was stopped.

---

### Workflow 2: Reviewing Duplicates

**The results panel** shows the folder tree of all scanned files. The filter bar above the tree offers four views:

| Filter | Shows |
|--------|-------|
| **All** | Every file discovered in the scan scope, whether hashed or not |
| **Duplicates Only** | Only files that have at least one local duplicate |
| **Cross-Library** | Files that match entries in a trusted user's synced library |

Selecting **Duplicates Only** collapses the tree to show only the affected files. Files are still shown in their original folder context.

**Clicking a file** (or a duplicate badge) with a known duplicate opens the **Compare View**.

---

### Workflow 3: Comparing and Acting on Duplicates

The Compare View opens as a panel or modal showing all files that share the same visual content, laid out side by side:

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   [image]    │   │   [image]    │   │   [image]    │
│ C:\Photos\   │   │ Z:\Family\   │   │ D:\Backup\   │
│ beach.jpg    │   │ photo.jpg    │   │ img0041.jpg  │
│ 2.1 MB       │   │ 1.8 MB       │   │ 2.1 MB       │
│ 2023-06-15   │   │ 2023-07-30   │   │ 2023-06-15   │
│ [KEEP] [DEL] │   │ [KEEP] [DEL] │   │ [KEEP] [DEL] │
└──────────────┘   └──────────────┘   └──────────────┘
[Apply to all in group]    [Batch rules...]
```

Images are shown as 400×400 thumbnails (pre-generated at scan time, so the view opens instantly). Metadata — file path, size, modification date — is shown under each image.

**Per-file actions (inline buttons on each tile):**
- **KEEP** — mark this copy as the one to retain; the others in the group are implicitly candidates for deletion
- **DEL** (Delete) — mark this copy for deletion
- **Rename** — opens an inline text field on the tile to rename the file in place

**Group-level actions:**
- **Apply to all in group** — apply the current KEEP/DEL marking across all files in the group at once
- **Batch rules...** — open a dialog to apply a rule automatically, e.g.:
  - Keep the oldest file (by modification date), delete the rest
  - Keep the largest file (highest file size), delete the rest
  - Keep the file in a specific folder, delete copies elsewhere

**Actions are staged, not immediate.** The user marks files across multiple groups, then reviews the full list of pending actions before confirming. A confirmation dialog lists all files to be deleted before any disk operation occurs.

---

### Workflow 4: Cross-Library Duplicates (Shared Libraries)

When a trusted user's library has been synced (see Workflow 5), the **Cross-Library** filter becomes active. It shows files on the local machine that match files in another user's library.

The compare view for a cross-library group distinguishes local from remote tiles:

```
┌──────────────┐   ┌──────────────┐
│   [image]    │   │   [image]    │
│ C:\Photos\   │   │ Alice's copy │
│ beach.jpg    │   │ vacation_    │
│ 2.1 MB       │   │ beach.jpg    │
│ 2023-06-15   │   │ 2.1 MB       │
│ [KEEP] [DEL] │   │ (read only)  │
└──────────────┘   └──────────────┘
```

- **Local tiles** have the full action buttons (KEEP / DEL / RENAME)
- **Remote tiles** are informational only — no action buttons, labeled with the peer's display name
- The user can decide to keep or delete their own copy; they cannot affect the other user's files

---

### Workflow 5: Setting Up Library Sync

**First-time sync setup** (one user does this once):

1. Open **Share > Configure Sync...**
2. Enter a display name (e.g. `alice`) — this becomes the filename in the shared folder
3. Click **Sign in with Google** — a browser window opens for Google account authorization; the app requests only access to files it creates (not the user's full Drive)
4. **Outside the app**: in Google Drive's web interface, create a shared folder and share it with trusted users (the dialog shows a link to drive.google.com and brief instructions for this step)
5. Paste the folder URL or ID into the app
6. Choose a privacy level — **Filename only** (default), **Hash only**, or **Full path**. This setting applies to all exports: both automatic Drive sync and manual JSON export
7. Click **Save**

All other trusted users repeat steps 2–6 with their own display name, pointing at the same shared folder.

**Ongoing sync:**

- On app start: the app silently downloads other users' exports in the background and updates the Cross-Library view
- After a scan completes: the app uploads the updated export automatically
- On app close: a final export upload runs
- The status bar shows a sync indicator: `↕ Syncing...` while in progress, `✓ Synced 2 min ago` when idle

**If Drive is unavailable** (offline, not signed in):
- The status bar shows `⚠ Sync unavailable — showing last known data`
- The Cross-Library view still shows results from the last successful sync
- The pending export is queued and sent at the next successful sync

**Manage peers**: Share > Manage Synced Libraries lists all imported users. Any user can be removed, which clears their data from the local database.

---

### Workflow 6: Manual Export / Import (Fallback)

For users who do not use Google Drive sync, the app supports manual sharing:

1. **Export**: Share > Export Scan Results... — enter a display name, save to a `.json` file. The export uses the privacy level configured in Share > Configure Sync (defaulting to **Filename only**). Send the file via email or USB.
2. **Import**: Share > Import Scan Results... — open a `.json` file from another user. The app imports the hashes and immediately shows cross-library matches in the Cross-Library filter.

---

### Language / Localization

The app auto-detects the Windows system language on first launch. Hungarian (`hu`) and English (`en`) are supported. The language can be changed in File > Settings > Language without restarting the app.

All UI text is localized: menus, buttons, dialogs, status messages, filter labels. Internal data (database field values, JSON keys, log messages) always stays in English regardless of UI language.

---

## Requirements

### Platform
- **OS:** Windows (10/11)
- **Distribution:** Installer package (Inno Setup)

### Supported Image Formats
- **Scanner discovery is limited to formats produced by digital cameras:** `.jpg`, `.jpeg`, `.heic`, `.heif`
- These cover DSLR/mirrorless (JPEG), iPhone (HEIC default, JPEG compatibility), and Android (JPEG default, HEIC on newer devices)
- Other formats (PNG, GIF, BMP, TIFF, WebP, AVIF) are intentionally excluded — they are not standard camera output formats

### Duplicate Detection
- Exact content match, regardless of filename or metadata
- Method: decode image pixels → normalize color space → SHA-256 hash of raw pixel data
- Normalization: `image.convert("RGB")` + `ImageOps.exif_transpose()` before hashing
- Handles re-saved copies, renamed files, different EXIF data

### Image Library Scale
- Several thousand images
- Storage: local drives or network-mounted drives (Windows drive letters / UNC paths)
- No custom network access handling — relies on Windows-accessible paths

### User Features

| # | Feature |
|---|---------|
| 4.1 | Browse, select, and add folders to the scan scope |
| 4.2 | Pause, resume, or stop the scanning process |
| 4.3 | View results in original directory tree, with filters: All / Duplicates Only / Cross-Library |
| 4.4 | Visual side-by-side comparison of duplicate groups before taking action |
| 4.5 | Actions: delete, rename, keep, or apply batch rules (keep oldest / keep largest); actions are staged and reviewed before any disk operation |
| 4.6 | Hungarian (hu) and English (en) UI language, auto-detected from system locale |

### Sharing
- Sync scan results with trusted users via a shared Google Drive folder
- Each user writes their own `{username}.json` export; reads others' exports
- Cross-library duplicates automatically detected and shown in a dedicated filter
- No custom server infrastructure — Google Drive is the transport layer
- Manual JSON export/import also supported as a fallback

### Post-Action Cleanup

After the user confirms staged actions (individually or as a batch), the app must bring the database and thumbnail cache back into a consistent, minimal state:

**Database cleanup:**
- Confirming a **delete** action sets `files.status = 'deleted'` for the affected row; the `duplicate_groups` view immediately reflects the change because it filters on `status = 'active'`
- Confirming a **rename** action updates `files.path` to the new name and sets `files.status = 'renamed'`
- After any batch confirmation, the results panel must re-query and refresh so stale duplicate badges are removed for groups that no longer have more than one active member
- Removing a folder from the scan scope must purge (or mark inactive) all `files` rows whose path falls under that folder for the current session, then trigger orphan thumbnail cleanup

**Thumbnail cache cleanup:**
- After each batch confirmation, `db.py` must identify orphaned thumbnails: `pixel_hash` values that are no longer referenced by any `files` row with `status = 'active'`
- The corresponding `thumbs/{pixel_hash}.jpg` file is deleted from disk for each orphaned hash
- Cleanup is deferred (runs after all staged actions in the batch are applied) to avoid repeated I/O during the confirmation loop
- A `cleanup_orphaned_thumbnails()` utility in `db.py` encapsulates the orphan query and returns `list[str]` — the thumbnail paths to remove. `compare_view.py` (Phase 4) receives this list and calls `os.remove()` for each path. File deletion always happens in the caller, never inside `db.py`, consistent with the module ownership rule (db.py does no disk operations)

**Session cleanup:**
- `ON DELETE CASCADE` on `files.session_id` removes file rows when a session is deleted; the app must then call `cleanup_orphaned_thumbnails()` to purge the now-unreferenced thumbnail files from disk
- On app startup, `cleanup_orphaned_thumbnails()` runs once in the background to recover from any previously interrupted cleanup

### Security

#### File system access

- **Symlink and junction traversal** — the folder walker (`scanner.py`) must skip any directory entry that is a symbolic link or a Windows directory junction (`os.path.islink()` returns `True` for both on Windows). Without this, a junction pointing at `C:\Windows\System32` inside a scanned photo folder would cause the scanner to hash system files. Skipped entries are logged but do not abort the scan.
- **ACL and permission errors** — the scanner must not request elevated privileges. If a file or directory is unreadable under the current user's token, the error is caught, logged, and skipped (existing test: `test_discovery_pass_handles_unreadable_file`). The app never calls UAC elevation APIs.
- **Confirmed-delete path validation** — before performing a confirmed `delete` action, `compare_view.py` must verify that the resolved absolute path of the file still falls within one of the session's registered `session_folders` roots. A path that resolves outside the scan scope (e.g., due to a race-condition rename) is rejected and the user is notified.

#### Input validation and path traversal

- **Rename target validation** — the rename input field must reject any value that contains a path separator (`\`, `/`), starts with `.`, is empty, or exceeds 255 characters. Only a bare filename is accepted; `db.py` stores only the new stem. The actual `os.rename()` call constructs the destination path as `parent_of_original / new_name`, never from raw user input.
- **Username sanitization** — the display name entered in Share > Configure Sync is the stem of the exported JSON filename. It must be validated as a safe filename component: 1–64 characters, `[A-Za-z0-9_-]` only, no dots. Validation runs before saving to `sync_config` and before any Drive API call.
- **Drive folder ID validation** — the pasted Drive folder ID is validated as a string of 25–50 alphanumeric characters (`[A-Za-z0-9_-]`) before it is stored or passed to the API. An invalid format shows an inline error; no API call is made.

#### SQL safety

- **Parameterized queries throughout** — `db.py` must use `?` placeholders for every value in every query, without exception. No string formatting or concatenation with user-supplied data (file paths, usernames, hashes, action details) is permitted anywhere in the codebase. This is a hard rule enforced in code review.
- **`pixel_hash` format enforcement** — before any `remote_files.pixel_hash` value is inserted into the DB or used in a JOIN, it must be validated as a 64-character lowercase hexadecimal string. Values that fail this check are rejected with a logged `ImportError`; the rest of the import proceeds.

#### JSON import limits

- **File size cap** — imported JSON files (both manual and Drive-downloaded) are rejected if larger than **10 MB**. The check happens before parsing; no bytes beyond the limit are read.
- **Field length limits** — during import, `pixel_hash` must be exactly 64 hex chars; `filename` and `path` fields are truncated to 1024 characters; `username` must pass the same `[A-Za-z0-9_-]` check as the local setting. Entries that fail validation are skipped with a warning; the import is not aborted.
- **Maximum entry count** — a single import payload may contain at most 100 000 file entries. Payloads exceeding this are rejected entirely with a clear error message.

#### Credential and token storage

- **OAuth2 client secret** — `client_secrets.json` is bundled with the installer by necessity (Google's installed-app model). This is an accepted limitation documented by Google: the client secret is effectively public for desktop apps. The `drive.file` scope limits damage: the app can only access files it created, not the user's full Drive.
- **OAuth2 token storage** — after the OAuth2 desktop flow completes, the access and refresh tokens are written to `%APPDATA%\DejaView\credentials.json` using `google-auth`'s standard `Credentials.to_json()`. The file is created with `os.open(..., os.O_CREAT | os.O_WRONLY, 0o600)` (owner read/write only) before writing. The token file path is never stored in the SQLite database.

#### Network drive resilience

- **Timeout for network paths** — before scanning a UNC path or network-mapped drive letter, the scanner checks reachability with a short probe (`os.stat()` with a 5-second OS-level timeout via `signal` or a watchdog thread). If the probe fails, the folder is skipped with a warning rather than letting `os.walk()` hang indefinitely.
- **Mid-scan disconnection** — if a network path becomes unreachable during Pass 1 or Pass 2, the I/O error is caught per-file; the scanner continues with remaining folders. The disconnected folder is flagged in the status bar.

#### Distribution security

- **Installer code signing** — the Inno Setup installer `.exe` must be signed with a code-signing certificate before distribution. An unsigned installer triggers Windows SmartScreen and can be tampered with in transit. The PyInstaller build pipeline must include a signing step (signtool.exe) that runs before the installer is packaged.

### Resource Usage Optimization

The app must remain responsive and must not starve other Windows processes, especially during long scans of large libraries:

**CPU throttling:**
- The scanner `QThread` runs at `QThread.Priority.LowPriority`; this yields CPU to the UI thread and other foreground processes without requiring explicit sleep calls
- A configurable **scan throttle** setting (File > Settings > Scan Speed) lets the user trade scan speed for system responsiveness; the default is the lowest setting that does not visibly slow scans on typical hardware (no inter-file sleep at default; up to 20 ms sleep per file at maximum throttle)

**Memory discipline:**
- `hasher.py` must close the Pillow `Image` object immediately after hashing and thumbnail generation — no decoded image is held in memory across files
- The scanner never loads more than one image into memory at a time
- Thumbnails loaded in `compare_view.py` are loaded on demand (when the tile scrolls into view) and released when the Compare View is closed

**Database write batching:**
- During Pass 1 (discovery), file rows are inserted in batches of up to 100 per transaction rather than one transaction per file, reducing SQLite write pressure and disk I/O
- During Pass 2 (hashing), each `pixel_hash` and `thumbnail_path` update is committed individually (required for accurate resume), but WAL mode ensures these writes do not block concurrent UI reads

**UI update rate-limiting:**
- The results panel does not refresh the tree on every `hash_complete` signal; instead, incoming signals are queued and the tree is refreshed at most once every 200 ms via a `QTimer` debounce, preventing the UI from flooding the event loop during rapid hashing
- Progress bar and status label updates bypass the debounce and apply immediately (they are cheap label-only updates)

---

## Technology Stack

| Concern | Choice |
|---------|--------|
| Language | Python |
| UI Framework | PyQt6 |
| Image decoding | Pillow |
| Hashing | `hashlib` SHA-256 on normalized pixel data |
| Database | SQLite (`sqlite3` stdlib) — stored locally, never on cloud |
| Background work | `QThread` workers |
| Cloud sync | Google Drive API (`google-api-python-client`) |
| Localization | Qt Linguist (`.ts` / `.qm` files), `pylupdate6` + `lrelease` |
| Packaging | PyInstaller → Inno Setup installer |
| Sharing format | JSON |

---

## Architecture

```
dejaview/
├── main.py                  # Entry point — locale load, DB init; sync-on-start wired in Phase 6 (guarded by sync_enabled=0 in earlier phases)
├── core/
│   ├── scanner.py           # Folder walker — QThread, two-pass scan (discovery then hashing)
│   │                        # Manages session state (create/pause/resume/stop) via db.py
│   │                        # Emits signals for progress; queries duplicate_groups view to update badges
│   └── hasher.py            # Pixel-decode → RGB normalize → EXIF transpose → SHA-256
│                            # Returns (pixel_hash, thumbnail_path); called per file by scanner.py
├── data/
│   ├── db.py                # SQLite abstraction — DDL, migrations, all raw SQL
│   ├── export.py            # build_export_payload(); manual JSON export/import workflow
│   └── sync.py              # DriveSync: OAuth2, upload/download peer exports,
│                            # compute_cross_matches(); offline fallback via local cache
├── ui/
│   ├── main_window.py       # App shell — menu, toolbar, layout, sync lifecycle hooks
│   ├── folder_panel.py      # Req 4.1 — Add / remove / browse scan folders
│   ├── scan_control.py      # Req 4.2 — Progress bar, pause / resume / stop
│   ├── results_panel.py     # Req 4.3 — Tree view with All/Duplicates Only filters (Phase 3); Cross-Library filter added in Phase 5
│   ├── compare_view.py      # Req 4.4 + 4.5 — Side-by-side tiles with inline KEEP/DEL/Rename actions
│   │                        # is_local param hides action buttons on remote tiles; batch rules dialog
│   └── share_dialog.py      # Google sign-in, folder ID config, privacy level, peer list, Sync Now
└── resources/
    ├── icons/
    ├── i18n/
    │   ├── app.ts           # Source strings (English) — checked into VCS
    │   ├── app_hu.ts        # Hungarian translations — checked into VCS
    │   └── app_hu.qm        # Compiled binary — generated by lrelease, bundled in installer
    └── client_secrets.json  # Google OAuth2 desktop credentials (from Google Cloud Console)
```

**Module ownership rules:**
- `db.py` — all raw SQL; no business logic
- `scanner.py` — disk walker + QThread; manages session state via `db.py`; calls `hasher.py` per file; emits Qt signals for progress and badge updates
- `hasher.py` — pure function: one file path in, `(pixel_hash, thumbnail_path)` out; no DB access
- `sync.py` — all Google Drive API calls; calls `export.py` for payload building; calls `db.py` for peer tables
- `compare_view.py` — all staging logic; reads and writes the `actions` table via `db.py`; no direct file operations

---

## Database Schema (SQLite)

Database stored at `%APPDATA%\DejaView\library.db`.
Enable WAL mode on open: `PRAGMA journal_mode=WAL;` (allows concurrent UI reads during scan writes).

```sql
-- Scan sessions
sessions (
  id          INTEGER PRIMARY KEY,
  name        TEXT,
  created_at  TEXT,
  status      TEXT           -- 'in_progress' | 'paused' | 'complete'
)

-- Root folders belonging to each session (replaces root_folders_json)
session_folders (
  session_id  INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
  folder_path TEXT,
  PRIMARY KEY (session_id, folder_path)
)

-- Every file encountered during a scan
files (
  id             INTEGER PRIMARY KEY,
  session_id     INTEGER REFERENCES sessions(id),
  path           TEXT NOT NULL,
  size           INTEGER,
  modified_at    TEXT,
  pixel_hash     TEXT,            -- SHA-256 of normalized pixel data; NULL until hashed
  thumbnail_path TEXT,            -- path to cached 400×400 thumbnail (generated at hash time)
  status         TEXT DEFAULT 'active',  -- 'active' | 'deleted' | 'renamed'
  scanned_at     TEXT,
  UNIQUE (session_id, path)       -- prevent double-scanning the same file
)

-- User actions taken on individual files
actions (
  id            INTEGER PRIMARY KEY,
  file_id       INTEGER REFERENCES files(id),
  action_type   TEXT,             -- 'delete' | 'rename' | 'keep'
  detail        TEXT,
  status        TEXT DEFAULT 'staged', -- 'staged' | 'confirmed'
  performed_at  TEXT             -- NULL until confirmed
)

-- Duplicate groups are derived, not stored — use this view:
CREATE VIEW duplicate_groups AS
  SELECT session_id, pixel_hash, COUNT(*) AS file_count
  FROM files
  WHERE pixel_hash IS NOT NULL AND status = 'active'
  GROUP BY session_id, pixel_hash
  HAVING COUNT(*) > 1;

-- ── Sharing / Cross-library tables ──────────────────────────────────────────

-- Google Drive sync configuration (singleton row)
sync_config (
  id               INTEGER PRIMARY KEY CHECK (id = 1),
  local_username   TEXT NOT NULL,       -- stem for own export file: "alice" → "alice.json"
  gdrive_folder_id TEXT,                -- Drive folder ID (NULL = not configured)
  gdrive_file_id   TEXT,                -- Drive file ID of own exported JSON (for updates)
  sync_enabled     INTEGER DEFAULT 0,
  export_privacy   TEXT DEFAULT 'filename', -- 'hash_only' | 'filename' | 'full_path'; applies to both auto-sync and manual export
  pending_export   INTEGER DEFAULT 0,   -- 1 = export queued (was offline at last trigger)
  last_exported_at TEXT,
  last_imported_at TEXT,
  scan_delay_ms    INTEGER DEFAULT 0    -- inter-file sleep for scan throttle (ms); 0 = no delay; max 20; read once at scan start
)

-- One row per remote user whose export we have imported
remote_peers (
  id           INTEGER PRIMARY KEY,
  username     TEXT UNIQUE NOT NULL,
  last_seen_at TEXT,
  file_mtime   TEXT                     -- Drive file modifiedTime at last import (skip if unchanged)
)

-- Files from remote peers' JSON exports
remote_files (
  id           INTEGER PRIMARY KEY,
  peer_id      INTEGER REFERENCES remote_peers(id) ON DELETE CASCADE,
  remote_id    TEXT,                    -- namespaced "alice:1001" from their export
  filename     TEXT,                    -- NULL for hash_only privacy level
  path         TEXT,                    -- NULL unless full_path privacy level
  size         INTEGER,
  modified_at  TEXT,
  pixel_hash   TEXT NOT NULL
)

-- Cross-library matches are not stored — computed at display time via JOIN:
--   SELECT f.*, rf.*, rp.username
--   FROM files f
--   JOIN remote_files rf ON rf.pixel_hash = f.pixel_hash
--   JOIN remote_peers rp ON rp.id = rf.peer_id
--   WHERE f.session_id = ?
-- idx_files_hash and idx_remote_files_hash make this fast enough for thousands of images.

-- ── Indexes ─────────────────────────────────────────────────────────────────

CREATE INDEX idx_files_session    ON files(session_id);
CREATE INDEX idx_files_hash       ON files(pixel_hash);
CREATE INDEX idx_files_path       ON files(path);
CREATE INDEX idx_files_status     ON files(status);
CREATE INDEX idx_actions_file     ON actions(file_id);
CREATE INDEX idx_remote_files_hash ON remote_files(pixel_hash);
```

---

## UI Layout

### Main Window

```
┌────────────────────────────────────────────────────────┐
│ Menu: File | View | Scan | Share                       │
├──────────────┬─────────────────────────────────────────┤
│ FOLDER PANEL │  RESULTS PANEL                          │
│              │  [All | Dupes Only | Cross-Library]      │
│ [+ Add...]   │  ┌─ Folder A/                           │
│ [- Remove]   │  │  ├─ img001.jpg                       │
│              │  │  └─ img002.jpg  ● DUPLICATE          │
│ ▶ C:\Photos  │  └─ Folder B/                           │
│ ▶ Z:\Family  │     └─ photo.jpg  ● DUPLICATE           │
├──────────────┴─────────────────────────────────────────┤
│ [▶ Start] [⏸ Pause] [⏹ Stop]   ████░░░░ 47%  230/490  │
└────────────────────────────────────────────────────────┘
```

### Compare View (opens on selecting a duplicate group)

```
┌───────────────────────────────────────────────────────┐
│  DUPLICATE GROUP  (3 files · SHA: a3f9...)            │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐         │
│  │  [image]  │  │  [image]  │  │  [image]  │         │
│  │ C:\Photos │  │ Z:\Family │  │ D:\Backup │         │
│  │  2.1 MB   │  │  1.8 MB   │  │  2.1 MB   │         │
│  │ 2023-06-1 │  │ 2023-07-3 │  │ 2023-06-1 │         │
│  [KEEP][DEL] │  [KEEP][DEL] │  [KEEP][DEL]│         │
│  └───────────┘  └───────────┘  └───────────┘         │
│  [Apply to all in group]   [Batch rules...]           │
└───────────────────────────────────────────────────────┘
```

Cross-library compare view: remote tiles show peer name badge, no action buttons
(enforced by `is_local: bool` parameter in tile widget constructor — not rendered, not disabled).

---

## Development Phases

| Phase | Focus | Deliverable |
|-------|-------|-------------|
| 1 | Core engine | `hasher.py` + `scanner.py` (two-pass, session state machine) + SQLite schema + `i18n/` setup; all UI strings use `self.tr()`; headless and testable |
| 2 | Minimal UI | `main.py` (locale load, DB init; sync hook is a no-op stub until Phase 6) + folder panel + scan control + progress bar (discovery phase + hash phase) |
| 3 | Results view | Tree view with All / Duplicates Only filters; live badge updates via `duplicate_groups` view |
| 4 | Comparison | Side-by-side `compare_view.py` with inline KEEP/DEL/Rename actions + staging + batch rules + confirmation dialog (see Phase 4 sub-tasks below) |
| 5 | Manual sharing | `export.py`: `build_export_payload()`, manual JSON export/import, cross-library JOIN query, Cross-Library filter in results panel |
| 6 | Google Drive sync | `sync.py`: OAuth2, folder config, privacy level, auto sync on start/stop/scan, `share_dialog.py`, offline fallback |
| 7 | Distribution | `lrelease` → bundle `app_hu.qm`; locate `qt_hu.qm` from the Qt installation (e.g. `PyQt6/Qt6/translations/qt_hu.qm`) and bundle alongside; PyInstaller build; Inno Setup installer with Hungarian language option |

### Phase 4 Sub-tasks

| # | Sub-task | Focus | Deliverable |
|---|----------|-------|-------------|
| 4.1 | `ui/compare_view.py` — full widget | `_FileTile` (local + remote), `CompareView`, `_BatchRulesDialog`, `_ConfirmDialog`, `_validate_rename()`, path scope check, orphan thumbnail cleanup, `actions_confirmed`/`closed` signals | ~420 LOC production code |
| 4.2 | Integrate into `main_window.py` | Wire `results_panel.compare_view_requested(pixel_hash)` → open CompareView; wire `actions_confirmed` → `ResultsPanel.reload()`; wire `closed` → restore results panel | ~30 LOC diff in main_window.py |
| 4.3 | `tests/ui/test_compare_view.py` + verify | All plan §UI Tests for compare_view.py: tile rendering, local/remote button presence, KEEP/DEL staging, batch rules, rename validation, confirmation dialog, path scope guard | Full test file + verify all tests pass |

---

## Key Technical Decisions

### Why pixel-hash instead of file-hash?
File hashing (MD5/SHA-256 of raw bytes) would miss duplicates that were:
- Re-saved with different EXIF/metadata
- Opened and re-exported by a different app
- Transferred with modified timestamps

Pixel hashing decodes the image content and hashes only the visual data,
making detection robust to those differences while still being an exact match
(not perceptual/fuzzy).

### Pixel hash normalization spec
Before hashing, `hasher.py` must apply a canonical pipeline to every image:
1. `img = Image.open(path)`
2. `img = ImageOps.exif_transpose(img)` — apply EXIF orientation so a rotated JPEG and its manually-rotated copy produce the same hash
3. `img = img.convert("RGB")` — normalize to RGB mode (ensures consistent hashing regardless of internal color mode)
4. `h = hashlib.sha256(img.tobytes()).hexdigest()`

Without this, visually identical images in different formats or with EXIF orientation flags will hash differently (false negatives).

### Two-pass scan and file-size pre-filter
The scan runs in two sequential passes, both driven by `scanner.py`:

**Pass 1 — Discovery**: walk all folders, insert a row per file with `path` and `size`; `pixel_hash` stays NULL. The results tree is populated from this pass, so all files appear immediately. The progress bar shows "Discovering files…".

**Pass 2 — Hashing**: group files by size. Only groups with two or more members need pixel hashing — unique-size files are guaranteed not to be duplicates. This eliminates 70–90% of Pillow decode operations on typical photo libraries. As each file is hashed, its `pixel_hash` is written and the UI re-queries the `duplicate_groups` view to update badges in real time.

The two-pass structure is why results appear early but badges arrive later — the UX reflects this explicitly (see Workflow 1, Step 2).

### Pause/resume state machine (`scanner.py`)
Pause and resume apply only during Pass 2 (hashing). Pass 1 (discovery) is fast enough to not warrant pausing.

- `PASS1`: walks all folders, inserts files with `pixel_hash = NULL`; completes before Pass 2 begins
- `PASS2_SCANNING`: iterates size-grouped files, calls `hasher.py` per file, writes `pixel_hash` to DB
- `PAUSE` signal received: set `sessions.status = 'paused'`; the QThread exits after the current file
- `RESUME`: skip Pass 1 if `files` rows already exist for this session; in Pass 2, skip files where `pixel_hash IS NOT NULL`
- `STOP`: set `sessions.status = 'stopped'`; partial results remain browsable
- Crash recovery: rows with `pixel_hash IS NULL` are re-hashed on resume (idempotent)

### Why SQLite stays local
SQLite uses file-system byte-range locks that cloud sync clients (OneDrive, Dropbox, Google Drive desktop) interfere with. Putting a `.db` file in a synced folder risks corruption when the sync client holds the file open during upload. The database is stored at `%APPDATA%\DejaView\library.db` — never on cloud storage. Only lightweight JSON export files are exchanged via Google Drive.

### Why Google Drive API for sharing
Using the Google Drive API directly rather than a local folder path:
- No dependency on any cloud sync client being installed or running
- No file-lock conflicts (API calls, not file-system access)
- Works on any Windows machine with internet access
- `drive.file` scope — app only sees files it created, not the user's full Drive
- One shared Drive folder, shared via standard Drive sharing — no custom infrastructure

### Why PyQt6?
- Native Windows look and feel
- `QThread` integrates naturally with the scan engine (signals for progress, pause, stop)
- Qt Linguist provides a complete i18n pipeline without third-party dependencies
- Mature widget set covers tree views, image display, and dialogs without third-party add-ons

### Why SQLite?
- No installation required — single file database
- Enables pause/resume: scan state persisted between sessions
- WAL mode allows concurrent reader (UI) + writer (scanner) without blocking

### Thumbnail caching
At hash time, `hasher.py` generates a 400×400 thumbnail and saves it to
`%APPDATA%\DejaView\thumbs\{pixel_hash}.jpg`. The path is stored in
`files.thumbnail_path`. `compare_view.py` loads thumbnails, not full images,
to prevent UI thread blocking.

### Security design

**Symlink guard in `scanner.py`**

```python
for entry in os.scandir(dir_path):
    if entry.is_symlink() or (entry.is_dir() and os.path.islink(entry.path)):
        log.warning("Skipping symlink/junction: %s", entry.path)
        continue
    # proceed with walk
```
`os.path.islink()` returns `True` for both POSIX symlinks and Windows directory junctions, so a single check covers both cases.

**Parameterized SQL — enforced pattern**

Every `db.py` method that takes external data uses `?` placeholders:

```python
# correct
cursor.execute("INSERT INTO files (path, size) VALUES (?, ?)", (path, size))

# forbidden — never do this
cursor.execute(f"INSERT INTO files (path) VALUES ('{path}')")
```

Paths, hashes, usernames, action details — all go through `?`. This is enforced in code review; any bare string interpolation in `db.py` is a blocking issue.

**`pixel_hash` validation helper**

```python
import re
_HASH_RE = re.compile(r'^[0-9a-f]{64}$')

def validate_pixel_hash(value: str) -> bool:
    return bool(_HASH_RE.match(value))
```

Called by `export.import_payload()` for every entry in the incoming JSON before any DB write.

**Rename path guard in `compare_view.py`**

```python
import re
_SAFE_NAME_RE = re.compile(r'^[^\\/:*?"<>|.][^\\/:*?"<>|]{0,253}$')

def _validate_rename(new_name: str) -> bool:
    return bool(_SAFE_NAME_RE.match(new_name))

# When constructing the destination path:
dest = Path(original_path).parent / new_name   # never Path(new_name) alone
```

**OAuth2 token file creation**

```python
fd = os.open(token_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(credentials.to_json())
```

Creating via `os.open` with mode `0o600` ensures the file is owner-readable only before any data is written, avoiding a race between `open()` and `chmod()`.

**Network probe before scan**

```python
def _is_reachable(path: str, timeout_s: float = 5.0) -> bool:
    try:
        result = concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(
            os.stat, path
        ).result(timeout=timeout_s)
        return True
    except (concurrent.futures.TimeoutError, OSError):
        return False
```

Called once per root folder in `scanner.py` before Pass 1 begins. Unreachable roots are skipped with a status-bar warning; the scan continues for remaining roots.

**JSON import size guard in `sync.py` / `export.py`**

```python
MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ENTRIES = 100_000

raw = response_bytes  # from Drive or file open
if len(raw) > MAX_IMPORT_BYTES:
    raise ImportError("Peer export exceeds maximum allowed size (10 MB)")
payload = json.loads(raw)
if len(payload.get("files", [])) > MAX_IMPORT_ENTRIES:
    raise ImportError("Peer export contains too many entries")
```

### Post-action cleanup design

Orphan detection is a single SQL query:

```sql
SELECT DISTINCT thumbnail_path
FROM files
WHERE thumbnail_path IS NOT NULL
  AND pixel_hash NOT IN (
      SELECT pixel_hash FROM files WHERE status = 'active'
  );
```

This runs in `db.cleanup_orphaned_thumbnails() -> list[str]`, which returns the
paths to delete. The caller (`compare_view.py` after a batch confirmation, or
`main_window.py` on startup cleanup) calls `os.remove()` for each returned path.
File deletion always happens in the caller — never inside `db.py` — consistent
with the module ownership rule.

The results panel listens for a `actions_confirmed` signal emitted by
`compare_view.py` after each batch; on receipt it re-queries `duplicate_groups`
and repopulates only the changed subtree (not a full tree rebuild), keeping the
refresh cheap.

### Resource throttling design

The inter-file sleep (scan throttle) is stored as `scan_delay_ms INTEGER DEFAULT 0`
in `sync_config` (reusing the singleton settings row) and read once at scan start —
no live reconfiguration mid-scan. The `QThread.Priority.LowPriority` setting is
applied in `scanner.py`'s `run()` method as its first statement, before any I/O.

The 200 ms UI debounce is a `QTimer` with `setSingleShot(False)` owned by
`results_panel.py`. The scanner emits `hash_complete(file_id)` signals at full
speed; the results panel enqueues the ids and the timer triggers a single batch
refresh. This separates scanner throughput from UI repaint rate entirely.

---

## Dependencies

```
# Runtime
Pillow                      # Image decoding and normalization
PyQt6                       # UI framework
google-api-python-client    # Google Drive API
google-auth-oauthlib        # OAuth2 desktop flow
google-auth-httplib2        # HTTP transport for Drive API

# Dev / build only
pyinstaller                 # Packaging
pylupdate6                  # Extract tr() strings into .ts files
lrelease                    # Compile .ts → .qm
```

`client_secrets.json` (Google Cloud Console OAuth2 desktop credentials)
is bundled with the installer — not a Python package.

---

## Test Framework

### Goals

The test suite serves as a regression safety net for the entire development lifecycle:

- Every module added in Phases 1–7 acquires tests before or alongside the code (test-driven where practical)
- Tests run in under 60 seconds on a developer laptop (no real Drive API, no real disk I/O beyond temp dirs)
- Any change that breaks a user-visible behaviour surfaces as a failing test before it reaches `main`
- UI tests verify widget state, not pixel output — they run headless under a minimal `QApplication`

---

### Test Stack

| Tool | Purpose |
|------|---------|
| `pytest` | Test runner, parametrize, fixtures |
| `pytest-qt` | `qtbot` fixture for PyQt6 widget interaction; waits for Qt signals |
| `pytest-cov` | Coverage measurement; enforces thresholds |
| `unittest.mock` (`MagicMock`, `patch`) | Mock Google Drive API, OS file operations |
| `Pillow` | Generate synthetic fixture images programmatically |
| `tmp_path` (pytest built-in) | Isolated temp dirs for DB files, thumbnails, image fixtures |

Add to `requirements-dev.txt`:
```
pytest
pytest-qt
pytest-cov
```

---

### Directory Layout

```
dejaview/
├── tests/
│   ├── conftest.py              # Shared fixtures: QApplication, in-memory DB, fixture image factory
│   ├── fixtures/
│   │   └── make_fixtures.py     # Script (not a test): generates canonical .jpg/.png test images on disk
│   ├── unit/
│   │   ├── test_hasher.py       # core/hasher.py — pure function
│   │   ├── test_db.py           # data/db.py — schema, CRUD, views
│   │   ├── test_export.py       # data/export.py — payload building, privacy levels
│   │   ├── test_sync.py         # data/sync.py — Drive API fully mocked
│   │   └── test_security.py     # Security: symlink guard, path traversal, SQL safety, JSON limits
│   ├── integration/
│   │   ├── test_scanner_pass1.py    # Discovery pass: file walk → DB rows
│   │   ├── test_scanner_pass2.py    # Hash pass: size-filter logic, badge signals
│   │   ├── test_scanner_state.py    # Pause / resume / stop / crash-recovery state machine
│   │   └── test_cross_library.py   # Export → import round-trip → cross-library JOIN query
│   └── ui/
│       ├── test_folder_panel.py
│       ├── test_scan_control.py
│       ├── test_results_panel.py
│       └── test_compare_view.py
└── pytest.ini
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
addopts = --cov=. --cov-config=.coveragerc --cov-report=term-missing -x
qt_api = pyqt6
```

`.coveragerc`:
```ini
[run]
omit =
    tests/*
    resources/*
    main.py

[report]
fail_under = 80
```

---

### Fixture Strategy

#### `tests/conftest.py` — shared fixtures

```python
@pytest.fixture(scope="session")
def qapp():
    """Single QApplication for the entire test session (pytest-qt provides this automatically)."""
    ...

@pytest.fixture
def db(tmp_path):
    """Fresh in-memory (or tmp_path) SQLite DB with schema applied. Returned as an open db.Database."""
    from data.db import Database
    d = Database(tmp_path / "test.db")
    d.open()
    yield d
    d.close()

@pytest.fixture
def thumb_dir(tmp_path):
    """Isolated thumbnail cache directory."""
    t = tmp_path / "thumbs"
    t.mkdir()
    return t

@pytest.fixture
def image_factory(tmp_path):
    """
    Returns a callable: make_image(color, mode, exif_orientation, fmt) -> Path.
    Creates a synthetic Pillow image, saves it to tmp_path, returns its path.
    Supports modes: 'RGB', 'RGBA', 'L', 'P' (palette).
    Supports EXIF orientation tags 1–8.
    """
    ...

@pytest.fixture
def session_factory(db):
    """Creates a scan session row and returns its id."""
    ...
```

#### `tests/fixtures/make_fixtures.py` — static canonical images

A standalone script (not collected by pytest) that generates a small set of reference images into `tests/fixtures/images/` and checks them into VCS:

| File | Content | Purpose |
|------|---------|---------|
| `red_rgb.jpg` | 64×64 solid red, RGB | Canonical baseline |
| `red_rgba.png` | 64×64 solid red, RGBA | Same visual content, different format |
| `red_gray.png` | 64×64 solid red, grayscale-L | Same visual content, different mode |
| `red_exif_rot90.jpg` | `red_rgb.jpg` re-saved with EXIF orientation=6 (90° CW) | Should produce same pixel hash after transpose |
| `blue_rgb.jpg` | 64×64 solid blue | Visually different, guaranteed different hash |
| `corrupt.jpg` | Truncated JPEG bytes | Error-handling fixture |

Committed as binary. The script documents how they were produced so they can be regenerated if needed.

---

### Unit Tests: `core/hasher.py`

File: `tests/unit/test_hasher.py`

`hasher.hash_file(path, thumb_dir) -> (pixel_hash: str, thumbnail_path: str)`

#### Hash correctness

```
test_same_content_jpg_and_png_produce_same_hash
    Given red_rgb.jpg and red_rgba.png (same visual content)
    When hash_file() is called on each
    Then both pixel_hash values are equal

test_different_images_produce_different_hashes
    Given red_rgb.jpg and blue_rgb.jpg
    Then pixel_hash values differ

test_exif_orientation_is_normalized
    Given red_rgb.jpg and red_exif_rot90.jpg
    Then pixel_hash values are equal
    (EXIF transpose applied before hashing)

test_grayscale_image_produces_same_hash_as_rgb_equivalent
    Given red_gray.png (L mode) and red_rgb.jpg (RGB, same content)
    Then pixel_hash values are equal
    (convert("RGB") normalizes both to the same bytes)

test_rgba_image_matches_rgb_equivalent
    Given red_rgba.png and red_rgb.jpg
    Then pixel_hash values are equal
```

Parametrize `test_same_content_*` across all equivalent pairs in the fixture set.

#### Thumbnail generation

```
test_thumbnail_is_created_at_correct_path
    Given red_rgb.jpg, thumb_dir
    When hash_file() is called
    Then thumb_dir / f"{pixel_hash}.jpg" exists

test_thumbnail_dimensions_are_400x400_or_smaller
    Given any valid image
    Then thumbnail width <= 400 and height <= 400

test_thumbnail_not_recreated_if_already_exists
    Given hash_file() already ran (thumbnail exists)
    When hash_file() runs again for the same image
    Then the thumbnail file is not modified (mtime unchanged)
    (idempotent — avoids redundant Pillow encode on resume)
```

#### Error handling

```
test_corrupt_file_raises_or_returns_none
    Given corrupt.jpg
    When hash_file() is called
    Then it raises a well-typed exception (e.g. UnidentifiedImageError or a custom HashError)
    — it must NOT return a garbage hash or cause the scanner to crash

test_nonexistent_file_raises_file_not_found
    Given a path that does not exist
    Then FileNotFoundError (or custom HashError wrapping it) is raised
```

---

### Unit Tests: `data/db.py`

File: `tests/unit/test_db.py`

#### Schema

```
test_all_tables_created_on_open
    Given a fresh DB
    Then tables: sessions, session_folders, files, actions, sync_config,
                 remote_peers, remote_files all exist

test_all_indexes_created
    Then idx_files_session, idx_files_hash, idx_files_path, idx_files_status,
         idx_actions_file, idx_remote_files_hash all exist

test_duplicate_groups_view_exists
    Then the view duplicate_groups is queryable

test_wal_mode_enabled
    PRAGMA journal_mode returns 'wal'
```

#### Session CRUD

```
test_create_session_returns_id
test_session_status_defaults_to_in_progress
test_update_session_status_to_paused
test_update_session_status_to_complete
test_delete_session_cascades_to_files_and_folders
```

#### File operations

```
test_insert_file_row
test_upsert_on_duplicate_session_path_pair
    Inserting the same (session_id, path) twice must not raise — it updates in place

test_update_pixel_hash
test_files_with_null_hash_not_in_duplicate_groups
test_files_with_unique_size_not_in_duplicate_groups
    Even if two files share a hash, if size-filter logic excludes them they never get hashed —
    this tests the view contract: only pixel_hash IS NOT NULL, status = 'active', count > 1

test_duplicate_groups_view_counts_correctly
    Insert 3 files with the same pixel_hash for one session_id
    Query duplicate_groups → file_count = 3
    Mark one as status='deleted' → file_count = 2
```

#### Actions

```
test_stage_action_for_file
test_action_status_defaults_to_staged
test_confirm_action_sets_performed_at
test_list_staged_actions_for_session
```

#### Sharing tables

```
test_insert_sync_config_singleton
test_update_sync_config
test_insert_remote_peer
test_insert_remote_files_for_peer
test_delete_peer_cascades_to_remote_files
test_cross_library_join_query_returns_matching_files
    Given a local file with pixel_hash='abc' and a remote_file with pixel_hash='abc'
    Then the JOIN query returns one row with both local and remote metadata
```

---

### Unit Tests: `data/export.py`

File: `tests/unit/test_export.py`

`export.build_export_payload(db, session_id, username, privacy_level) -> dict`

```
test_hash_only_privacy_omits_filename_and_path
    payload['files'][n] has 'pixel_hash', 'size', 'modified_at'
    but no 'filename' and no 'path'

test_filename_privacy_includes_filename_not_path
    payload['files'][n] has 'filename' but no 'path'

test_full_path_privacy_includes_full_path
    payload['files'][n] has 'path' (and 'filename' can be derived from it)

test_export_only_includes_active_files
    Files with status='deleted' must not appear in the payload

test_export_payload_contains_username_and_timestamp
    payload['username'] == username
    payload['exported_at'] is a valid ISO-8601 string

test_round_trip_hash_only
    build_export_payload(..., 'hash_only') → JSON string → import_payload(db, json_str)
    Then remote_files table has correct pixel_hash rows
    And cross-library JOIN returns the expected local files

test_import_malformed_json_raises_clean_error
    Given a string that is not valid JSON
    Then import_payload raises a specific ImportError (not a raw json.JSONDecodeError bubbling up)

test_import_missing_required_fields_raises_clean_error
    Given JSON with missing 'pixel_hash' on a file entry
    Then import_payload raises a specific ImportError

test_import_is_idempotent
    Importing the same payload twice produces the same DB state (no duplicates)
```

---

### Unit Tests: `data/sync.py`

File: `tests/unit/test_sync.py`

All Google Drive API calls are mocked via `unittest.mock.patch`.

```
test_upload_called_with_correct_file_id_on_update
    Given sync_config has gdrive_file_id set
    When DriveSync.upload() is called
    Then drive.files().update() is called (not create)
    And the correct gdrive_file_id is passed

test_upload_called_with_create_on_first_export
    Given sync_config.gdrive_file_id is NULL
    Then drive.files().create() is called
    And the returned file id is saved to sync_config.gdrive_file_id

test_download_skips_unchanged_peer_file
    Given remote_peer has file_mtime matching the Drive file's modifiedTime
    When DriveSync.download_peers() is called
    Then drive.files().get_media() is NOT called for that peer

test_download_imports_changed_peer_file
    Given file_mtime does not match
    Then drive.files().get_media() IS called and import_payload() is invoked

test_offline_fallback_does_not_raise
    Given drive API raises HttpError (simulated network failure)
    Then DriveSync.sync() catches it, sets status to 'unavailable'
    And no exception propagates to the caller

test_pending_export_flag_set_when_offline
    Given sync call fails
    Then sync_config.pending_export = 1

test_pending_export_sent_on_next_successful_sync
    Given pending_export = 1
    When the next sync succeeds
    Then upload is called and pending_export reset to 0

test_remove_peer_clears_remote_files
    Given a peer exists with 3 remote_files rows
    When DriveSync.remove_peer(username) is called
    Then the peer row and all its remote_files are gone
```

---

### Integration Tests: `core/scanner.py`

These tests instantiate the real `Scanner` QThread against a real temp directory of synthetic images and a real (tmp_path) SQLite DB. No Drive API involved.

File: `tests/integration/test_scanner_pass1.py`

```
test_discovery_pass_inserts_all_files
    Given a tmp_path folder with 5 image files
    When scanner runs Pass 1
    Then db.files has 5 rows for this session_id, all with pixel_hash = NULL

test_discovery_pass_records_correct_path_and_size
    Then each row's path and size match the actual file

test_discovery_pass_does_not_enter_excluded_dirs
    Given a folder with a subfolder named '.hidden' containing 2 files
    When scanning with that subfolder excluded
    Then those 2 files do not appear in db.files
    (documents the exclusion contract — implement exclusion in Phase 1)

test_discovery_pass_completes_before_hash_pass_begins
    Verified via signal ordering: file_discovered signals before first hash_complete signal

test_discovery_pass_handles_empty_folder
    Given a folder that exists but is empty
    Then no rows inserted, no exception

test_discovery_pass_handles_unreadable_file
    Given a folder containing a file with no read permission
    Then scanner logs/signals the error but continues, other files are inserted
```

File: `tests/integration/test_scanner_pass2.py`

```
test_only_size_duplicate_candidates_are_hashed
    Given 4 files: two with size=1000, two with unique sizes
    When scanner completes
    Then exactly 2 files have pixel_hash IS NOT NULL (only the size-pair)

test_badge_signal_emitted_for_confirmed_duplicate
    Given two files with identical pixel content (same hash)
    When scanner emits duplicate_found signal
    Then both file ids are included in the signal payload

test_unique_file_never_emits_duplicate_signal
    Given 3 files all with unique content
    Then no duplicate_found signal is emitted

test_thumbnail_path_stored_in_db
    After scan, files with pixel_hash have thumbnail_path IS NOT NULL

test_progress_signals_advance_monotonically
    progress_updated(current, total) signals emitted with current increasing each time
```

File: `tests/integration/test_scanner_state.py`

```
test_pause_sets_session_status_to_paused
    Call scanner.pause() during Pass 2
    Then sessions.status = 'paused' in DB

test_pause_stops_thread_after_current_file_completes
    The QThread finishes within a reasonable timeout after pause() is called

test_resume_skips_already_hashed_files
    Given a paused session where 2 of 4 files are hashed
    When scanner.resume() is called
    Then only the remaining 2 NULL-hash files are processed
    (verified by counting hasher.hash_file() calls with a mock)

test_resume_skips_pass1_if_files_already_discovered
    Given a paused session with existing files rows
    When scanner.resume() is called
    Then no new file rows are inserted (Pass 1 skipped entirely)

test_stop_sets_session_status_to_stopped
    Call scanner.stop()
    Then sessions.status = 'stopped'

test_partial_results_remain_after_stop
    Hashed files retain their pixel_hash after stop

test_crash_recovery_rehashes_null_hash_files
    Given a session where 2 files have pixel_hash = NULL (simulated mid-scan crash)
    When scanner.resume() is called
    Then those 2 NULL rows are re-hashed (idempotent recovery)

test_session_status_set_to_complete_when_scan_finishes_normally
    After a full scan with no pause/stop
    Then sessions.status = 'complete'
```

---

### Integration Tests: Cross-library round-trip

File: `tests/integration/test_cross_library.py`

```
test_export_then_import_produces_cross_library_match
    Given local file with pixel_hash='abc123'
    And peer export JSON containing pixel_hash='abc123'
    When import_payload() is called
    Then the cross-library JOIN query returns one result row
    And the result row includes both local file metadata and the peer's username

test_hash_only_import_does_not_expose_peer_filenames
    Given peer export with privacy='hash_only'
    Then remote_files.filename IS NULL for all imported rows

test_no_cross_library_match_for_unshared_hash
    Given local file with pixel_hash='abc123'
    And peer export containing only pixel_hash='xyz999'
    Then cross-library JOIN returns zero rows

test_multiple_peers_both_matched
    Given two peers both having pixel_hash='abc123'
    Then cross-library JOIN returns two rows (one per peer)

test_removing_peer_removes_their_cross_library_results
    After remove_peer(), the cross-library JOIN returns zero rows for that peer
```

---

### UI Tests: `ui/folder_panel.py`

File: `tests/ui/test_folder_panel.py`

```
test_add_folder_appears_in_list(qtbot)
    Given a FolderPanel widget
    When add_folder(path) is called programmatically
    Then the list model contains one item with that path

test_remove_folder_removes_from_list(qtbot)
    Given a FolderPanel with one folder
    When remove_folder(path) is called
    Then the list model is empty

test_duplicate_folder_not_added_twice(qtbot)
    Adding the same path twice results in one list entry

test_folder_list_persists_to_db(qtbot, db)
    After add_folder(), session_folders table contains the folder path
```

---

### UI Tests: `ui/scan_control.py`

File: `tests/ui/test_scan_control.py`

```
test_initial_state_only_start_enabled(qtbot)
    On widget creation: Start enabled, Pause disabled, Stop disabled

test_after_start_pause_and_stop_become_enabled(qtbot)
    Simulate scan_started signal → Pause and Stop become enabled, Start disabled

test_after_pause_resume_enabled_not_pause(qtbot)
    Simulate scan_paused signal → Resume enabled, Pause disabled

test_after_stop_only_start_enabled(qtbot)
    Simulate scan_stopped signal → back to initial button state

test_progress_bar_updates_on_signal(qtbot)
    Emit progress_updated(47, 100) → progress bar value is 47 and label shows "47 / 100"

test_status_label_shows_paused_badge_when_paused(qtbot)
    After scan_paused signal → status label contains "PAUSED" text
```

---

### UI Tests: `ui/results_panel.py`

File: `tests/ui/test_results_panel.py`

```
test_all_filter_shows_every_file(qtbot, db)
    Given 5 files in DB (2 duplicates, 3 unique)
    When filter is set to 'All'
    Then tree model has 5 leaf nodes

test_duplicates_only_filter_hides_unique_files(qtbot, db)
    When filter is set to 'Duplicates Only'
    Then only the 2 duplicate files are visible

test_cross_library_filter_shows_cross_matches(qtbot, db)
    Given a remote_file match for one local file
    When filter is set to 'Cross-Library'
    Then only that one local file is visible

test_duplicate_badge_visible_on_duplicate_file(qtbot, db)
    The tree item for a duplicate file has the DUPLICATE badge text in its display data

test_no_badge_on_unique_file(qtbot, db)
    The tree item for a unique file has no badge text

test_clicking_duplicate_file_opens_compare_view(qtbot)
    Simulate click on a duplicate file row
    Then compare_view_requested signal is emitted with the correct pixel_hash
```

---

### UI Tests: `ui/compare_view.py`

File: `tests/ui/test_compare_view.py`

```
test_all_tiles_rendered_for_group(qtbot, db)
    Given a duplicate group with 3 local files
    When CompareView is opened for that group
    Then 3 tiles are visible

test_local_tile_has_keep_and_del_buttons(qtbot, db)
    A tile constructed with is_local=True has KEEP and DEL buttons present

test_remote_tile_has_no_action_buttons(qtbot, db)
    A tile constructed with is_local=False has neither KEEP nor DEL buttons
    (buttons are not rendered, not merely disabled)

test_clicking_keep_stages_keep_action(qtbot, db)
    Click KEEP on a tile → actions table has one 'keep' row for that file_id, status='staged'

test_clicking_del_stages_delete_action(qtbot, db)
    Click DEL on a tile → actions table has one 'delete' row, status='staged'

test_clicking_keep_on_one_marks_others_as_del_candidates(qtbot, db)
    After KEEP on tile 1, tiles 2 and 3 are visually marked as candidates for deletion

test_batch_rule_keep_oldest_stages_correct_actions(qtbot, db)
    Given 3 files with different modified_at dates
    Apply 'keep oldest' batch rule
    Then actions table has 'keep' for the earliest file and 'delete' for the other two

test_batch_rule_keep_largest_stages_correct_actions(qtbot, db)
    Given 3 files with different sizes
    Apply 'keep largest' batch rule
    Then actions table has 'keep' for the largest file

test_rename_action_staged_with_new_name(qtbot, db)
    Click Rename, type new name in inline field, confirm
    Then actions table has 'rename' row with detail = new name

test_confirmation_dialog_lists_all_staged_deletes(qtbot, db)
    Given 2 staged 'delete' actions
    When confirmation dialog opens
    Then it lists exactly 2 file paths

test_confirm_sets_action_status_to_confirmed(qtbot, db)
    After confirmation
    Then actions.status = 'confirmed' for both rows
    And actions.performed_at IS NOT NULL
```

---

### Security Tests

File: `tests/unit/test_security.py`

#### Symlink / junction guard

```
test_scanner_skips_symlinked_directory
    Given a scan folder containing a directory symlink pointing outside the scope
    When scanner runs Pass 1
    Then no files from the symlink target appear in db.files
    And a warning is logged for the skipped entry

test_scanner_skips_windows_junction
    Given a scan folder containing a Windows directory junction (created with mklink /J)
    When scanner runs Pass 1
    Then the junction target is not traversed

test_scanner_does_not_skip_regular_directory
    Given a scan folder with a normal subdirectory (not a symlink)
    Then files inside it ARE discovered
```

#### Rename path traversal

```
test_rename_rejects_path_separator
    Given a rename input of "../../evil.jpg"
    When _validate_rename() is called
    Then it returns False

test_rename_rejects_empty_string
    Then _validate_rename("") returns False

test_rename_rejects_leading_dot
    Then _validate_rename(".hidden") returns False

test_rename_rejects_over_255_chars
    Then _validate_rename("a" * 256) returns False

test_rename_accepts_valid_filename
    Then _validate_rename("vacation_beach_2023.jpg") returns True

test_rename_destination_is_same_directory
    Given original path "C:/Photos/img.jpg" and new name "img_copy.jpg"
    When the rename destination is constructed
    Then it is "C:/Photos/img_copy.jpg" (parent unchanged)
```

#### SQL parameterization

```
test_file_path_with_sql_injection_stored_safely
    Given a file path containing single quotes and SQL keywords:
      "C:/Photos/it's a'; DROP TABLE files; -- .jpg"
    When insert_file() is called with this path
    Then the row is stored without error
    And SELECT path FROM files returns the exact original string
    And the files table still exists

test_pixel_hash_with_special_chars_stored_safely
    (Same pattern with a crafted pixel_hash value — caught by format validation first,
     then verified the DB write uses parameterization regardless)
```

#### `pixel_hash` format validation

```
test_valid_pixel_hash_accepted
    "a3f9" * 16  (64 hex chars) → validate_pixel_hash returns True

test_pixel_hash_too_short_rejected
    "a3f9" * 15 + "a3" → False

test_pixel_hash_non_hex_chars_rejected
    "g" + "a" * 63 → False

test_pixel_hash_with_sql_injection_rejected
    "'; DROP TABLE files; --" + "a" * 41 → False
```

#### JSON import limits

```
test_import_rejects_payload_over_10mb
    Given a JSON bytestring of 10 MB + 1 byte
    When import_payload() is called
    Then ImportError is raised with a message about size limit
    And no rows are inserted into remote_files

test_import_rejects_payload_with_too_many_entries
    Given a valid JSON payload with 100 001 file entries
    Then ImportError is raised

test_import_truncates_long_filename_field
    Given a peer file entry with filename of 2000 characters
    When import_payload() stores the row
    Then remote_files.filename is at most 1024 characters

test_import_skips_entry_with_invalid_pixel_hash
    Given a payload with one valid and one invalid pixel_hash entry
    Then only the valid entry is inserted; a warning is logged for the invalid one
    And no exception propagates
```

#### Credential file permissions

```
test_token_file_created_with_restricted_permissions
    Given a credentials save path in tmp_path
    When save_credentials(creds, path) is called
    Then os.stat(path).st_mode & 0o777 == 0o600
    (Owner read/write only — no group or other access)
```

---

### Regression Suites

These tests exercise complete user workflows from the development phases. They run against real modules with no mocking except the Drive API. Each regression test is labeled with the workflow number from the UX section.

File: `tests/integration/test_regression.py`

```
# Workflow 1 — Scanning a Photo Library
test_regression_wf1_scan_produces_duplicate_badges
    1. Create tmp folder with 3 image files: img_a.jpg, img_b.jpg (identical content), img_c.jpg (unique)
    2. Create DB session, add folder
    3. Run scanner to completion
    4. Assert duplicate_groups view returns pixel_hash for img_a/img_b with file_count=2
    5. Assert img_c is NOT in duplicate_groups
    6. Assert sessions.status = 'complete'

# Workflow 2 — Reviewing Duplicates
test_regression_wf2_filter_duplicates_only
    1. Scan as above
    2. Query the "Duplicates Only" result set (the same query results_panel uses)
    3. Assert only 2 paths returned (the duplicates), img_c excluded

# Workflow 3 — Acting on Duplicates (staging + confirm)
test_regression_wf3_stage_and_confirm_delete
    1. Scan as above
    2. Stage action: delete img_b.jpg
    3. Assert actions.status = 'staged', no files actually deleted yet
    4. Confirm the action (call the confirm pathway)
    5. Assert actions.status = 'confirmed', actions.performed_at IS NOT NULL
    6. Assert (in a test that does real file deletion) img_b.jpg no longer exists on disk
       (this sub-test is gated: only run when RUN_DESTRUCTIVE_TESTS=1 env var is set)

# Workflow 4 — Cross-Library (read-only remote tiles)
test_regression_wf4_remote_tile_has_no_actions(qtbot, db)
    1. Create local file, create matching remote_file in DB for peer 'alice'
    2. Open CompareView with the cross-library group
    3. Assert local tile has KEEP + DEL buttons
    4. Assert remote tile has no KEEP, no DEL, no Rename button
    5. Assert remote tile shows 'alice' peer label

# Workflow 5 — Google Drive Sync (fully mocked)
test_regression_wf5_auto_upload_after_scan_complete
    1. Configure mock DriveSync
    2. Run scanner to completion
    3. Assert DriveSync.upload() was called exactly once after scan_complete signal

test_regression_wf5_auto_download_on_start
    1. Mock Drive API with one peer file available
    2. Simulate app startup (call the sync-on-start hook)
    3. Assert import_payload() was called and remote_files populated

# Workflow 6 — Manual Export / Import
test_regression_wf6_manual_export_import_round_trip
    1. Scan a folder with 2 duplicate images
    2. Export to JSON (all three privacy levels tested via parametrize)
    3. Create a second DB (simulating another user)
    4. Import the JSON into the second DB
    5. Assert cross-library JOIN in the second DB returns the expected pixel_hash matches
```

---

### Coverage Requirements

| Module | Minimum Coverage |
|--------|-----------------|
| `core/hasher.py` | 95% |
| `core/scanner.py` | 85% |
| `data/db.py` | 90% |
| `data/export.py` | 90% |
| `data/sync.py` | 80% |
| `ui/*.py` | 70% |
| Overall | 80% |

These thresholds are enforced in CI via `pytest --cov --cov-fail-under=80`.

---

### Running Tests

```bash
# All tests with coverage report
pytest

# Fast: unit tests only (no Qt, no QThread spin-up)
pytest tests/unit/

# Integration tests (slower — spins up QThread workers)
pytest tests/integration/

# UI tests (requires display or virtual framebuffer)
pytest tests/ui/

# Generate HTML coverage report
pytest --cov-report=html
open htmlcov/index.html

# Run with destructive tests enabled (actual file deletion)
RUN_DESTRUCTIVE_TESTS=1 pytest tests/integration/test_regression.py::test_regression_wf3_stage_and_confirm_delete
```

On CI (GitHub Actions / local pre-commit hook), run:
```bash
pytest tests/unit/ tests/integration/ tests/ui/ -x --cov --cov-fail-under=80
```

The `-x` flag stops on the first failure — a broken regression is always blocking.

---

### Test Development Rules

- **No test touches real `%APPDATA%`** — always redirect `DB_PATH` and `THUMB_DIR` via fixtures or env vars
- **No test calls the real Google Drive API** — mock at the `google.oauth2.credentials.Credentials` and `googleapiclient.discovery.build` level
- **No test writes outside `tmp_path`** — destructive tests are opt-in via env var
- **Each test is independent** — tests must not share DB state; use fresh `db` fixture per test
- **Tests name the requirement they cover** — test docstring or comment cites the feature number (e.g. `# Req 4.2 — pause/resume`) to link failures to the spec
