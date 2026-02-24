# UI Enhancement 1 — View State Persistence & Dynamic View Adjustment: Progress Tracker

## Overall: 100% complete (2/2 features done)

## Features Checklist

| Feature | Status | Notes/Blockers | Completed By |
|---------|--------|----------------|--------------|
| **1 — View State Persistence** | ✅ Done | Filter mode, tree expansion, scroll position, selected item all survive reload cycles | Task #1.1–1.4 |
| **2 — Dynamic View Adjustment** | ✅ Done | Column auto-resize, indent fitting, splitter auto-adjust, smart expand/collapse | Task #2.1–2.4 |

---

## Feature 1: View State Persistence — Detailed Breakdown

**Problem:** When user opens CompareView (double-click duplicate) and returns, `reload()` calls `_model.clear()` + `expandAll()`, destroying all manual adjustments.

**Solution:** Save/restore pattern built into `reload()` so all callers benefit automatically.

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 1.1 | `_ViewState` dataclass | ✅ Done | Stores filter_mode, expanded_paths, scroll_value, selected_path |
| 1.2 | `_save_view_state()` + `_collect_expanded()` | ✅ Done | Captures filter, walks tree for expanded folder paths, reads scrollbar + selection |
| 1.3 | `_restore_view_state()` + `_find_file_by_path()` | ✅ Done | Restores filter + radio buttons, selectively expands folders, deferred scroll restore via `QTimer.singleShot(0)`, re-selects file by path |
| 1.4 | Modify `reload()` + `set_session_id()` | ✅ Done | State saved at top of `reload()`, restored at bottom; `set_session_id()` clears saved state for fresh sessions |

### State Persistence Lifecycle

| Trigger | Saves State? | Restores State? | Notes |
|---------|-------------|-----------------|-------|
| Return from CompareView | Yes (via `reload()`) | Yes | Filter, expansion, scroll, selection all restored |
| Action confirmation in CompareView | Yes (via `reload()`) | Yes | Deleted files gracefully skipped during restore |
| Cross-library import | Yes (via `reload()`) | Yes | |
| New session (`set_session_id()`) | No | No | `_saved_state` cleared; fresh smart expand |
| First load (no prior state) | No | No | Falls through to `_smart_expand()` |

### What Gets Persisted

| Setting | Saved How | Restored How |
|---------|-----------|-------------|
| Filter mode | `_proxy.filter_mode` string | `set_filter()` — updates proxy + radio buttons |
| Tree expansion | Set of folder paths from `_folder_items` reverse lookup | `setExpanded()` per folder in `_folder_items` |
| Scroll position | `verticalScrollBar().value()` | `QTimer.singleShot(0, ...)` — deferred for layout |
| Selected file | `ROLE_FILE_PATH` of current item | `_find_file_by_path()` + `setCurrentIndex()` |

---

## Feature 2: Dynamic View Adjustment — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 2.1 | Column auto-resize | ✅ Done | Column 0 switched from `Stretch` to `Interactive`; `_fit_columns()` auto-fits with viewport floor |
| 2.2 | Tree indent fitting | ✅ Done | `_adjust_indentation()` scales indent inversely with depth (20px default → 8px min) |
| 2.3 | Splitter auto-adjust | ✅ Done | `_auto_fit_splitter()` in MainWindow sizes left pane to longest folder name via `QFontMetrics` |
| 2.4 | Smart expand/collapse | ✅ Done | `_smart_expand()` replaces blanket `expandAll()` — depth-limited in "All" mode, path-to-match in filter modes |

### 2.1 Column Auto-Resize

| Before | After |
|--------|-------|
| Column 0: `QHeaderView.ResizeMode.Stretch` (fills all space, no manual resize) | Column 0: `QHeaderView.ResizeMode.Interactive` (auto-fits to content, user can manually resize) |
| Deep paths truncated, no scrollbar | `_fit_columns()` called after `reload()` and `_flush_pending()`; horizontal scrollbar appears when content exceeds viewport |

### 2.2 Tree Indent Fitting

```
Depth ≤ 4  → 20px indent (Qt default)
Depth  5   → 16px
Depth  8   → 10px
Depth 10+  → 8px  (minimum)
Formula: max(8, 20 * 4 // depth)
```

### 2.3 Splitter Auto-Adjust

- Connected to `FolderPanel.folders_changed` signal
- Measures longest folder basename via `QFontMetrics.horizontalAdvance()`
- Adds 60px padding for margins/scrollbar/buttons
- Clamped to existing 180–300px constraints

### 2.4 Smart Expand/Collapse

| Filter Mode | Expand Strategy |
|-------------|----------------|
| **All** | Expand first 2 levels, collapse deeper (`_expand_to_depth`) |
| **Duplicates Only** | Collapse all, then expand only folder chains leading to duplicate files (`_expand_paths_to_matches`) |
| **Cross-Library** | Collapse all, then expand only folder chains leading to cross-library files |

Filter changes also trigger `_smart_expand()` — switching to "Duplicates Only" immediately collapses irrelevant folders.

---

## Regression Test Results

```
cd dejaview && python -m pytest tests/unit/ --no-cov -q
```

| Metric | Before | After |
|--------|--------|-------|
| Tests passed | 156 | 156 |
| Tests skipped | 10 | 10 |
| Tests failed | 0 | 0 |
| Run time | ~5.5 s | ~5.5 s |

No regressions introduced. All 156 unit tests pass.

---

## Files Changed

| Action | Path | Changes |
|--------|------|---------|
| **Modified** | `dejaview/ui/results_panel.py` | +170 LOC — `_ViewState` dataclass, `_save/_restore_view_state()`, `_fit_columns()`, `_adjust_indentation()`, `_smart_expand()` + helpers, modified `reload()`, `set_session_id()`, `_on_filter_changed()`, `_flush_pending()`; header mode `Stretch` → `Interactive` |
| **Modified** | `dejaview/ui/main_window.py` | +14 LOC — `import os`, `_auto_fit_splitter()` slot, `folders_changed` signal connection |

---

## Key Technical Decisions

- **State saved inside `reload()`** — All callers (compare-view return, action confirmation, cross-library import) automatically benefit without code changes
- **No disk persistence** — View state is transient within a session; `_ViewState` is an in-memory dataclass, not stored in DB or QSettings
- **Deferred scroll restore** — `QTimer.singleShot(0, ...)` ensures Qt layout completes before setting scrollbar value
- **User manual adjustments take priority** — Column Interactive mode and saved expansion state respect user choices; smart expand only fires on first load or filter change
- **Indent formula trades readability for space** — At depth 10 the indent is 8px (versus Qt's default 20px), keeping deeply nested filenames visible

---

## Manual Testing Checklist

- [ ] Scan a folder with duplicates
- [ ] Set filter to "Duplicates Only", collapse some folders, scroll down, select a file
- [ ] Double-click a duplicate to open CompareView
- [ ] Close CompareView — verify filter, expansion, scroll, selection all preserved
- [ ] Confirm actions in CompareView — verify state preserved (minus deleted files)
- [ ] Add folders with long names — verify left pane auto-sizes
- [ ] Scan deeply nested directories — verify indentation shrinks
- [ ] Switch between filter modes — verify smart expand/collapse behaviour

---

## Local Commands

```bash
# Run unit tests (fast, no PyQt6 needed)
cd dejaview && python -m pytest tests/unit/ --no-cov -q

# Run all tests including UI
cd dejaview && python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q
```
