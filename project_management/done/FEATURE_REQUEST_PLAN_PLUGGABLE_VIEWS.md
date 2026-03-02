# DejaView — Feature Request Plan: Results Panel Refactor — Pluggable Views & Action Planning

## Overview

Refactor the monolithic ResultsPanel into a pluggable view architecture and add a Planning view where users can mark duplicates with actions (keep/delete/ignore). The current ResultsPanel becomes the "Discovery" view; new views can be added for different user personas or workflow phases. The data/model layer is separated so multiple views share it.

## Problem

Today the ResultsPanel is read-only — it shows duplicates but the user cannot act on them. There is no mechanism to mark files for deletion, keeping, or ignoring. The panel mixes model logic (tree building, folder hierarchy, badge computation) with view/widget concerns, making it impossible to offer alternative views.

Users need a workflow: **Discovery** (scan) → **Planning** (mark actions) → **Plan Review** → **Execution** → **Review**. This refactor builds Discovery (existing) + Planning (new); later phases get the architecture for free.

## User Experience

### Workflow: Planning actions on duplicates

**Step 1 — Scan completes, user browses results (existing)**

The user sees the Discovery view (current ResultsPanel) with duplicate badges. A new "Plan Actions" button or menu item is available when duplicate groups exist.

**Step 2 — User enters Planning mode**

Clicking "Plan Actions" swaps the right panel to the Planning view:

```
[< Back to Results]          Planning Mode          [Keep Newest Only]
─────────────────────────────────────────────────────────────────────
Scope: (o) Local Duplicates  ( ) Cross-Library  ( ) All
─────────────────────────────────────────────────────────────────────
 Name               │ Status          │ Action
 > photos/vacation/ │ DUPLICATED      │ [Keep] [Delete] [Ignore]
   img1.jpg         │ DUPLICATE       │ [Keep] [Delete] [Ignore]
   img2.jpg         │ ✦ CROSS-LIB     │ [Keep] [Delete] [Ignore]
                    │  (Bob's PC)     │
 > photos/backup/   │ DUPLICATED      │ [Keep] [Delete] [Ignore]
   img1.jpg         │ DUPLICATE       │ [Keep] [Delete] [Ignore]
─────────────────────────────────────────────────────────────────────
 3 / 8 decided                                      [Review Plan >>]
```

**Step 3 — User marks items with actions**

- **UC1 — Folder-level:** User clicks Delete on a fully-duplicated folder → all files in that folder are marked for deletion. The folder and its children disappear from the planning view (decided items are hidden).
- **UC2 — File-level:** User clicks Keep/Delete/Ignore on individual files → each file disappears after decision.
- **UC3 — Brave mode:** User clicks "Keep Newest Only" → confirmation dialog → all older copies auto-marked for deletion. Planning view clears.

**Step 4 — Progress feedback**

The summary bar at the bottom shows "N / M decided", updating live. The tree shrinks as decisions are made. When all items are decided, the user sees "All items decided" and can proceed to review.

### Local vs remote content

All items in the planning tree are **local files** — the user can only plan actions on files they own. Cross-library items (files matching a remote peer's hash) show a distinct badge with the peer username for context, but the action applies to the local copy only. The scope filter lets the user focus on local-only duplicates, cross-library matches, or both.

Brave mode (UC3) excludes cross-library matches — they require individual review since remote copies cannot be managed.

---

## Solution

### 1. DB schema: `file_actions` table (`data/db.py`)

Add to `_DDL`:

```sql
CREATE TABLE IF NOT EXISTS file_actions (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    action      TEXT NOT NULL CHECK (action IN ('keep', 'delete', 'ignore')),
    scope       TEXT NOT NULL DEFAULT 'file' CHECK (scope IN ('file', 'folder')),
    decided_at  TEXT,
    executed_at TEXT,
    UNIQUE (session_id, file_id)
);
CREATE INDEX IF NOT EXISTS idx_file_actions_session ON file_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_file_actions_file    ON file_actions(file_id);
```

One row per file, even for folder-level decisions (`scope='folder'`). `executed_at` stays NULL until the Execution phase (future).

Add migration in `_migrate()`: check table existence, CREATE if absent.

New `Database` methods:
- `set_file_action(session_id, file_id, action, scope='file')` — INSERT OR REPLACE
- `set_file_actions_batch(rows)` — bulk INSERT OR REPLACE for folder-level decisions
- `get_file_actions_for_session(session_id)` → `list[sqlite3.Row]`
- `get_decided_file_ids(session_id)` → `set[int]`
- `clear_file_action(session_id, file_id)` — single undo
- `clear_all_actions(session_id)` — reset entire plan

### 2. Extract shared model: new `ui/results_model.py`

Move from `results_panel.py`:
- All `ROLE_*` constants (lines 47–55)
- All `FILTER_*` constants (lines 58–60)
- `_ViewState` dataclass (lines 70–77)
- `_DuplicateFilterProxy` class (lines 80–133)
- `_DEBOUNCE_MS`, `_DEFAULT_INDENT`, `_MIN_INDENT` constants

Add new constants:
- `ROLE_ACTION = Qt.ItemDataRole.UserRole + 10`
- `ROLE_HAS_DECISION = Qt.ItemDataRole.UserRole + 11`

Add new class `ResultsTreeModel` (plain Python object, not QWidget):
- Owns `QStandardItemModel`, `_folder_items`, `_file_id_to_item`, `_duplicate_hashes`, `_cross_library_hashes`
- Methods: `add_file_to_tree()`, `get_or_create_folder()`, `update_file_badge()`, `compute_folder_duplication()`, `load_from_db(db, session_id)`

Update `results_panel.py`: import from `results_model`, re-export constants for backward compat, accept optional `ResultsTreeModel` in constructor.

### 3. Planning filter proxy (in `ui/results_model.py`)

New subclass `PlanningFilterProxy(_DuplicateFilterProxy)`:
- Holds `_decided_file_ids: set[int]` and a scope mode (local dupes / cross-lib / all)
- `filterAcceptsRow()`: base duplicate/cross-lib filter + hides files in `_decided_file_ids`; folders shown only if they have undecided descendants
- `set_decided_file_ids(ids)` → `invalidateFilter()`

### 4. Workflow phase enum: new `ui/workflow.py`

```python
from enum import Enum, auto

class WorkflowPhase(Enum):
    DISCOVERY = auto()
    PLANNING = auto()
    PLAN_REVIEW = auto()   # future
    EXECUTION = auto()     # future
    REVIEW = auto()        # future
```

### 5. Planning panel: new `ui/planning_panel.py`

Three-column tree (Name, Status, Action) using shared `ResultsTreeModel` + `PlanningFilterProxy`.

Key components:
- **`_ActionDelegate(QStyledItemDelegate)`** — paints Keep/Delete/Ignore buttons per row via `paint()` / `editorEvent()` (no real QWidget per row)
- **Scope filter radio buttons** — Local Duplicates / Cross-Library / All
- **Summary bar** — "N / M decided", updates live
- **"Keep Newest Only" button** — brave mode with confirmation dialog
- **Back button** — returns to Discovery view

Signals: `closed`, `compare_view_requested(str)`, `review_requested`

### 6. MainWindow integration (`ui/main_window.py`)

Reuse existing splitter swap pattern (same as ScanProgressWidget / CompareView):
- Add "Plan Actions" item to Scan menu (enabled when session has duplicates)
- Add `_show_planning_panel()` / `_hide_planning_panel()` methods
- Wire `planning_panel.closed` → `_hide_planning_panel()` + `results_panel.reload()`
- Track `_workflow_phase` property

---

## Files to Modify

| File | Change |
|------|--------|
| `data/db.py` | Add `file_actions` table DDL, migration, 6 CRUD methods |
| `ui/results_model.py` | **New** — shared model: roles, filters, `ResultsTreeModel`, `PlanningFilterProxy` |
| `ui/results_panel.py` | Import from `results_model`, accept shared model, re-export constants |
| `ui/planning_panel.py` | **New** — planning view with action delegate, brave mode, summary bar |
| `ui/workflow.py` | **New** — `WorkflowPhase` enum |
| `ui/main_window.py` | Add Plan menu item, panel swap, workflow phase tracking |
| `tests/unit/test_db.py` | Add `file_actions` CRUD tests |
| `tests/unit/test_planning_panel.py` | **New** — action assignment, filter, brave mode tests |

---

## Task Log

### Stage 1: DB Schema

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Add `file_actions` table to DDL | ✅ Done | Added to `_DDL` string with CHECK constraints and UNIQUE |
| 1.2 | Add migration for existing DBs | ✅ Done | In `_migrate()` — checks sqlite_master for table existence |
| 1.3 | Add 6 CRUD methods | ✅ Done | set_file_action, set_file_actions_batch, get_file_actions_for_session, get_decided_file_ids, clear_file_action, clear_all_actions — all use ON CONFLICT upsert |
| 1.4 | Write unit tests | ✅ Done | 14 tests in TestFileActions class — 68 total pass |

### Stage 2: Shared Model Extraction

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Create `ui/results_model.py` with roles, filters, `ViewState`, `DuplicateFilterProxy` | ✅ Done | Moved constants, dataclass, filter proxy; renamed to public names |
| 2.2 | Create `ResultsTreeModel` class | ✅ Done | Owns QStandardItemModel, lookup dicts, hash sets, tree-building, folder duplication |
| 2.3 | Update `results_panel.py` to import from `results_model` | ✅ Done | Re-exports all constants + aliases; accepts optional tree_model param |
| 2.4 | Verify existing tests pass | ✅ Done | 178 passed, 10 skipped — no regressions |

### Stage 3: Planning Filter Proxy

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Add `PlanningFilterProxy` to `ui/results_model.py` | ✅ Done | Scope filter (local/cross-lib/all) + hide decided items |
| 3.2 | Add `ROLE_ACTION`, `ROLE_HAS_DECISION` constants | ✅ Done | Added in results_model.py |
| 3.3 | Write filter tests | ✅ Done | 6 PlanningFilterProxy tests + 4 action persistence + 1 brave mode logic = 11 tests |

### Stage 4: Workflow Phase Enum

| # | Task | Status | Details |
|---|------|--------|---------|
| 4.1 | Create `ui/workflow.py` | ✅ Done | WorkflowPhase enum with 5 phases (3 future) |

### Stage 5: Planning Panel

| # | Task | Status | Details |
|---|------|--------|---------|
| 5.1 | Create `ui/planning_panel.py` scaffold | ✅ Done | Layout with top bar, scope filter, tree, summary bar |
| 5.2 | Implement `_ActionDelegate` | ✅ Done | Paint + editorEvent for Keep/Delete/Ignore colored buttons |
| 5.3 | Wire action buttons to DB | ✅ Done | UC1 (folder via batch) + UC2 (single file) |
| 5.4 | Implement "Keep Newest Only" brave mode | ✅ Done | UC3 with confirmation dialog, excludes cross-lib |
| 5.5 | Add cross-library peer info badges | ✅ Done | `ROLE_PEER_USERNAMES`, `cross_library_peers` dict, `_file_badge_text()` helper; badges show `✦ CROSS-LIB (bob)` or combined `● DUPLICATE ✦ alice, bob`; 7 new tests |
| 5.6 | Write planning panel tests | ✅ Done | 18 tests in test_planning_panel.py — 196 total pass |

### Stage 6: MainWindow Integration

| # | Task | Status | Details |
|---|------|--------|---------|
| 6.1 | Add "Plan Actions" menu item | ✅ Done | In Scan menu, enabled when session has duplicates |
| 6.2 | Add panel swap methods | ✅ Done | `_show_planning_panel()` / `_hide_planning_panel()` following existing swap pattern |
| 6.3 | Wire signals and workflow phase | ✅ Done | `closed` → hide panel + reload results; `compare_view_requested` → compare view; `WorkflowPhase` tracking |
| 6.4 | Update i18n files | ✅ Done | 2 MainWindow + 12 PlanningPanel strings in both app.ts and app_hu.ts |

---

## Verification

1. **Unit tests pass:**
   ```bash
   cd dejaview
   python -m pytest tests/unit/ --no-cov -q
   ```

2. **Manual smoke test — Planning workflow:**
   - Run a scan with known duplicates
   - Click "Plan Actions" → planning panel appears with duplicate items
   - Mark individual files Keep/Delete/Ignore → items disappear, summary updates
   - Mark a fully-duplicated folder for deletion → all children disappear
   - Click "Keep Newest Only" → confirmation → all remaining items marked, view clears
   - Click "Back to Results" → results panel shows unchanged data

3. **Manual smoke test — Cross-library in planning:**
   - Import a peer's scan data
   - Enter Planning mode, switch scope to "Cross-Library"
   - Verify cross-library items show peer username badge
   - Mark a cross-library item → only local copy affected

4. **Regression — existing features:**
   - Compare view still works from both Discovery and Planning panels
   - Scan progress swap pattern still works
   - Filter modes in Discovery view unchanged
