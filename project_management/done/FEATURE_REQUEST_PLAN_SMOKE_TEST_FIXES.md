# DejaView — Feature Request Plan: Phase 5 Smoke Test Fixes

## Overview

After the Phase 5 (Advanced Cleanup) smoke test, 7 issues were identified across UX, performance, and behaviour. This plan addresses all of them.

## Problem

1. **Panel borders**: Panels on the cleanup screen are hard to distinguish — no visual separators between FolderPanel, FilterSidebar, and ResultsPanel.
2. **Panel sizes**: Panels don't proportionally match their content quantity — all receive similar horizontal space.
3. **Layout order**: FolderPanel and scan controls are side-by-side with results. User expects folders/scanning on top, actions below.
4. **Smart select → plan review**: After smart selection completes, the user stays on the cleanup screen instead of navigating to plan review.
5. **Plan review performance**: Plan review screen takes minutes to load with 10k+ changes due to per-row `QPushButton` widget allocation.
6. **Two-copy auto-keep**: When two copies exist and one is marked for deletion, the other should auto-mark as "keep".
7. **Three+-copy prompt**: When three or more copies exist and one is marked to keep, prompt user to mark all others for deletion.

---

## Solution

### Task 1 — Plan Review Performance (Issue 5)

**Problem:** `plan_review.py:_populate_delete_tree()` creates a real `QPushButton` per row via `setItemWidget()`. With 10k+ items this means 10k native OS window handles + 10k layout recalculations. Also calls `setExpanded(True)` per folder item inside the loop, and uses no `blockSignals()`.

**Fix:** Replace `QPushButton`/`setItemWidget()` with a custom painted delegate (same pattern as `_ActionDelegate` in `planning_panel.py:84-192`).

**File:** `ui/plan_review.py`

1. Create `_RemoveDelegate(QStyledItemDelegate)`:
   - `paint()`: draw a small red "✖" circle in column 2 for removable items
   - `editorEvent()`: detect mouse click in the painted rect, emit `remove_clicked(data)` where data is either `list[int]` (action_ids for folder) or `int` (file_id)
   - `sizeHint()`: fixed 28×28

2. Refactor `_populate_delete_tree()`:
   - Remove all `QPushButton` creation and `setItemWidget()` calls
   - Store file_id in column 2 data for individual items: `item.setData(2, UserRole, file_id)`
   - Wrap population in `blockSignals(True)` / `blockSignals(False)`
   - Move `setExpanded(True)` to a single `expandAll()` call after all items are added

3. Wire delegate in `_build_ui()`:
   - `self._remove_delegate = _RemoveDelegate(self)`
   - `self._delete_tree.setItemDelegateForColumn(2, self._remove_delegate)`
   - Connect `remove_clicked` → `_on_remove_clicked()` dispatcher

**Expected speedup:** From minutes → seconds for 10k items (O(n) widget allocations → O(0)).

---

### Task 2 — Sibling Auto-Actions (Issues 6 + 7)

**Problem:** When marking one file in a duplicate group, siblings are unaffected.

**File:** `ui/planning_panel.py` — extend `_on_action_clicked()` (line 347)

**Issue 6 — Auto-keep sibling in 2-copy groups:**
After setting action == "delete" on a file:
1. `db.get_file(file_id)` → get `pixel_hash`
2. `db.get_cluster_files(session_id, pixel_hash)` → get siblings
3. If exactly 2 files in group and the other is undecided → auto-mark as "keep"

**Issue 7 — Prompt for 3+ copy groups:**
After setting action == "keep" on a file:
1. Same sibling lookup
2. If 3+ files and there are undecided siblings → `QMessageBox.question()`: "Mark the other N copies for deletion?"
3. If Yes → `db.set_file_actions_batch()` for all undecided siblings as "delete"

**New import:** `import os` (for `os.path.basename` in the dialog message)

**New tr() strings (2):**
- `"Mark Others for Deletion?"`
- `"You kept {0}.\n\nMark the other {1} copies for deletion?"`

---

### Task 3 — Smart Select Auto-Jump to Plan Review (Issue 4)

**Problem:** After smart select completes, the user stays on the cleanup screen.

**File:** `ui/cleanup_screen.py` — extend `_on_preset_applied()` (line 302)

After reload, if `delete_count > 0`, show `QMessageBox.question()`:
- "Smart Select Complete" / "{0} files kept, {1} marked for deletion.\n\nWould you like to review the plan?"
- Yes → `self.review_requested.emit()` (already wired to `MainWindow._on_review_requested()` → `nav.navigate_to("plan_review")`)

**New import:** `QMessageBox` in `cleanup_screen.py`

**New tr() strings (2):**
- `"Smart Select Complete"`
- `"{0} files kept, {1} marked for deletion.\n\nWould you like to review the plan?"`

---

### Task 4 — Layout Restructure: Folders on Top (Issue 3)

**Problem:** FolderPanel is alongside ResultsPanel in a horizontal splitter. User wants folder selection on top, actions below.

**Files:** `ui/cleanup_screen.py`, `ui/folder_panel.py`

#### 4a. Convert FolderPanel to horizontal compact bar (`folder_panel.py`)

**Current layout:**
```
QVBoxLayout:
  QLabel("Scan Folders")
  QListWidget (full height)
  [+ Add] [- Remove]
```

**New layout:**
```
QHBoxLayout:
  QLabel("Scan Folders:")
  QListWidget (compact, maxHeight ~80)
  [+ Add...] [- Remove]
```

Changes:
- Outer layout: QVBoxLayout → QHBoxLayout
- `self._list.setMaximumHeight(80)` for compact display
- Buttons go directly into the main row (no nested QHBoxLayout)
- `self.setMaximumHeight(100)` on the panel itself

#### 4b. Restructure CleanupScreen layout (`cleanup_screen.py`)

**Current:**
```
QVBoxLayout:
  BatchActions
  QSplitter(H): [FolderPanel | FilterSidebar | ResultsPanel]
```

**New:**
```
QVBoxLayout:
  FolderPanel (compact horizontal bar, full width)    ← TOP
  QSplitter(H):                                       ← MAIN AREA
    FilterSidebar (collapsible, hidden by default)
    right_container (QWidget):
      QVBoxLayout:
        BatchActions toolbar
        ResultsPanel
```

Changes to `_build_ui()`:
1. Add `self._folder_panel` to main QVBoxLayout (before splitter, not in splitter)
2. Create `self._right_container = QWidget()` with QVBoxLayout holding BatchActions + ResultsPanel
3. Splitter has 2 widgets: FilterSidebar + right_container
4. Stretch factors: sidebar=0, right_container=1
5. Remove min/max width constraints from folder panel

Update panel-swap methods to use `_right_container` layout:
- `show_scan_progress()` / `hide_scan_progress()`
- `show_planning_panel()` / `_hide_planning_panel()`
- `_on_compare_requested()` / `_close_compare_view()`
- Remove `_auto_fit_splitter()` (folder panel no longer in splitter)

---

### Task 5 — Panel Sizes (Issue 2)

**File:** `ui/cleanup_screen.py`

After task 4's restructure, the splitter has only FilterSidebar + right_container:
- `setStretchFactor(0, 0)` — sidebar: fixed width
- `setStretchFactor(1, 1)` — right container: stretch (gets maximum space)

When filter sidebar is hidden (default), results panel gets 100% horizontal space.

---

### Task 6 — Panel Borders (Issue 1)

**Files:** `ui/folder_panel.py`, `ui/results_panel.py`, `ui/filter_sidebar.py`, `ui/batch_actions.py`, `ui/cleanup_screen.py`

Apply consistent border styling using class-scoped stylesheets:

1. **FolderPanel**: `border-bottom: 1px solid #d1d5db;` (separator below top bar)
2. **FilterSidebar**: `border-right: 1px solid #d1d5db;` (separator from results)
3. **BatchActions**: `border-bottom: 1px solid #e5e7eb;` (subtle separator below toolbar)
4. **Splitter handle**: `QSplitter::handle { background: #d1d5db; width: 1px; }`
5. **Section headings**: bold font, slightly larger size

Pattern reference: `plan_review.py:170-177` totals_frame styling.

---

### Task 7 — i18n (EN + HU)

Add new tr() strings from tasks 2 and 3 to both `.ts` files, then recompile:

| Context | String |
|---------|--------|
| PlanningPanel | `"Mark Others for Deletion?"` |
| PlanningPanel | `"You kept {0}.\n\nMark the other {1} copies for deletion?"` |
| CleanupScreen | `"Smart Select Complete"` |
| CleanupScreen | `"{0} files kept, {1} marked for deletion.\n\nWould you like to review the plan?"` |

```
cd dejaview/resources/i18n && lrelease app_hu.ts && lrelease app.ts
```

---

### Task 8 — Tests + Build Verification

- Run all existing tests: `python -m pytest tests/unit/ --no-cov -q` — 304 must pass
- Add sibling auto-action tests in `tests/unit/test_planning_panel.py`:
  - `test_delete_one_of_two_auto_keeps_sibling`
  - `test_delete_does_not_auto_keep_when_sibling_already_decided`
  - `test_delete_does_not_auto_keep_in_3plus_group`
  - `test_keep_in_3plus_prompts_batch_delete` (mock QMessageBox)
- Build: `resources\build.bat`

---

## Task Dependency Order

```
Task 1 (perf) ──────────────┐
Task 2 (siblings) ──────────┤
Task 3 (auto-jump) ─────────┼──► Task 7 (i18n) ──► Task 8 (tests + build)
Task 4 (layout restructure) ┤
Task 5 (panel sizes) ───────┤
Task 6 (panel borders) ─────┘
```

Tasks 1–3 are independent. Task 5 depends on Task 4. Task 6 is best after Task 4. Tasks 7–8 are last.

## Verification

```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q
```

All 304 existing tests must pass. New tests should add ~5-8 tests.

Manual smoke test:
1. Open cleanup screen → verify folder panel is at the top, results below
2. Verify panel borders and visual separation
3. Start a scan with large dataset → verify results panel dominates space
4. Run Smart Select → confirm navigation prompt → verify plan review loads
5. Plan Review with 10k+ items → verify loads in seconds, scroll smoothly
6. In planning mode: mark one of two duplicates as delete → verify sibling auto-marked keep
7. Mark one of three duplicates as keep → verify prompt to delete others
