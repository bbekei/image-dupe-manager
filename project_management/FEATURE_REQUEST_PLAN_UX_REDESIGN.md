# DejaView — Feature Request Plan: UX Redesign — Family Sharing & Local Cleanup Journey

## Overview

Redesign the DejaView user experience around the "Sync-Plan-Commit-Fulfill" journey defined in `UX_REQUIREMENTS.md`. Today the app is a linear tool (scan → browse → plan). The redesign transforms it into a family-oriented hub with a Dashboard entry point, five purpose-built screens, advanced high-volume cleanup, and a social photo-request workflow. The plan is organized into six consequential phases, each delivering a usable increment.

## Problem

Today the app launches directly into a folder panel + scan workflow. There is no central navigation hub, no way to browse "Family Treasures" (photos that family members have but you don't), no plan review gate before destructive operations, no execution progress screen, and no support for requesting photos from relatives. The existing cleanup flow works but lacks the filtering, clustering, and smart selection needed for 100k+ image libraries. Files marked for deletion have no soft-delete recovery path.

## User Experience

### Target Screen Flow

```
                    ┌──────────────────────┐
           ┌────── │  1. DASHBOARD (Home)  │ ──────┐
           │       │  Status Cards + Feed  │       │
           │       └──────────┬───────────┘       │
           │                  │                    │
           v                  v                    v
┌─────────────────┐  ┌────────────────┐  ┌──────────────────┐
│ 2. LOCAL CLEANUP│  │ 3. FAMILY      │  │  Request Approval │
│ Scan + Filter + │  │ DISCOVERY      │  │  (Grant / Deny)   │
│ Cluster + Batch │  │ Grid + Request │  └──────────────────┘
└────────┬────────┘  └────────┬───────┘
         │                    │
         v                    v
   ┌──────────────┐    (items added to
   │ PLANNING     │     request queue)
   │ Keep/Del/Ign │          │
   └──────┬───────┘          │
          │                  │
          v                  v
   ┌────────────────────────────────┐
   │  4. PLAN REVIEW ("Cart")      │
   │  Left: Deletions  Right: Reqs │
   │  Impact totals + Commit btn   │
   └──────────┬─────────────────────┘
              │
              v
   ┌────────────────────────────────┐
   │  5. EXECUTION & PROGRESS      │
   │  Progress bars + Real-time log│
   │  Minimize to tray             │
   └──────────┬─────────────────────┘
              │
              v
         Back to Dashboard
```

### Navigation Architecture Change

**Current:** QSplitter with ad-hoc hide/show panel swaps in MainWindow (886 lines).

**Target:** `QStackedWidget` managed by a lightweight `NavigationController` with a back-stack. FolderPanel and ScanControl become contextual (visible only on relevant screens). MainWindow becomes a thin shell: menu bar + NavigationController + status bar.

### Design Principles (from requirements)

- **Safety First:** No file deleted without passing Plan Review (Screen 4)
- **No Dead Ends:** Every screen has "Back to Dashboard" or "Cancel"
- **Visual Consistency:** Red = Deletion, Green = Requests/Additions
- **Nondestructive:** Soft-delete to `.dejaview_trash` with 30-day recovery
- **Performance:** Virtual scrolling for 100k+ images, on-demand thumbnails

---

## Solution

### Phase 1: Navigation Shell & Dashboard (Foundation)

**Priority: P0 — Everything else depends on this.**

Replace the ad-hoc splitter-swap navigation with a structured `QStackedWidget` + `NavigationController`. Add the Dashboard as the app's entry point. Extract the existing scan/results flow into a self-contained cleanup screen container.

#### 1.1 NavigationController (`ui/navigation.py` — NEW)

Plain QObject wrapping a QStackedWidget:
- `register_screen(name, widget)` / `navigate_to(name)` / `go_back()`
- Maintains a back-stack (list of screen names)
- Emits `screen_changed(str)` so menu bar and bottom bar adapt visibility
- Screen names map to `WorkflowPhase` enum values

#### 1.2 Dashboard (`ui/dashboard.py` — NEW)

Three clickable status summary cards in a horizontal layout:
- **"Local Duplicates"** — count + potential space savings → navigates to cleanup
- **"Family Photos"** — count of remote-only hashes → navigates to discovery (placeholder until Phase 4)
- **"Pending Requests"** — count → navigates to request list (placeholder until Phase 6)

Below cards: Sync Status row ("Last synced: [time]" + "Sync Now" button) and a "Start New Scan" quick action.

Cards refresh from DB on each show via snapshot queries.

#### 1.3 Cleanup Screen Container (`ui/cleanup_screen.py` — NEW)

Absorbs the existing FolderPanel + ResultsPanel + scan flow from MainWindow:
- Internal QSplitter (FolderPanel left, right-pane right)
- Owns all existing panel-swap methods (`_show_scan_progress`, `_hide_scan_progress`, `_show_planning_panel`, etc.)
- ~200 lines extracted from `main_window.py`

#### 1.4 MainWindow Refactor (`ui/main_window.py` — MAJOR MODIFY)

- Replace QSplitter central area with QVBoxLayout → QStackedWidget + ScanControl
- Register screens: dashboard, cleanup, (placeholders for plan_review, execution, discovery)
- ScanControl visibility toggled per screen (only on cleanup)
- FolderPanel moves inside CleanupScreen's own splitter
- Session restore: start on Dashboard if previous session complete, resume on cleanup if paused

#### 1.5 Supporting Changes

- `ui/workflow.py` — Add `DASHBOARD` and `FAMILY_DISCOVERY` phases to enum
- `data/db.py` — Add `get_family_treasure_count(session_id)` query
- `resources/i18n/` — Dashboard + Navigation strings in both languages

#### Files

| File | Change |
|------|--------|
| `ui/navigation.py` | **NEW** — NavigationController with back-stack |
| `ui/dashboard.py` | **NEW** — Status cards, sync row, quick actions |
| `ui/cleanup_screen.py` | **NEW** — Container for existing scan/results/planning flow |
| `ui/main_window.py` | **MAJOR MODIFY** — Thin shell with QStackedWidget |
| `ui/workflow.py` | **MODIFY** — Add DASHBOARD, FAMILY_DISCOVERY phases |
| `data/db.py` | **MODIFY** — Add `get_family_treasure_count()` |
| `resources/i18n/app.ts` | **MODIFY** — EN strings |
| `resources/i18n/app_hu.ts` | **MODIFY** — HU strings |
| `tests/unit/test_navigation.py` | **NEW** — Back-stack, screen switching |
| `tests/unit/test_dashboard.py` | **NEW** — Card counts, navigation signals |

---

### Phase 2: Soft-Delete Infrastructure & Plan Review Screen

**Priority: P0 — Required before any file operations can occur.**

Build the safety infrastructure (soft-delete to `.dejaview_trash`) and the Plan Review screen — the "final gate" before any file system changes.

#### 2.1 Soft-Delete Module (`core/trash.py` — NEW)

- `soft_delete(file_path, session_id)` — move to `.dejaview_trash/{session_id}/`
- `recover(trash_path, original_path)` — restore from trash
- `purge_expired(trash_root, max_age_days=30)` — remove expired files
- Only module that performs destructive filesystem operations

#### 2.2 DB: `soft_deletes` Table (`data/db.py` — MODIFY)

```sql
CREATE TABLE IF NOT EXISTS soft_deletes (
    id            INTEGER PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES sessions(id),
    file_id       INTEGER NOT NULL REFERENCES files(id),
    original_path TEXT NOT NULL,
    trash_path    TEXT NOT NULL,
    deleted_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    recovered_at  TEXT,
    UNIQUE (session_id, file_id)
);
```

Methods: `record_soft_delete`, `record_recovery`, `get_active_soft_deletes`, `get_expired_soft_deletes`.

#### 2.3 Plan Review Screen (`ui/plan_review.py` — NEW)

Two-column layout per UX_SCREEN_REQUIREMENTS Screen 4:

```
[< Back to Planning]      Plan Review      [Clear Plan]
─────────────────────────────────────────────────────────
│ FILES TO DELETE (32)    │ FILES TO REQUEST (5)        │
│                         │                              │
│ [X] > /photos/backup/   │ (empty — populated Phase 4)  │
│ [X]   img1.jpg          │                              │
│ [X]   img2.jpg          │                              │
│ [X] /photos/dup3.jpg    │                              │
─────────────────────────────────────────────────────────
│ Storage Change: -1.2 GB │ Network Activity: +150 MB   │
│                         [Apply Changes >>]             │
─────────────────────────────────────────────────────────
```

- Left column: file_actions where `action='delete'`, with "X" to remove from plan
  - **Folder-level actions:** When an entire folder was selected for deletion in Planning mode (`scope='folder'`), display the folder as a collapsible group with its children. The "X" on the folder removes the entire folder decision.
  - **File-level actions:** Individual files shown flat with their own "X" button.
- Right column: request queue (placeholder, populated in Phase 4)
- Impact totals: sum of file sizes
- "Apply Changes" emits `commit_requested` (wired in Phase 3)

New DB method: `get_plan_summary(session_id)` → `{delete_count, delete_bytes, keep_count, folder_count}`.

#### 2.4 Wire PlanningPanel → Plan Review

The existing `_review_btn` in `planning_panel.py` emits `review_requested` but currently goes nowhere. Wire it through NavigationController to open Plan Review.

#### Files

| File | Change |
|------|--------|
| `core/trash.py` | **NEW** — Soft-delete file operations |
| `ui/plan_review.py` | **NEW** — Two-column review screen |
| `data/db.py` | **MODIFY** — `soft_deletes` table + CRUD + `get_plan_summary()` |
| `ui/planning_panel.py` | **MODIFY** — Wire review button to navigation |
| `ui/main_window.py` | **MODIFY** — Register plan_review screen |
| `resources/i18n/app.ts` | **MODIFY** |
| `resources/i18n/app_hu.ts` | **MODIFY** |
| `tests/unit/test_trash.py` | **NEW** |
| `tests/unit/test_plan_review.py` | **NEW** |
| `tests/unit/test_db.py` | **MODIFY** — soft_deletes tests |

---

### Phase 3: Execution Screen & File Operations Engine

**Priority: P0 — Completes the local cleanup end-to-end pipeline.**

Implement the Execution screen (Screen 5) and the file operations engine that performs soft-deletes and uploads the updated JSON export.

#### 3.1 PlanExecutor (`core/executor.py` — NEW)

QThread following the existing Scanner pattern. Executes two **sequential** stages:

**Stage A — Local Cleanup:**
- Iterates file_actions where `action='delete'`
- Calls `core/trash.soft_delete()` for each file
- Records in `soft_deletes` table, marks `file_actions.executed_at`
- Emits progress signals: `progress_updated`, `task_started`, `log_message`

**Stage B — Cloud Sync (after all local operations complete):**
- Generates updated JSON export via `data.export.build_export_payload()`
- Uploads to Google Drive via DriveSync (single upload at end, not per-file)
- Emits `execution_complete(success_count, error_count)`

The two stages run sequentially, never in parallel. The JSON export reflects the final state after all local file operations have completed.

#### 3.2 Execution Screen (`ui/execution_screen.py` — NEW)

Per UX_SCREEN_REQUIREMENTS Screen 5:
- **Sequential** progress bars for "Local Cleanup" (active first) then "Cloud Sync" (starts after cleanup completes)
- Collapsible real-time log (scrolling text area)
- "Minimize to Tray" button
- On completion: "Done" button → back to Dashboard with refreshed card counts

#### 3.3 System Tray (`ui/tray.py` — NEW)

Minimal QSystemTrayIcon: show during background execution, balloon notification on completion, click to restore window.

#### 3.4 Startup Trash Cleanup (`main.py` — MODIFY)

Call `trash.purge_expired()` during app startup to enforce the 30-day recovery window.

#### 3.5 Plan Review → Execution Wiring

"Apply Changes" in Plan Review:
1. Confirmation dialog: "Move N files to .dejaview_trash. Recoverable for 30 days."
2. Create PlanExecutor, navigate to execution screen, start thread
3. Wire signals (same pattern as Scanner → ScanProgressWidget)

#### Files

| File | Change |
|------|--------|
| `core/executor.py` | **NEW** — PlanExecutor QThread |
| `ui/execution_screen.py` | **NEW** — Progress bars, log, completion |
| `ui/tray.py` | **NEW** — System tray icon |
| `ui/plan_review.py` | **MODIFY** — Wire Apply Changes to executor |
| `ui/main_window.py` | **MODIFY** — Register execution screen, wire lifecycle |
| `main.py` | **MODIFY** — Trash purge at startup |
| `data/db.py` | **MODIFY** — `mark_file_action_executed()` |
| `resources/i18n/app.ts` | **MODIFY** |
| `resources/i18n/app_hu.ts` | **MODIFY** |
| `tests/unit/test_executor.py` | **NEW** |

---

### Phase 4: Family Discovery Screen & Request Queue

**Priority: P1 — Enables the "social" dimension of DejaView.**

Implement Screen 3 (Family Discovery) and the request queue system. Users browse "Family Treasures" and request photos from relatives.

#### 4.1 DB: `requests` Table (`data/db.py` — MODIFY)

```sql
CREATE TABLE IF NOT EXISTS requests (
    id           INTEGER PRIMARY KEY,
    session_id   INTEGER NOT NULL REFERENCES sessions(id),
    pixel_hash   TEXT NOT NULL,
    target_peer  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','denied','fulfilled','cancelled')),
    requested_at TEXT NOT NULL,
    responded_at TEXT,
    fulfilled_at TEXT,
    UNIQUE (session_id, pixel_hash, target_peer)
);
```

Methods: `create_request`, `create_requests_batch`, `get_requests_for_session`, `get_pending_requests_count`, `update_request_status`, `cancel_request`, `get_incoming_requests`.

#### 4.2 Family Discovery Screen (`ui/family_discovery.py` — NEW)

Grid view (QListView in IconMode with custom QAbstractListModel for virtual scrolling):

```
[< Dashboard]     Family Photos     [Request Selected (0)]
──────────────────────────────────────────────────────────
Filter: [All Providers v] [Date: Any v] [Not Requested v]
──────────────────────────────────────────────────────────
│ [thumb]    │ [thumb]    │ [thumb]    │ [thumb]    │
│ From: Bob  │ From: Mom  │ From: Bob  │ From: Dad  │
│ [Heart]    │ [Heart]    │ [Heart]    │ [Heart]    │
──────────────────────────────────────────────────────────
Showing 156 family photos from 3 providers
```

- Provider filter from `remote_peers` table
- Heart button toggles request (INSERT/DELETE in `requests`)
- Bulk select via Ctrl+Click + "Request Selected" button
- Placeholder thumbnails (remote files have no local thumbnails)

Data query: `get_family_treasures(session_id)` — remote_files NOT IN local files, joined with peer info.

#### 4.3 Export Enhancement (`data/export.py` — MODIFY)

Add `requests_outgoing` section to export JSON. Update `import_payload` to parse incoming requests from peer JSONs.

#### 4.4 Plan Review Enhancement (`ui/plan_review.py` — MODIFY)

Populate right column with pending requests from `requests` table. Each row: peer name + hash + "X" to cancel.

#### 4.5 Dashboard Enhancement (`ui/dashboard.py` — MODIFY)

Wire Family Photos card to actual count. Wire Requests card to `get_pending_requests_count()`.

#### Files

| File | Change |
|------|--------|
| `ui/family_discovery.py` | **NEW** — Grid view of family treasures |
| `data/db.py` | **MODIFY** — `requests` table + CRUD + `get_family_treasures()` |
| `data/export.py` | **MODIFY** — `requests_outgoing` in export schema |
| `ui/plan_review.py` | **MODIFY** — Right column with requests |
| `ui/dashboard.py` | **MODIFY** — Wire family + request cards |
| `ui/main_window.py` | **MODIFY** — Register family_discovery screen |
| `resources/i18n/app.ts` | **MODIFY** |
| `resources/i18n/app_hu.ts` | **MODIFY** |
| `tests/unit/test_family_discovery.py` | **NEW** |
| `tests/unit/test_db.py` | **MODIFY** — requests CRUD tests |
| `tests/unit/test_export.py` | **MODIFY** — Export with requests |

---

### Phase 5: Advanced Cleanup — Filtering, Clusters, Smart Selection

**Priority: P1 — Transforms local cleanup for 100k+ scale.**

Upgrade the existing ResultsPanel from a simple tree view into the "High-Volume Mode" (Screen 2). Adds filtering sidebar, duplicate cluster grouping, batch selection, smart selection engine, and the Master Copy badge.

#### 5.1 Filtering Sidebar (`ui/filter_sidebar.py` — NEW)

Collapsible sidebar replacing current radio buttons:
- **Group by:** Directory / Hash Group
- **Date Range:** From/To date pickers (EXIF Date Taken or File Created)
- **File Type:** Checkboxes for .jpg, .png, .raw, .heic, etc.
- **Redundancy Level:** Min copies spinner (show worst offenders first)
- **Full Duplicate Folders Only:** Toggle to show only folders where every file is a duplicate (all children have duplicates elsewhere). Leverages the existing `compute_folder_duplication()` logic in `ResultsTreeModel`.
- **Family Safety:** Toggle "Only show files backed up in Family"
- **Sort by:** Waste (total size) / Path Length / Copies Count

Emits `filters_changed(FilterCriteria)` signal with a dataclass payload.

#### 5.2 Cluster View Model (`ui/cluster_model.py` — NEW)

QAbstractItemModel grouping files by pixel_hash instead of by directory:

```
│ Cluster            │ Copies │ Total Size │ Action              │
│ > [thumb] img.jpg  │ 4 in 3 dirs │ 45 MB │ [Keep Best] [Keep Newest] │
│   C:/Photos/img.jpg (12 MB, 4032x3024) ★ Master │ [Keep][Del][Ign] │
│   C:/Backup/img.jpg (12 MB, 4032x3024)          │ [Keep][Del][Ign] │
│   D:/Dump/img(1).jpg (10 MB, 3024x3024)         │ [Keep][Del][Ign] │
```

Cluster-level actions ("Keep Best", "Keep Newest", "Keep Deepest Path") apply to all files in the cluster.

#### 5.3 Smart Selection Engine (`core/selection.py` — NEW)

```python
class SelectionPreset(Enum):
    KEEP_HIGHEST_RESOLUTION = auto()
    KEEP_NEWEST = auto()
    KEEP_DEEPEST_PATH = auto()
    KEEP_LARGEST_FILE = auto()
```

- `apply_selection_preset(db, session_id, preset, filter_criteria)` → marks files
- **Master Copy protection (always enforced):** The engine unconditionally refuses to mark the last remaining copy of any hash for deletion. This is a hard safety rule, not a user-togglable option. The app is a deduplication tool, not a general file manager.
- **Master Copy badge:** Identifies the highest-quality version per cluster (resolution × file size). Applied at the **folder level** when possible: if an entire folder contains the "best" copies, the folder row itself gets the Master Copy badge. When two folders are completely identical (same hashes, same quality), one is chosen randomly as the Master and the choice is stable within a session (seeded by folder path hash).

#### 5.4 Batch Selection Tools (`ui/batch_actions.py` — NEW)

- "Select All in This Folder" — mark all files under a folder
- "Select by Pattern" — regex/glob dialog (e.g., `*_copy*`, `*(1)*`)

Note: Master Copy protection is always enforced (see 5.3), not a user toggle.

#### 5.5 Results Panel Enhancement (`ui/results_panel.py` — MODIFY)

- Toggle between "Tree View" (existing) and "Cluster View" (new)
- Global search bar (filename fragment) at the top
- Statistical header: "2,405 groups selected | 1.2 GB potential savings"
- "Smart Select" button opening preset picker dialog

#### 5.6 Virtual Scrolling

For cluster model: use `QAbstractItemModel` with lazy loading from DB (not `QStandardItemModel` which loads all rows into memory). Thumbnails loaded on-demand via background thread with LRU cache.

#### Files

| File | Change |
|------|--------|
| `ui/filter_sidebar.py` | **NEW** — Collapsible filtering sidebar |
| `ui/cluster_model.py` | **NEW** — Hash-group-based cluster model |
| `core/selection.py` | **NEW** — Smart selection presets + Master Copy logic |
| `ui/batch_actions.py` | **NEW** — Batch selection toolbar |
| `ui/results_panel.py` | **MODIFY** — Cluster toggle, search, smart select, stats header |
| `ui/cleanup_screen.py` | **MODIFY** — Integrate filter sidebar |
| `ui/results_model.py` | **MODIFY** — Add `ROLE_MASTER_COPY` |
| `data/db.py` | **MODIFY** — Filtered duplicate queries (date, extension, min copies) |
| `resources/i18n/app.ts` | **MODIFY** |
| `resources/i18n/app_hu.ts` | **MODIFY** |
| `tests/unit/test_cluster_model.py` | **NEW** |
| `tests/unit/test_selection.py` | **NEW** |
| `tests/unit/test_filter_sidebar.py` | **NEW** |

---

### Phase 6: Activity Feed, Request Fulfillment & Polish

**Priority: P2 — Completes the social workflow and adds polish.**

Add the Family Activity Feed on the Dashboard, request fulfillment (approve/deny/upload), trash recovery UI, path exclusion protection, and privacy zones.

#### 6.1 DB: `activity_log` + `protected_paths` Tables

```sql
CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'scan_complete','sync_complete','request_sent','request_received',
        'request_fulfilled','files_deleted','files_recovered')),
    summary    TEXT NOT NULL,
    details    TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS protected_paths (
    id          INTEGER PRIMARY KEY,
    path_prefix TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);
```

#### 6.2 Activity Feed (`ui/activity_feed.py` — NEW)

QListWidget embedded below Dashboard cards. Shows 20 most recent events with icons (scan, sync, heart, trash, restore).

#### 6.3 Request Fulfillment (`ui/request_list.py` — NEW)

Incoming request approval screen: "Mom wants: photo_abc [Approve] [Deny]". On approve: locate local file by hash, upload to `Shared_Transfers/For_[Requester]/` on Google Drive.

#### 6.3b Fulfilled Request Ingestion (`data/sync.py` — MODIFY)

When the app detects fulfilled requests (files placed in `Shared_Transfers/For_[Me]/` on Google Drive):
- Download the file from Drive
- Save to a DejaView subfolder inside the default Windows Pictures folder (e.g., `%USERPROFILE%\Pictures\DejaView\From_[PeerName]\`)
- Update the request status to `fulfilled` in the DB
- Log the event to `activity_log`

The target folder is resolved via `pathlib.Path.home() / "Pictures" / "DejaView" / f"From_{peer_name}"` with automatic directory creation.

#### 6.4 Trash Recovery (`ui/trash_recovery.py` — NEW)

List of soft-deleted files with "Recover" button. Accessible from File menu or Settings.

#### 6.5 Path Exclusion

Right-click context menu on folders: "Always Keep This Folder" → inserts into `protected_paths`. Smart selection engine (Phase 5) checks this table before marking files.

#### 6.6 Sync Enhancement (`data/sync.py` — MODIFY)

- Detect incoming requests in downloaded peer JSONs
- Detect fulfilled requests (files in `Shared_Transfers/For_[Me]/`)
- Log all events to `activity_log`

#### Files

| File | Change |
|------|--------|
| `ui/activity_feed.py` | **NEW** |
| `ui/request_list.py` | **NEW** |
| `ui/trash_recovery.py` | **NEW** |
| `data/db.py` | **MODIFY** — `activity_log` + `protected_paths` tables |
| `data/sync.py` | **MODIFY** — Request fulfillment, activity logging |
| `data/export.py` | **MODIFY** — `requests_incoming` parsing |
| `ui/dashboard.py` | **MODIFY** — Activity feed widget, incoming requests card |
| `ui/results_panel.py` | **MODIFY** — "Always Keep" context menu |
| `core/selection.py` | **MODIFY** — Respect `protected_paths` |
| `ui/main_window.py` | **MODIFY** — Register recovery screen, activity hooks |
| `resources/i18n/app.ts` | **MODIFY** |
| `resources/i18n/app_hu.ts` | **MODIFY** |
| `tests/unit/test_activity_feed.py` | **NEW** |
| `tests/unit/test_request_fulfillment.py` | **NEW** |
| `tests/unit/test_trash_recovery.py` | **NEW** |

---

## Phase Dependency Graph

```
Phase 1: Navigation Shell + Dashboard         ← FOUNDATION
    │
    v
Phase 2: Soft-Delete + Plan Review            ← SAFETY GATE
    │
    v
Phase 3: Execution Screen + File Ops          ← COMPLETES LOCAL PIPELINE
    │
    ├──► Phase 4: Family Discovery + Requests  ← SOCIAL DIMENSION
    │
    ├──► Phase 5: Advanced Cleanup             ← HIGH-VOLUME SCALE
    │
    v
Phase 6: Activity Feed + Fulfillment + Polish ← NEEDS ALL ABOVE
```

Phases 4 and 5 can run in parallel after Phase 3. Phase 5 is higher priority for the core use case (local dedup at scale).

---

## Risk Assessment

| Risk | Phase | Mitigation |
|------|-------|------------|
| MainWindow refactor breaks existing features | 1 | Extract CleanupScreen as a pure refactor first, validate all tests pass, then add NavigationController |
| QStandardItemModel can't handle 100k items | 5 | Replace with QAbstractItemModel + lazy DB loading in the cluster model; keep existing model for tree view |
| Google Drive file upload (not just JSON metadata) | 6 | Existing sync.py only handles JSON; file upload to `Shared_Transfers/` folders is new capability |
| i18n drift | All | Add both .ts files in every phase; never defer translations |

---

## Execution Tracking

Per `CONVENTIONS.md`, each phase shall have a corresponding execution log file created at the start of implementation and updated continuously as work progresses:

| Phase | Plan File | Execution Log |
|-------|-----------|---------------|
| 1 | This file | `FEATURE_REQUEST_EXECUTION_UX_PHASE_1.md` |
| 2 | This file | `FEATURE_REQUEST_EXECUTION_UX_PHASE_2.md` |
| 3 | This file | `FEATURE_REQUEST_EXECUTION_UX_PHASE_3.md` |
| 4 | This file | `FEATURE_REQUEST_EXECUTION_UX_PHASE_4.md` |
| 5 | This file | `FEATURE_REQUEST_EXECUTION_UX_PHASE_5.md` |
| 6 | This file | `FEATURE_REQUEST_EXECUTION_UX_PHASE_6.md` |

Each execution log tracks: task status (with `⬜`/`✅ Done` icons), what was actually done (not just what was planned), artifacts created, test results, and any deviations from the plan. Completed execution logs are moved to `project_management/done/`.

---

## Task Log

### Stage 1: Navigation Shell & Dashboard (Phase 1)

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Create `ui/navigation.py` — NavigationController | ⬜ | QObject + QStackedWidget + back-stack |
| 1.2 | Create `ui/dashboard.py` — Status cards + sync row | ⬜ | 3 clickable cards, sync status, quick actions |
| 1.3 | Create `ui/cleanup_screen.py` — Extract scan/results flow | ⬜ | Move ~200 lines from main_window.py |
| 1.4 | Refactor `ui/main_window.py` — Thin navigation shell | ⬜ | QStackedWidget replaces splitter, ScanControl contextual |
| 1.5 | Update `ui/workflow.py` — Add DASHBOARD, FAMILY_DISCOVERY | ⬜ | |
| 1.6 | Add `db.get_family_treasure_count()` | ⬜ | |
| 1.7 | Add i18n strings (EN + HU) | ⬜ | |
| 1.8 | Write tests — navigation + dashboard | ⬜ | |

### Stage 2: Soft-Delete & Plan Review (Phase 2)

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Create `core/trash.py` — Soft-delete module | ⬜ | soft_delete, recover, purge_expired |
| 2.2 | Add `soft_deletes` table + migration + CRUD | ⬜ | |
| 2.3 | Create `ui/plan_review.py` — Two-column review | ⬜ | Deletions left, requests right, impact totals |
| 2.4 | Add `db.get_plan_summary()` | ⬜ | |
| 2.5 | Wire PlanningPanel review button → Plan Review | ⬜ | |
| 2.6 | Add i18n strings (EN + HU) | ⬜ | |
| 2.7 | Write tests — trash + plan review + DB | ⬜ | |

### Stage 3: Execution Screen & File Ops (Phase 3)

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Create `core/executor.py` — PlanExecutor QThread | ⬜ | Follows Scanner pattern |
| 3.2 | Create `ui/execution_screen.py` — Progress + log | ⬜ | |
| 3.3 | Create `ui/tray.py` — System tray icon | ⬜ | |
| 3.4 | Wire Plan Review → Execution with confirmation | ⬜ | |
| 3.5 | Add startup trash purge in `main.py` | ⬜ | |
| 3.6 | Add `db.mark_file_action_executed()` | ⬜ | |
| 3.7 | Add i18n strings (EN + HU) | ⬜ | |
| 3.8 | Write tests — executor | ⬜ | |

### Stage 4: Family Discovery & Requests (Phase 4)

| # | Task | Status | Details |
|---|------|--------|---------|
| 4.1 | Add `requests` table + migration + CRUD | ⬜ | |
| 4.2 | Create `ui/family_discovery.py` — Grid view | ⬜ | QListView IconMode + custom model |
| 4.3 | Enhance `data/export.py` — `requests_outgoing` | ⬜ | |
| 4.4 | Enhance `ui/plan_review.py` — Right column with requests | ⬜ | |
| 4.5 | Enhance `ui/dashboard.py` — Wire family + request cards | ⬜ | |
| 4.6 | Add i18n strings (EN + HU) | ⬜ | |
| 4.7 | Write tests — family discovery + requests + export | ⬜ | |

### Stage 5: Advanced Cleanup (Phase 5)

| # | Task | Status | Details |
|---|------|--------|---------|
| 5.1 | Create `ui/filter_sidebar.py` — Collapsible filters | ⬜ | Date, type, redundancy, full-dupe-folders-only, family safety, sort |
| 5.2 | Create `ui/cluster_model.py` — Hash-grouped model | ⬜ | QAbstractItemModel with lazy loading |
| 5.3 | Create `core/selection.py` — Smart presets + Master Copy | ⬜ | |
| 5.4 | Create `ui/batch_actions.py` — Batch selection tools | ⬜ | Select All in Folder, Select by Pattern |
| 5.5 | Enhance `ui/results_panel.py` — Cluster toggle, search, stats | ⬜ | |
| 5.6 | Integrate filter sidebar into cleanup_screen | ⬜ | |
| 5.7 | Add `ROLE_MASTER_COPY` to results_model | ⬜ | |
| 5.8 | Add filtered duplicate queries to DB | ⬜ | Date range, extension, min copies |
| 5.9 | Add i18n strings (EN + HU) | ⬜ | |
| 5.10 | Write tests — cluster, selection, filter | ⬜ | |

### Stage 6: Activity Feed, Fulfillment & Polish (Phase 6)

| # | Task | Status | Details |
|---|------|--------|---------|
| 6.1 | Add `activity_log` + `protected_paths` tables | ⬜ | |
| 6.2 | Create `ui/activity_feed.py` — Dashboard feed widget | ⬜ | |
| 6.3 | Create `ui/request_list.py` — Approve/deny incoming | ⬜ | |
| 6.4 | Create `ui/trash_recovery.py` — Recovery screen | ⬜ | |
| 6.5 | Add path exclusion (right-click "Always Keep") | ⬜ | |
| 6.6 | Enhance `data/sync.py` — Request fulfillment + activity logging | ⬜ | Fulfilled files downloaded to `%USERPROFILE%\Pictures\DejaView\From_[Peer]\` |
| 6.7 | Add i18n strings (EN + HU) | ⬜ | |
| 6.8 | Write tests — activity, fulfillment, recovery | ⬜ | |

---

## Verification

### Per-phase test commands
```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q
```

### End-to-end manual smoke test (after all phases)

1. **Dashboard:** Launch app → Dashboard appears with status cards → click "Start New Scan"
2. **Cleanup flow:** Scan completes → click "Local Duplicates" card → cleanup screen with filters → apply filters → switch to cluster view → use Smart Select → enter Planning mode
3. **Plan Review:** Click "Review Plan" → see deletions + requests → remove an item → click "Apply Changes"
4. **Execution:** Progress bars advance → files moved to `.dejaview_trash` → "Done" → back to Dashboard
5. **Family Discovery:** Click "Family Photos" card → grid of remote photos → request some → verify in Plan Review right column
6. **Activity Feed:** Dashboard shows recent events (scan, sync, requests)
7. **Trash Recovery:** File menu → Recover Deleted Files → recover a file → verify restored
8. **Path Exclusion:** Right-click folder → "Always Keep" → run Smart Select → verify folder excluded
