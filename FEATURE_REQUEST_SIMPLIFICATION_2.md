# Feature Request: UI Simplification (Round 2)

This document describes three UI simplification changes for the DejaView application.
Each feature includes detailed requirements, affected files, and implementation guidance.

---

## Feature 1: Remove the View Menu

### Problem
The View menu exists in the menu bar but contains zero actions. It was added as a Phase 3 placeholder and was never populated. It clutters the menu bar and confuses users.

### Current State
- `dejaview/ui/main_window.py` line 96: `mb.addMenu(self.tr("View"))` — creates an empty, non-functional menu
- Menu bar currently shows: **File | View | Scan | Share | Help**

### Requirements
1. Remove the View menu entirely from the menu bar
2. Update menu bar to show: **File | Scan | Share | Help**

### Implementation Details

**Code changes:**
| File | Change |
|------|--------|
| `dejaview/ui/main_window.py` | Delete line 96 (`mb.addMenu(self.tr("View"))`). Update module docstring (line 5) from `File \| View \| Scan \| Share \| Help` to `File \| Scan \| Share \| Help`. |
| `dejaview/resources/i18n/app.ts` | Remove any `"View"` translation entries |
| `dejaview/resources/i18n/app_hu.ts` | Remove `"Nézet"` translation entries |

**User guide changes:**
| File | Change |
|------|--------|
| `dejaview/resources/help/USER_GUIDE.md` | Line 35: Change `Menu: File \| View \| Scan \| Share` → `Menu: File \| Scan \| Share \| Help` |
| `dejaview/resources/help/USER_GUIDE_HU.md` | Line 35: Change `Menü: Fájl \| Nézet \| Szkennelés \| Megosztás` → `Menü: Fájl \| Szkennelés \| Megosztás \| Súgó` |
| `USER_GUIDE.md` (root) | Same change as the in-app English guide |

**Tests:** No test changes needed — no existing tests reference the View menu.

---

## Feature 2: Make the Settings Dialog Functional

### Problem
The **File > Settings…** menu item exists but has no callback — clicking it does nothing. Language is silently auto-detected from the Windows system locale with no way for the user to override it. There is no UI for application-level preferences.

### Current State
- `dejaview/ui/main_window.py` line 91: `file_menu.addAction(self.tr("Settings…"))` — placeholder, no slot connected
- `dejaview/main.py` line 49: Language detected from `QLocale.system().name()[:2]` — only `"hu"` is handled, everything else falls back to English
- No settings dialog, no `app_config` table, no user preference storage for general settings

### Requirements
1. Create a Settings dialog accessible via **File > Settings…**
2. Allow the user to choose a language: Auto (system default), English, or Magyar (Hungarian)
3. Language changes take effect after restarting the application
4. Include a placeholder for a future UI theme selector
5. Persist settings across sessions

### Implementation Details

#### 2.1 — New Database Table: `app_config`

Add to the schema in `dejaview/data/db.py`:

```sql
CREATE TABLE IF NOT EXISTS app_config (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    language TEXT NOT NULL DEFAULT 'auto',
    theme    TEXT NOT NULL DEFAULT 'system'
);
```

Add two new methods to the `Database` class:

```python
def get_app_config(self) -> dict | None:
    """Return the app_config singleton row, or None if not yet created."""
    ...

def upsert_app_config(self, **fields) -> None:
    """Insert or update the app_config singleton with the given fields."""
    ...
```

This table is separate from `sync_config` because it stores application-wide preferences unrelated to sync/sharing.

#### 2.2 — New File: `dejaview/ui/settings_dialog.py`

A modal `QDialog` with the following layout:

```
┌─ Settings ──────────────────────────────────┐
│                                             │
│  Language                                   │
│  ┌─────────────────────────────┐            │
│  │ Auto (system default)    ▼  │            │
│  └─────────────────────────────┘            │
│                                             │
│  Theme                                      │
│  ┌─────────────────────────────┐            │
│  │ System Default           ▼  │  (grayed)  │
│  └─────────────────────────────┘            │
│  "Additional themes coming in a future      │
│   release."                                 │
│                                             │
│              [ Save ]  [ Cancel ]           │
└─────────────────────────────────────────────┘
```

**Language combo box options:**
| Display Text | Stored Value |
|-------------|-------------|
| Auto (system default) | `'auto'` |
| English | `'en'` |
| Magyar | `'hu'` |

**Theme combo box:** Single option "System Default", disabled. Tooltip: "Additional themes coming in a future release."

**On Save:**
- Write selection to `app_config` table via `db.upsert_app_config(language=..., theme=...)`
- If language changed: show `QMessageBox.information()` with message "Please restart DejaView to apply the new language."
- Emit `settings_saved` signal

**On Cancel:** Close dialog without saving.

All visible strings must use `self.tr()` for i18n support.

#### 2.3 — Wire Settings Action in MainWindow

In `dejaview/ui/main_window.py`:

```python
# Change line 91 from:
file_menu.addAction(self.tr("Settings…"))   # Phase 7 placeholder
# To:
file_menu.addAction(self.tr("Settings…"), self._on_settings)
```

Add new slot:

```python
@pyqtSlot()
def _on_settings(self) -> None:
    """File > Settings — open the Settings dialog."""
    from ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(db=self._db, parent=self)
    dlg.settings_saved.connect(
        lambda: self._status_bar.showMessage(self.tr("Settings saved."))
    )
    dlg.exec()
```

#### 2.4 — Language Loading Change in main.py

Modify `_load_translators()` in `dejaview/main.py` to read the user's language preference:

```python
def _load_translators(app: QApplication, db_path: Path) -> None:
    # Open a temporary DB connection to read app_config
    db = Database(db_path)
    db.open()
    config = db.get_app_config()
    db.close()

    lang_pref = config["language"] if config else "auto"

    if lang_pref == "auto":
        lang = QLocale.system().name()[:2]  # current behavior
    else:
        lang = lang_pref

    if lang != "hu":
        return

    # ... rest of translator loading unchanged ...
```

Note: This requires passing `db_path` to `_load_translators()`, which is a minor signature change.

#### 2.5 — i18n Strings

Add to `dejaview/resources/i18n/app.ts` and `app_hu.ts`:

New translatable strings:
- "Settings" (dialog title)
- "Language"
- "Auto (system default)"
- "Theme"
- "System Default"
- "Additional themes coming in a future release."
- "Please restart DejaView to apply the new language."
- "Settings saved."
- "Save"
- "Cancel"

#### 2.6 — User Guide Changes

**`dejaview/resources/help/USER_GUIDE.md`** — Replace the Settings section (lines 182-189):

```markdown
## Settings

### Changing the Language

The app automatically uses Hungarian or English based on your Windows system
language. To override this, go to **File > Settings**, choose your preferred
language from the dropdown, and click **Save**. You will need to restart the
application for the change to take effect.

### Theme

A theme selector is available in the Settings dialog. Currently only the
system default theme is supported; additional themes are planned for a
future release.
```

**`dejaview/resources/help/USER_GUIDE_HU.md`** — Same section translated:

```markdown
## Beállítások

### Nyelv módosítása

Az alkalmazás automatikusan a Windows rendszer nyelve alapján választ
magyart vagy angolt. Ha felül szeretné írni, nyissa meg a
**Fájl > Beállítások** menüpontot, válassza ki a kívánt nyelvet a
legördülő listából, majd kattintson a **Mentés** gombra. A változtatás
az alkalmazás újraindítása után lép érvénybe.

### Téma

A Beállítások ablakban elérhető egy témaválasztó. Jelenleg csak a
rendszer alapértelmezett téma támogatott; további témák egy jövőbeli
kiadásban lesznek elérhetők.
```

**Root-level `USER_GUIDE.md`** — Keep in sync with the in-app English guide.

---

## Feature 3: UX-Friendly Navigation

### Problem
The current workflow requires too many manual steps to discover and analyze duplicates:
1. After a scan completes, the results panel stays on the "All" filter — the user must manually switch to "Duplicates Only"
2. The status bar only shows "Scan complete." with no summary of what was found
3. Comparing duplicates requires double-clicking a file row — there is no visible button or context menu (poor discoverability)
4. When an entire folder's contents are duplicated, the user sees every file individually badged, rather than seeing the folder as a single duplicated unit

### Current State
- `dejaview/ui/main_window.py:_on_scan_complete()` — shows "Scan complete." and triggers sync; does not change the filter
- `dejaview/ui/results_panel.py:_on_item_double_clicked()` — the only way to open CompareView; no button, no context menu
- Folder nodes in the tree have no duplication awareness — only individual files get `● DUPLICATE` badges

### Requirements

#### 3a. Auto-switch to "Duplicates Only" filter after scan completes
- After a scan finishes, if duplicates were found, automatically switch the filter to "Duplicates Only"
- If no duplicates were found, keep the "All" filter and show an appropriate message

#### 3b. Scan results summary in the status bar
- Replace `"Scan complete."` with a detailed summary including file count, duplicate count, and group count

#### 3c. Visible "Compare" button and context menu
- Add a Compare button to the results panel that enables when a duplicate is selected
- Add a right-click context menu on duplicate files with a "Compare Duplicates" entry
- Keep double-click working as a power-user shortcut

#### 3d. Folder-level duplication grouping
- When all files in a folder (recursively) are duplicates, badge the folder as "DUPLICATED FOLDER"
- In "Duplicates Only" filter mode, show fully-duplicated folders collapsed (hiding individual files)
- Allow the user to expand the folder to see individual files if needed
- Support comparing a fully-duplicated folder as a whole unit

### Implementation Details

#### 3a — Auto-filter After Scan

In `dejaview/ui/main_window.py`, modify `_on_scan_complete()`:

```python
@pyqtSlot()
def _on_scan_complete(self) -> None:
    # Compute scan summary
    if self._session_id is None:
        return
    files = self._db.get_files_for_session(self._session_id)
    total_files = sum(1 for f in files if f["status"] == "active")
    dup_groups = self._db.get_duplicate_groups(self._session_id)
    group_count = len(dup_groups)
    dup_file_count = sum(g["file_count"] for g in dup_groups)

    if group_count > 0:
        self._results_panel.set_filter(FILTER_DUPLICATES_ONLY)
        self._status_bar.showMessage(
            self.tr("Scan complete: {0} files scanned, {1} duplicates in {2} groups.").format(
                total_files, dup_file_count, group_count
            )
        )
    else:
        self._status_bar.showMessage(
            self.tr("Scan complete: {0} files scanned. No duplicates found.").format(total_files)
        )

    # Trigger sync (existing behavior)
    self._run_sync(session_id=self._session_id)
```

Import `FILTER_DUPLICATES_ONLY` from `results_panel` at the top of the file.

#### 3b — Scan Summary

Covered above in 3a. The summary message format:
- With duplicates: `"Scan complete: 150 files scanned, 12 duplicates in 5 groups."`
- Without duplicates: `"Scan complete: 150 files scanned. No duplicates found."`

#### 3c — Compare Button and Context Menu

In `dejaview/ui/results_panel.py`:

**Add Compare button to the filter bar:**

```python
def _build_ui(self) -> None:
    # ... existing filter radio buttons ...
    filter_row.addStretch()

    # Compare button (new)
    self._compare_btn = QPushButton(self.tr("Compare"), self)
    self._compare_btn.setEnabled(False)
    filter_row.addWidget(self._compare_btn)

    layout.addLayout(filter_row)
    # ... rest of tree setup ...

    # Connect Compare button
    self._compare_btn.clicked.connect(self._on_compare_clicked)

    # Enable context menu on tree
    self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    self._tree.customContextMenuRequested.connect(self._on_context_menu)
```

**Update Compare button state on selection change:**

```python
def _build_ui(self) -> None:
    # ... after setting up the tree ...
    # Wire selection change (must be done after model is set)
    self._tree.selectionModel().currentChanged.connect(self._on_selection_changed)

@pyqtSlot(QModelIndex, QModelIndex)
def _on_selection_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
    """Enable/disable Compare button based on selection."""
    if not current.isValid():
        self._compare_btn.setEnabled(False)
        return
    source = self._proxy.mapToSource(current)
    item = self._model.itemFromIndex(source)
    if item is None:
        self._compare_btn.setEnabled(False)
        return
    # Enable for duplicate files
    is_file = item.data(ROLE_NODE_TYPE) == "file"
    is_dup = bool(item.data(ROLE_IS_DUPLICATE))
    # Enable for fully-duplicated folders
    is_folder_dup = bool(item.data(ROLE_IS_FOLDER_DUPLICATED)) if item.data(ROLE_NODE_TYPE) == "folder" else False
    self._compare_btn.setEnabled((is_file and is_dup) or is_folder_dup)
```

**Compare button click handler:**

```python
@pyqtSlot()
def _on_compare_clicked(self) -> None:
    """Compare button clicked — emit compare signal for the selected item."""
    idx = self._tree.currentIndex()
    if not idx.isValid():
        return
    source = self._proxy.mapToSource(idx)
    item = self._model.itemFromIndex(source)
    if item and item.data(ROLE_NODE_TYPE) == "file":
        pixel_hash = item.data(ROLE_PIXEL_HASH)
        if pixel_hash and item.data(ROLE_IS_DUPLICATE):
            self.compare_view_requested.emit(pixel_hash)
    # TODO: folder-level comparison (Feature 3d)
```

**Right-click context menu:**

```python
@pyqtSlot(QPoint)
def _on_context_menu(self, position: QPoint) -> None:
    """Show context menu on right-click."""
    idx = self._tree.indexAt(position)
    if not idx.isValid():
        return
    source = self._proxy.mapToSource(idx)
    item = self._model.itemFromIndex(source)
    if item is None:
        return

    if item.data(ROLE_NODE_TYPE) == "file" and item.data(ROLE_IS_DUPLICATE):
        menu = QMenu(self)
        action = menu.addAction(self.tr("Compare Duplicates"))
        action.triggered.connect(
            lambda: self.compare_view_requested.emit(item.data(ROLE_PIXEL_HASH))
        )
        menu.exec(self._tree.viewport().mapToGlobal(position))
```

Additional imports needed: `QPushButton`, `QMenu`, `QPoint`.

#### 3d — Folder-Level Duplication Grouping

**New custom roles** (add to top of `results_panel.py`):

```python
ROLE_IS_FOLDER_DUPLICATED = Qt.ItemDataRole.UserRole + 7
ROLE_FOLDER_FILE_COUNT = Qt.ItemDataRole.UserRole + 8
```

**Detection — `_compute_folder_duplication()` method:**

```python
def _compute_folder_duplication(self) -> None:
    """Walk the tree bottom-up and mark folders where ALL files are duplicates."""
    self._compute_folder_dup_recursive(self._model.invisibleRootItem())

def _compute_folder_dup_recursive(self, parent: QStandardItem) -> tuple[int, int]:
    """Returns (total_file_count, duplicate_file_count) for subtree."""
    total = 0
    duplicated = 0

    for row in range(parent.rowCount()):
        child = parent.child(row, 0)
        if child is None:
            continue

        if child.data(ROLE_NODE_TYPE) == "file":
            total += 1
            if child.data(ROLE_IS_DUPLICATE):
                duplicated += 1

        elif child.data(ROLE_NODE_TYPE) == "folder":
            sub_total, sub_dup = self._compute_folder_dup_recursive(child)
            total += sub_total
            duplicated += sub_dup

            # Mark folder as fully duplicated if all files are duplicates
            is_fully_dup = sub_total > 0 and sub_total == sub_dup
            child.setData(is_fully_dup, ROLE_IS_FOLDER_DUPLICATED)
            child.setData(sub_total, ROLE_FOLDER_FILE_COUNT)

            # Set badge on the folder's status column
            badge_item = parent.child(row, 1)
            if badge_item and is_fully_dup:
                badge_item.setText(
                    self.tr("● DUPLICATED FOLDER ({0} files)").format(sub_total)
                )

    return total, duplicated
```

Call `_compute_folder_duplication()` at the end of `reload()` and `_flush_pending()` (after badge updates).

**Filter behavior change in `_DuplicateFilterProxy`:**

```python
def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
    if self._filter_mode == FILTER_ALL:
        return True

    idx = self.sourceModel().index(source_row, 0, source_parent)
    node_type = idx.data(ROLE_NODE_TYPE)

    if node_type == "file":
        # If parent folder is fully duplicated and we're in "Duplicates Only",
        # hide individual files (the folder badge represents them)
        parent_idx = source_parent
        if parent_idx.isValid():
            parent_is_folder_dup = parent_idx.data(ROLE_IS_FOLDER_DUPLICATED)
            if parent_is_folder_dup and self._filter_mode == FILTER_DUPLICATES_ONLY:
                return False  # Hidden; folder badge represents this group

        if self._filter_mode == FILTER_DUPLICATES_ONLY:
            return bool(idx.data(ROLE_IS_DUPLICATE))
        if self._filter_mode == FILTER_CROSS_LIBRARY:
            return bool(idx.data(ROLE_IS_CROSS_LIBRARY))
        return True

    # Folder node
    if node_type == "folder":
        # Fully duplicated folders are always visible in Duplicates filter
        if self._filter_mode == FILTER_DUPLICATES_ONLY and idx.data(ROLE_IS_FOLDER_DUPLICATED):
            return True
        # Otherwise: accept if any child is accepted (recursive)
        model = self.sourceModel()
        for child_row in range(model.rowCount(idx)):
            if self.filterAcceptsRow(child_row, idx):
                return True
        return False
```

**User expansion override:** When the user manually expands a fully-duplicated folder in "Duplicates Only" mode, the individual files should become visible. This can be achieved by:
- Connecting `self._tree.expanded` signal to a slot that temporarily overrides the filter for that folder's children
- Or by toggling the `ROLE_IS_FOLDER_DUPLICATED` flag off when expanded, and back on when collapsed

**Compare view for folders** — extend `dejaview/ui/compare_view.py`:
- Add a new signal or overload `compare_view_requested` to accept folder paths
- When a fully-duplicated folder is selected, find all other folders containing the same set of pixel hashes
- Show folder-level tiles: folder name, file count, total size, location
- Include an expandable file list within each tile

### Example UX Flow

**Before (current behavior with "Duplicates Only" filter):**
```
Photos/
  ├── vacation/
  │   ├── IMG_001.jpg   ● DUPLICATE
  │   ├── IMG_002.jpg   ● DUPLICATE
  │   └── IMG_003.jpg   ● DUPLICATE
  └── backup/
      ├── IMG_001.jpg   ● DUPLICATE
      ├── IMG_002.jpg   ● DUPLICATE
      └── IMG_003.jpg   ● DUPLICATE
```

**After (proposed, with "Duplicates Only" filter):**
```
Photos/
  ├── vacation/           ● DUPLICATED FOLDER (3 files)
  └── backup/             ● DUPLICATED FOLDER (3 files)
```

The user clicks **Compare** on `vacation/` to see it alongside `backup/` and decide which to keep.

### User Guide Changes for Feature 3

**`dejaview/resources/help/USER_GUIDE.md`:**

After Step 2 — Scan section (after "Partial results remain visible."), add:

> After scanning, the app automatically switches to the **Duplicates Only** view if any duplicates were found. The status bar shows a summary like: *Scan complete: 150 files scanned, 12 duplicates in 5 groups.*

Rewrite Step 3 — Review Results, line 97:
- **Old:** "Click any file with a **● DUPLICATE** badge to open the Compare View and see all copies side by side."
- **New:** "Select any file with a **● DUPLICATE** badge, then click the **Compare** button in the toolbar. You can also double-click the file, or right-click and choose **Compare Duplicates**."

Add new paragraph to Step 3:

> When all files inside a folder are duplicates, the folder itself is shown with a **● DUPLICATED FOLDER** badge and a file count. You can expand the folder to see individual files, or compare the folder as a whole to see where the duplicated content exists.

In Step 4 — Compare Duplicates, add:

> If you compare a duplicated folder, the Compare View shows folder-level tiles with the folder path, total file count, and size. This makes it easy to identify and manage entire folder copies.

**`dejaview/resources/help/USER_GUIDE_HU.md`:** Same changes translated to Hungarian.

**Root-level `USER_GUIDE.md`:** Keep in sync with the in-app English guide.

---

## Summary of All Files to Modify

| File | Feature(s) | Changes |
|------|-----------|---------|
| `dejaview/ui/main_window.py` | 1, 2, 3 | Remove View menu; wire Settings action; auto-filter + scan summary after scan |
| `dejaview/ui/settings_dialog.py` | 2 | **New file** — SettingsDialog with language + theme sections |
| `dejaview/data/db.py` | 2 | Add `app_config` table + `get_app_config()` / `upsert_app_config()` methods |
| `dejaview/main.py` | 2 | Read language preference from `app_config` before OS locale fallback |
| `dejaview/ui/results_panel.py` | 3 | Compare button, right-click context menu, folder-level duplication detection + badges, filter proxy updates |
| `dejaview/ui/compare_view.py` | 3 | Support folder-level comparison tiles |
| `dejaview/resources/help/USER_GUIDE.md` | 1, 2, 3 | Update menu diagram, Settings section, Steps 2–4 for new UX |
| `dejaview/resources/help/USER_GUIDE_HU.md` | 1, 2, 3 | Same updates in Hungarian |
| `USER_GUIDE.md` (root) | 1, 2, 3 | Keep in sync with in-app English guide |
| `dejaview/resources/i18n/app.ts` | 1, 2, 3 | Remove View; add Settings, Compare, and folder badge strings |
| `dejaview/resources/i18n/app_hu.ts` | 1, 2, 3 | Hungarian translations for all new/changed strings |

## Verification Checklist

- [ ] Launch app → menu bar shows: File | Scan | Share | Help (no View)
- [ ] File > Settings → dialog opens with Language and Theme sections
- [ ] Change language to Magyar → save → restart → verify Hungarian UI
- [ ] Change language to Auto → save → restart → verify OS-locale behavior restored
- [ ] Add folders → run scan → verify auto-switch to "Duplicates Only" filter when duplicates found
- [ ] Verify status bar shows: "Scan complete: N files scanned, N duplicates in N groups."
- [ ] Run scan with no duplicates → verify "No duplicates found." and filter stays on All
- [ ] Single-click a duplicate file → Compare button enables → click it → CompareView opens
- [ ] Right-click a duplicate file → context menu shows "Compare Duplicates" → click → CompareView opens
- [ ] Double-click still works (backward compatibility)
- [ ] Folder with all duplicate files shows "● DUPLICATED FOLDER (N files)" badge
- [ ] In "Duplicates Only" mode, fully-duplicated folders are collapsed (children hidden)
- [ ] Expanding a fully-duplicated folder reveals individual files
- [ ] Compare button works on a duplicated folder → folder-level CompareView
- [ ] Help > User Guide → all sections reflect the new behavior
- [ ] `python -m pytest tests/unit/ --no-cov -q` — all tests pass
