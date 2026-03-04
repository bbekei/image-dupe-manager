# DejaView — Technical Requirements Document

**Duplicate Photo Manager for Windows**

| | |
|---|---|
| **Version** | 2.0 — pywebview + React Migration |
| **Date** | March 2026 |
| **Status** | Approved |
| **Author** | Product & Engineering |

---

## 1. Application Overview

DejaView is a Windows desktop application that scans a user's photo library, identifies duplicate and visually similar images via pixel hashing and perceptual hashing, and provides a visual review interface for managing those duplicates. The application extends to cross-family duplicate detection and photo sharing through a Google Drive sync layer (Phase 1), with a custom cloud backend planned for Phase 2.

This document specifies the technology stack, component architecture, dependencies, and integration points required to modernize the UI layer from PyQt6 to a React-based webview while preserving the entire existing Python backend.

### 1.1 Migration Rationale

The existing PyQt6 application has ~27,500 lines of working Python code across `core/`, `data/`, `ui/`, and `tests/`. Rather than discarding 80% of this codebase (as a Tauri + Rust rewrite would require), the migration uses **pywebview** to host a React UI inside a native WebView2 window while keeping all Python backend code intact. Only the `ui/` layer (~6,000 lines) is replaced.

---

## 2. Architecture Overview

The application follows a two-layer architecture: a Python backend hosting a native WebView2 window via pywebview, and a React-based UI layer rendered inside that window.

### 2.1 Runtime Stack

| Property | Specification |
|---|---|
| Application Shell | pywebview 5.x — Python-hosted native window with system WebView2 rendering (Windows) |
| UI Framework | React 18+ with TypeScript |
| Styling | Tailwind CSS 3.x with custom design tokens matching the wireframe color system |
| State Management | Zustand (lightweight, no boilerplate, supports persistence middleware) |
| Routing | React Router v6 (hash-based routing for desktop app compatibility) |
| Build Tooling | Vite 5.x (fast HMR, native ESM) for frontend; PyInstaller for final production bundle |
| Backend Language | Python 3.12+ — existing codebase, all business logic |
| Frontend Language | TypeScript 5.x (strict mode) |
| Communication | pywebview JS↔Python bridge (`window.pywebview.api.*` for calls; `CustomEvent` dispatch for events) |

### 2.2 Layer Responsibilities

| Layer | Responsibility |
|---|---|
| pywebview (Python) | Window management, JS↔Python bridge, native OS dialogs, tray icon via `pystray`, system WebView2 rendering, hosting all backend logic in-process |
| React (TypeScript) | All UI rendering, user interaction handling, state management, calling Python backend functions via `window.pywebview.api.*`, listening for backend events via `CustomEvent` |
| Python Backend (existing) | ALL business logic: multi-pass scanning, pixel & perceptual hashing, SQLite database access, file operations (soft-delete, recover, purge), selection presets, similarity grouping, hash export/import, Google Drive sync, session lifecycle, master copy protection |

### 2.3 Communication Model

**Frontend → Backend (function calls):**
The React frontend calls Python functions directly via `window.pywebview.api.<function_name>(args)`. Each call returns a Promise that resolves with the Python function's return value (automatically JSON-serialized by pywebview).

**Backend → Frontend (events):**
Python pushes real-time events to the React frontend via `pywebview.evaluate_js()`, dispatching `CustomEvent` objects on the `window`:

```python
# Example: forwarding scanner progress signal
def on_progress(current, total):
    window.evaluate_js(
        f'window.dispatchEvent(new CustomEvent("scan:progress", '
        f'{{detail: {{current: {current}, total: {total}}}}}));'
    )
```

This replaces the current PyQt signal/slot system with equivalent functionality. All 13+ scanner signals and 6+ executor signals are forwarded as named `CustomEvent` types.

---

## 3. Frontend Dependencies

All frontend packages are managed via npm and bundled by Vite. The built output is served from `frontend/dist/` inside the pywebview window.

### 3.1 Core Dependencies

| Package | Purpose |
|---|---|
| `react`, `react-dom` | UI component library and DOM renderer |
| `react-router-dom` | Client-side routing with hash-based history for desktop app compatibility |
| `zustand` | Minimal state management — stores for scan state, review progress, family sharing, and UI preferences |
| `tailwindcss` | Utility-first CSS framework with custom design tokens matching the wireframe color system |
| `i18next`, `react-i18next` | Internationalization — runtime string translation with JSON translation files |

### 3.2 UI Component Dependencies

| Package | Purpose |
|---|---|
| `@tanstack/react-virtual` | Virtualized list rendering — critical for handling tens of thousands of duplicate groups without performance degradation |
| `react-compare-slider` | Side-by-side image comparison component for the group review and similarity screens; supports overlay and slider modes |
| `lucide-react` | Icon library — consistent, lightweight SVG icons for navigation, actions, and status indicators |
| `sonner` | Toast notification system for async operations: scan progress, share requests, bulk action confirmations |
| `@radix-ui/react-dialog` | Accessible modal dialogs for confirmation prompts (delete, auto-resolve, share approval) |
| `@radix-ui/react-dropdown-menu` | Accessible dropdown menus for per-photo and bulk action menus |
| `@radix-ui/react-tooltip` | Accessible tooltips for metadata display and action explanations |
| `date-fns` | Lightweight date formatting for file dates, request timestamps, and retention countdowns in the Duplicates Bin |

### 3.3 Data & Validation

| Package | Purpose |
|---|---|
| `zod` | Runtime schema validation for data flowing between the Python backend and the React frontend |

> **Note:** `@tanstack/react-query` is deferred to Phase 2 (cloud API integration). For Phase 1, all local data access uses direct `window.pywebview.api.*` calls, which return Promises natively. React-query's caching, retry, and optimistic update features become valuable only when the app communicates with a remote cloud backend.

---

## 4. Python Backend API

The Python backend is the existing DejaView codebase. All business logic, database access, file operations, and processing pipelines remain in Python. A thin API layer (`backend/api.py`) exposes these capabilities to the React frontend via pywebview's JS↔Python bridge.

### 4.1 Python Dependencies

| Package | Purpose |
|---|---|
| `pywebview` (v5.x) | Native window with WebView2, JS↔Python bridge |
| `pystray` | System tray icon (replaces PyQt6's QSystemTrayIcon) |
| `Pillow` | Image processing — EXIF orientation, RGB conversion, thumbnail generation |
| `xxhash` | Fast pixel hashing (xxh128, 60× faster than SHA-256) |
| `numpy` | Memory-optimized zero-copy view for hash computation |
| `imagehash` | Perceptual hashing (pHash) for similarity detection |
| `google-api-python-client` | Google Drive API for Phase 1 cloud sync |
| `google-auth-oauthlib` | OAuth2 desktop flow for Google Drive authentication |
| `google-auth-httplib2` | HTTP transport for Google APIs |

### 4.2 Backend API Functions

The following Python functions are exposed to the React frontend via `window.pywebview.api.*`. Each function is callable from JavaScript and returns JSON-serializable data.

#### Scan & Session Management

| Function | Description | Maps to |
|---|---|---|
| `start_scan(folders, session_name, enable_similarity)` | Starts a new multi-pass scan. Returns session_id. Emits progress events via CustomEvent. | `Scanner(db, folders).start()` |
| `pause_scan()` | Pauses the running scan. Scanner stops after current file. | `scanner.pause()` |
| `resume_scan(session_id)` | Resumes a paused scan, skipping already-processed files. | `scanner.set_resuming(True); scanner.start()` |
| `stop_scan()` | Stops the scan permanently. Session marked as `stopped`. | `scanner.stop()` |
| `get_sessions()` | Returns all scan sessions with status, folder count, file count. | `db.get_sessions()` |
| `get_scan_summary(session_id)` | Returns aggregate stats: total groups, total duplicates, recoverable space. | `db.get_session()` + `duplicate_groups` VIEW |

#### Duplicate Groups & File Actions

| Function | Description | Maps to |
|---|---|---|
| `get_duplicate_groups(session_id, offset, limit, filters)` | Paginated query returning duplicate groups with file metadata. Supports folder, date range, and size filters. | `db.get_files_by_session()` + filtering |
| `get_group_detail(session_id, pixel_hash)` | Returns full metadata for all files in a specific duplicate group, including thumbnail paths. | `db.get_files_by_hash()` |
| `set_file_action(file_id, action, scope)` | Marks a file with an action (keep/delete/ignore) at file or folder scope. | `db.set_file_action()` |
| `apply_selection_preset(session_id, preset, group_ids)` | Applies a smart selection preset to specified groups. Returns keep/delete counts. | `selection.apply_preset()` |
| `get_plan_summary(session_id)` | Returns all planned actions for review before execution, grouped by action type with impact totals. | `db.get_actions_by_session()` |
| `execute_plan(session_id)` | Executes all planned file actions (soft-delete, sync). Emits progress events. | `PlanExecutor(db, session_id).start()` |

#### Similarity Detection

| Function | Description | Maps to |
|---|---|---|
| `get_similarity_groups(session_id, threshold)` | Returns groups of visually similar (not identical) images, grouped by pHash proximity. | `similarity.build_similarity_groups()` |
| `apply_similarity_preset(session_id, preset, group_ids)` | Applies selection preset to similarity groups. Master copy protection enforced. | `similarity_selection.apply_similarity_preset()` |
| `recommend_keeper(files)` | Returns the recommended file to keep and the reason (resolution > size > date > path). | `similarity_selection.recommend_keeper()` |

#### Duplicates Bin (Soft Delete)

| Function | Description | Maps to |
|---|---|---|
| `get_bin_items(session_id)` | Returns all soft-deleted items with original path, trash path, deletion date, and expiry date. | `db.get_soft_deletes()` |
| `restore_from_bin(soft_delete_id)` | Moves a file from the trash back to its original location. | `trash.recover()` |
| `permanent_delete(soft_delete_ids)` | Permanently deletes specified bin items from disk. Irreversible. | `trash.purge()` |
| `purge_expired()` | Permanently deletes all bin items past their 30-day retention period. | `trash.purge_expired()` |

#### Family Sharing (Phase 1 — Google Drive)

| Function | Description | Maps to |
|---|---|---|
| `export_hashes(session_id)` | Exports hashes and metadata to a JSON file for sharing. | `export.export_session()` |
| `import_hashes(file_path)` | Imports a peer's hash export file. Validates schema, caps at 100K entries. | `export.import_file()` |
| `sync_drive()` | Uploads export to Google Drive shared folder and downloads peer exports. | `sync.sync()` |
| `get_remote_peers()` | Returns all known remote peers with last-seen timestamps. | `db.get_remote_peers()` |
| `get_requests(session_id)` | Returns all photo requests (incoming and outgoing) with status. | `db.get_requests()` |
| `respond_to_request(request_id, response)` | Approves or declines an incoming request. | `db.update_request()` |

#### Thumbnails & Configuration

| Function | Description | Maps to |
|---|---|---|
| `get_thumbnail_url(thumb_path)` | Returns a `file://` URL for the thumbnail that the webview can render. | Path conversion |
| `get_app_config()` | Returns all app configuration (language, theme, max workers, etc.). | `db.get_app_config()` |
| `set_app_config(key, value)` | Updates a single configuration value. | `db.set_app_config()` |

### 4.3 Backend Event Types

The following events are pushed from Python to the React frontend via `CustomEvent` dispatch. The React app listens with `window.addEventListener("scan:progress", handler)`.

| Event | Payload | Source Signal |
|---|---|---|
| `scan:progress` | `{current, total, phase}` | `Scanner.progress_updated` |
| `scan:file_discovered` | `{path, size}` | `Scanner.file_discovered` |
| `scan:hash_complete` | `{file_id, pixel_hash}` | `Scanner.hash_complete` |
| `scan:hash_batch` | `{count, duplicates_found}` | `Scanner.hash_complete_batch` |
| `scan:directory_hashed` | `{directory, file_count}` | `Scanner.directory_hashed` |
| `scan:duplicate_found` | `{pixel_hash, count}` | `Scanner.duplicate_found` |
| `scan:similarity_progress` | `{current, total}` | `Scanner.similarity_progress` |
| `scan:similarity_complete` | `{group_count}` | `Scanner.similarity_grouping_complete` |
| `scan:status` | `{status, message}` | `Scanner.status_message`, `scan_started`, `scan_paused`, `scan_resumed`, `scan_stopped`, `scan_complete`, `scan_error` |
| `exec:progress` | `{current, total, action, file_path}` | `PlanExecutor.progress` |
| `exec:complete` | `{success, summary}` | `PlanExecutor.complete` |
| `exec:error` | `{message, file_path}` | `PlanExecutor.error` |

---

## 5. Python Backend Architecture

The Python backend is the existing DejaView codebase. It is NOT a sidecar process — it runs in-process with pywebview as the application's primary runtime.

### 5.1 Scanner Pipeline

The scanner is a multi-pass QThread worker with a sophisticated state machine:

| Pass | Operation | Details |
|---|---|---|
| Pass 1: Discovery | File system walk | Symlink/junction guard, network reachability probe (5s timeout), incremental batch insertion (128-file batches), per-file discovery signals |
| Pass 2: Hashing | Size-filtered pixel hashing | Only hashes files whose size appears 2+ times (pre-filter). Sliding-window ThreadPoolExecutor with locality-aware submission. xxh128 pixel hash. Memory-based worker count scaling. Proportional throttling via `scan_delay_ms`. |
| Pass 3: Similarity (opt-in) | Perceptual hashing + grouping | Dual hashing (pixel_hash + pHash via `imagehash`). O(n²) Hamming distance on pHash representatives. Union-Find for transitive closure. Configurable threshold (default: 8 bits). |

**Pause/Resume State Machine:**
- `pause()` sets internal flag; scanner exits after current file
- `resume()` skips Pass 1, skips already-hashed files in Pass 2/3
- Session status persists across app restarts: `in_progress` → `paused` → `complete` | `stopped`
- On app restart with a `paused` session, the app navigates directly to the results screen with resume capability

### 5.2 Database Schema

The existing SQLite schema in `data/db.py` is the single source of truth. The Python backend is the sole writer. The React frontend accesses data exclusively through the API functions in Section 4.2.

**Database configuration:** WAL mode, foreign keys enabled, `check_same_thread=False` for cross-thread access.

| Table | Key Columns | Purpose |
|---|---|---|
| `sessions` | `id`, `name`, `created_at`, `status` | Scan session lifecycle |
| `session_folders` | `session_id`, `folder_path` | Scan scope (which folders to scan) |
| `files` | `id` (INTEGER PK), `session_id`, `path`, `size`, `modified_at`, `pixel_hash`, `hash_algorithm`, `thumbnail_path`, `status`, `scanned_at`, `perceptual_hash`, `width`, `height` | Scanned files with hash results |
| `file_actions` | `id`, `file_id`, `session_id`, `action` (keep/delete/ignore), `scope` (file/folder), `decided_at`, `executed_at` | User decisions with file or folder scope |
| `soft_deletes` | `id`, `session_id`, `file_id`, `original_path`, `trash_path`, `deleted_at`, `expires_at`, `recovered_at` | Soft-deleted files with 30-day recovery |
| `sync_config` | `local_username`, `gdrive_folder_id`, `gdrive_file_id`, `sync_enabled`, `export_privacy`, `pending_export`, `last_exported_at`, `last_imported_at`, `scan_delay_ms` | Google Drive sync configuration |
| `remote_peers` | `id`, `username`, `last_seen_at` | Known family peers |
| `remote_files` | `id`, `peer_id`, `pixel_hash`, `path`, `size`, `modified_at` | Files from peer exports |
| `requests` | `id`, `session_id`, `file_id`, `peer_username`, `direction`, `type`, `status`, `message`, `created_at`, `responded_at` | Photo request lifecycle |
| `app_config` | `language`, `theme`, `max_scan_workers`, `perf_logging` | Application preferences (typed columns with constraints) |
| `similarity_groups` | `id`, `session_id`, `threshold`, `created_at` | Similarity group sets |
| `similarity_group_members` | `group_id`, `file_id` | Files within similarity groups |

**Views:**
| View | Definition | Purpose |
|---|---|---|
| `duplicate_groups` | `SELECT session_id, pixel_hash, hash_algorithm, COUNT(*) AS file_count FROM files WHERE pixel_hash IS NOT NULL AND status = 'active' GROUP BY session_id, pixel_hash, hash_algorithm HAVING COUNT(*) > 1` | Always-fresh duplicate group aggregation |

**Key indexes:** `idx_files_session`, `idx_files_hash`, `idx_files_path`, `idx_files_status`, `idx_files_session_hash_status`, `idx_remote_files_hash`, `idx_file_actions_session`, `idx_file_actions_file`

### 5.3 Safety Invariants

**Master Copy Protection:** The last remaining copy of any `pixel_hash` must NEVER be marked for deletion. This invariant is enforced in:
- `core/selection.py` → `identify_master_copy()` for exact duplicate groups
- `core/similarity_selection.py` → same protection for similarity groups
- Must also be enforced in any auto-resolve UI logic

**Soft-Delete Recovery:** All file deletions go through `core/trash.py` which:
- Moves files to `%APPDATA%\DejaView\.dejaview_trash\`
- Records `trash_path` for reliable recovery
- Auto-purges expired items after 30 days
- Tracks `recovered_at` for recovery history

### 5.4 Selection Presets

Available presets for automated duplicate resolution:

| Preset | Keep Criteria | Available For |
|---|---|---|
| `KEEP_HIGHEST_RESOLUTION` | Highest `width × height` | Exact + Similarity |
| `KEEP_LARGEST_FILE` | Largest `size` in bytes | Exact + Similarity |
| `KEEP_NEWEST` | Most recent `modified_at` | Exact + Similarity |
| `KEEP_OLDEST` | Earliest `modified_at` | Exact + Similarity |
| `KEEP_SHORTEST_PATH` | Shortest file path (closest to root) | Exact + Similarity |

---

## 6. Cloud Sharing Layer

### 6.1 Phase 1 — Google Drive Sync (Current Implementation)

Cross-family duplicate detection uses Google Drive as a shared storage medium for hash exports. This is already implemented in `data/sync.py`.

| Property | Specification |
|---|---|
| Authentication | OAuth 2.0 desktop flow via `google-auth-oauthlib` |
| Sync Mechanism | JSON file exchange via a shared Google Drive folder |
| Export Content | Pixel hashes and metadata only (never full photos). Privacy levels: `hash_only`, `filename`, `full_path` |
| Import Validation | Schema validation, 10 MB file size cap, 100K entry cap, username format check |
| Offline Support | `pending_export` flag; syncs on next connection |
| Credential Storage | Restricted file permissions on stored OAuth tokens |

### 6.2 Phase 2 — Custom Cloud Backend (Future)

A custom REST API backend for real-time family matching, notifications, and direct file transfers. This is a separate project with its own requirements document.

**Planned capabilities** (not yet implemented):

| Capability | Description |
|---|---|
| Family Groups | Server-managed groups with invite links; each member registers their hash set |
| Real-Time Matching | Server compares hashes across family members; pushes match results via WebSocket or polling |
| File Transfer | Approved transfers via temporary pre-signed URLs (S3/R2); no permanent photo storage |
| Authentication | OAuth 2.0 / OpenID Connect — Google Sign-In or Microsoft Account |

**Planned API Endpoints:**

| Endpoint | Description |
|---|---|
| `POST /family/create` | Create a new family group; returns invite code |
| `POST /family/join` | Join a family group via invite code |
| `POST /hashes/sync` | Upload local hash set for cross-library matching |
| `GET /matches` | Retrieve cross-family duplicate matches |
| `POST /requests/send` | Send a sharing request to a family member |
| `GET /requests/inbox` | Retrieve pending incoming requests |
| `POST /requests/{id}/respond` | Approve or decline a request; triggers file transfer if approved |
| `GET /transfers/{id}/status` | Check status of an approved file transfer |

> **Note:** When Phase 2 is implemented, `@tanstack/react-query` should be added to the frontend dependencies for caching, retry, and optimistic updates on cloud API calls.

### 6.3 Privacy Considerations

- Only perceptual hashes and metadata are shared — never full-resolution photos
- Photo transfers occur only after explicit approval from both parties
- In Phase 2, transferred files use temporary pre-signed URLs that expire after download
- Users can leave a family group at any time; their hashes are purged within 24 hours
- All cloud communication uses TLS 1.3; hashes are encrypted at rest

---

## 7. Internationalization

The existing application has 324+ Hungarian translations maintained alongside English. The migration must preserve full i18n support.

### 7.1 Frontend i18n Stack

| Property | Specification |
|---|---|
| Library | `i18next` + `react-i18next` |
| Translation Format | JSON files (`en.json`, `hu.json`) in `frontend/src/i18n/` |
| String Wrapping | All UI strings use `t('key')` or `<Trans>` component |
| Fallback | English (en) is the fallback language |
| Language Switch | Calls `set_app_config('language', code)` on the Python backend; reloads i18next |

### 7.2 Migration Strategy

The existing Qt `.ts` XML translation files (`resources/i18n/app.ts`, `resources/i18n/app_hu.ts`) contain `<source>` and `<translation>` elements that can be programmatically converted to i18next JSON format:

```
Qt XML:  <message><source>Scan Complete</source><translation>Szkennelés kész</translation></message>
i18next: { "scan_complete": "Szkennelés kész" }
```

A one-time migration script should convert these files. The original `.ts` files are retained for reference.

---

## 8. Project Structure

```
dejaview/
├── core/                        — UNCHANGED
│   ├── hasher.py                — pixel hash (xxh128) + pHash + thumbnail generation
│   ├── scanner.py               — multi-pass QThread scanner (discovery → hashing → similarity)
│   ├── executor.py              — PlanExecutor QThread (executes file actions)
│   ├── trash.py                 — soft-delete file operations (move, recover, purge)
│   ├── selection.py             — smart selection presets + master copy protection
│   ├── similarity.py            — pHash similarity grouping (Union-Find)
│   ├── similarity_selection.py  — similarity-specific presets
│   └── perf_monitor.py          — performance telemetry
├── data/                        — UNCHANGED
│   ├── db.py                    — all SQLite access (sole DB owner, 1,623 lines)
│   ├── export.py                — hash export/import (JSON, validated)
│   └── sync.py                  — Google Drive sync
├── backend/                     — NEW: pywebview API bridge
│   └── api.py                   — exposes Python functions to JS via pywebview bridge
├── frontend/                    — NEW: React UI
│   ├── src/
│   │   ├── screens/             — Dashboard, BrowseResults, PlanReview, Execution,
│   │   │                          Similarity, DuplicatesBin, Family, Requests, Settings
│   │   ├── components/          — PhotoThumb, MetaRow, CompareView, FilterSidebar,
│   │   │                          BatchActions, ProgressBar, RequestCard
│   │   ├── stores/              — Zustand: useScanStore, useReviewStore, useBinStore,
│   │   │                          useFamilyStore, useSettingsStore
│   │   ├── hooks/               — usePyBridge, useScanProgress, useVirtualGroups
│   │   ├── i18n/                — en.json, hu.json
│   │   └── types/               — TypeScript interfaces matching Python API contracts
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── package.json
├── resources/i18n/              — RETAINED for migration reference (Qt .ts/.qm files)
├── tests/                       — UNCHANGED (pytest, in-memory SQLite fixtures)
│   ├── unit/                    — test_hasher.py, test_db.py, test_similarity.py, etc.
│   ├── integration/             — scanner state tests
│   └── fixtures/                — canonical test images (gray 128,128,128)
├── main.py                      — pywebview window creation + backend.api exposure
├── dejaview.spec                — PyInstaller (updated to bundle frontend/dist/)
└── requirements.txt             — add pywebview, pystray; keep all existing deps
```

---

## 9. Wireframe-to-Production Mapping

The wireframe screens map to production data sources via the Python Backend API (Section 4.2).

| Screen | Python API Functions | Key Integration |
|---|---|---|
| **Dashboard** | `get_scan_summary`, `get_sessions`, `get_app_config` | Persistent activity hub with status cards (Local Duplicates, Similar Images, Family Photos, Pending Requests). Not a one-time "Scan Complete" view. |
| **Scan Progress** | `start_scan` + `scan:*` events | Real-time progress with pause/resume controls. Phases displayed per scanner pass. |
| **Browse Results** | `get_duplicate_groups` (paginated), `get_group_detail`, `set_file_action` | List/tree + detail split view (NOT a linear stepper). Virtualized via `@tanstack/react-virtual`. Filter sidebar for folder, date range, size. Batch actions toolbar with selection presets. |
| **Plan Review** | `get_plan_summary` | Safety gate before execution. Full list of all planned changes. Impact totals (file count, size). Cancel individual actions. Confirmation dialog before proceeding. |
| **Execution** | `execute_plan` + `exec:*` events | Progress bars per stage (Local Cleanup, Cloud Sync). Real-time scrolling log. ETA display. "Minimize to Tray" support. |
| **Similarity Review** | `get_similarity_groups`, `apply_similarity_preset`, `recommend_keeper` | Side-by-side comparison. Similarity threshold display. Selection presets. Master copy indicators. |
| **Duplicates Bin** | `get_bin_items`, `restore_from_bin`, `permanent_delete`, `purge_expired` | 30-day retention countdown. Restore to original location. Batch permanent delete. |
| **Family Cross-Library** | `export_hashes`, `sync_drive`, `get_remote_peers` | Google Drive sync (Phase 1). Peer hash comparison. Request actions. |
| **Family Requests** | `get_requests`, `respond_to_request` | Incoming/outgoing request lifecycle. Approve/decline with status tracking. |
| **Settings** | `get_app_config`, `set_app_config` | Language selector, theme, max scan workers, scan throttling, Google Drive sync config. |

---

## 10. Development Environment Setup

### 10.1 Required Tools

| Tool | Version |
|---|---|
| Node.js | v20 LTS or later |
| Python | 3.12+ |
| OS | Windows 10/11 (primary target) |
| WebView | Microsoft Edge WebView2 (bundled with Windows 10 21H2+ and Windows 11) |
| IDE | VS Code recommended with ESLint, Tailwind CSS IntelliSense, and Python extensions |

### 10.2 Bootstrap Commands

```bash
# Frontend setup
cd dejaview/frontend
npm install
npm run dev  # Vite dev server on localhost:5173

# Backend setup
cd dejaview
pip install pywebview pystray
python main.py --dev  # Opens pywebview pointing at Vite dev server (localhost:5173)

# Frontend dependencies (initial install)
npm install react react-dom react-router-dom zustand tailwindcss
npm install @tanstack/react-virtual react-compare-slider lucide-react sonner
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-tooltip
npm install date-fns zod i18next react-i18next

# Production build
cd dejaview/frontend && npm run build   # outputs to frontend/dist/
cd dejaview && pyinstaller dejaview.spec  # bundles Python + frontend/dist/
```

### 10.3 Development Workflow

1. **Frontend development:** `npm run dev` starts Vite with HMR. Changes to React components reflect instantly in the pywebview window.
2. **Backend development:** Restart `python main.py --dev` after Python changes. No frontend rebuild needed.
3. **Testing:** `python -m pytest tests/unit/ --no-cov -q` runs all unit tests (backend unchanged, no PyQt6 needed for unit tests).
4. **API testing:** Open browser devtools in the pywebview window and call `window.pywebview.api.get_scan_summary(1)` directly.

---

## 11. Next Steps

1. Scaffold `frontend/` with Vite + React + TypeScript + Tailwind.
2. Create `backend/api.py` exposing existing Python functions to pywebview.
3. Update `main.py` to create pywebview window and expose the API.
4. Implement Dashboard screen (React) calling Python API.
5. Implement Browse Results screen with virtual scrolling and filter sidebar.
6. Implement Plan Review + Execution screens.
7. Implement Similarity Review screen.
8. Implement Duplicates Bin, Family, Requests, and Settings screens.
9. Migrate i18n translations (Qt XML → i18next JSON).
10. Update PyInstaller spec to bundle `frontend/dist/`.
11. End-to-end testing of full workflow: scan → browse → plan → review → execute → bin.
