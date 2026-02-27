"""
ui/results_panel.py — Results tree view (plan §Dev Phases Phase 3, Req 4.3).

Shows all scanned files in their original directory tree structure.
Filter bar: All | Duplicates Only (Cross-Library added in Phase 5).
Duplicate badges: "● DUPLICATE" on files that share a pixel_hash.

UI update rate-limiting (plan §Resource Usage — UI update rate-limiting):
  Incoming hash_complete signals are queued; the tree refreshes at most once
  every 200 ms via a QTimer debounce.  file_discovered signals during Pass 1
  also go through the debounce queue.

Emits compare_view_requested(str pixel_hash) when a duplicate file is clicked.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import (
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QPushButton,
    QRadioButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

log = logging.getLogger(__name__)

# Custom data roles stored on each leaf item (file row).
ROLE_FILE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_FILE_PATH = Qt.ItemDataRole.UserRole + 2
ROLE_PIXEL_HASH = Qt.ItemDataRole.UserRole + 3
ROLE_IS_DUPLICATE = Qt.ItemDataRole.UserRole + 4
ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 5  # "folder" or "file"
ROLE_IS_CROSS_LIBRARY = Qt.ItemDataRole.UserRole + 6  # Phase 5
ROLE_IS_FOLDER_DUPLICATED = Qt.ItemDataRole.UserRole + 7  # Feature 3d
ROLE_FOLDER_FILE_COUNT = Qt.ItemDataRole.UserRole + 8  # Feature 3d

# Filter modes
FILTER_ALL = "all"
FILTER_DUPLICATES_ONLY = "duplicates_only"
FILTER_CROSS_LIBRARY = "cross_library"  # Phase 5

# Debounce interval (plan §Resource Usage — UI update rate-limiting).
_DEBOUNCE_MS = 200

# Tree indentation bounds (dynamic indent fitting).
_DEFAULT_INDENT = 20
_MIN_INDENT = 8


@dataclass
class _ViewState:
    """Snapshot of user-adjustable view settings, saved/restored across reloads."""

    filter_mode: str = FILTER_ALL
    expanded_paths: set[str] = field(default_factory=set)
    scroll_value: int = 0
    selected_path: str | None = None


class _DuplicateFilterProxy(QSortFilterProxyModel):
    """Proxy that hides non-duplicate files when Duplicates Only filter is active.

    Shows files in their original folder context (plan §Workflow 2):
      "Files are still shown in their original folder context."
    A folder node is visible iff it has at least one visible descendant.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_mode: str = FILTER_ALL

    def set_filter_mode(self, mode: str) -> None:
        self._filter_mode = mode
        self.invalidateFilter()

    @property
    def filter_mode(self) -> str:
        return self._filter_mode

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if self._filter_mode == FILTER_ALL:
            return True

        idx = self.sourceModel().index(source_row, 0, source_parent)
        node_type = idx.data(ROLE_NODE_TYPE)

        if node_type == "file":
            # If parent folder is fully duplicated in Duplicates Only mode,
            # hide individual files — the folder badge represents them.
            if self._filter_mode == FILTER_DUPLICATES_ONLY and source_parent.isValid():
                parent_is_folder_dup = source_parent.data(ROLE_IS_FOLDER_DUPLICATED)
                if parent_is_folder_dup:
                    return False

            if self._filter_mode == FILTER_DUPLICATES_ONLY:
                return bool(idx.data(ROLE_IS_DUPLICATE))
            if self._filter_mode == FILTER_CROSS_LIBRARY:
                return bool(idx.data(ROLE_IS_CROSS_LIBRARY))
            return True

        # Folder node.
        if node_type == "folder":
            # Fully duplicated folders are always visible in Duplicates filter.
            if self._filter_mode == FILTER_DUPLICATES_ONLY and idx.data(ROLE_IS_FOLDER_DUPLICATED):
                return True
            # Otherwise: accept if any child is accepted (recursive).
            model = self.sourceModel()
            for child_row in range(model.rowCount(idx)):
                if self.filterAcceptsRow(child_row, idx):
                    return True
            return False

        return False


class ResultsPanel(QWidget):
    """
    Right pane: folder tree with filters and duplicate badges (plan §UI Layout).
    """

    compare_view_requested = pyqtSignal(str)  # pixel_hash
    compare_folder_requested = pyqtSignal(str)  # folder_path

    def __init__(self, db: Database, session_id: int | None = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id

        # Pending updates queued by scanner signals, flushed by debounce timer.
        self._pending_file_ids: list[int] = []
        self._pending_hash_ids: list[int] = []

        # Flag: only run _compute_folder_duplication() when a directory
        # boundary has been reached, not on every debounce tick.
        self._needs_folder_recompute: bool = False

        # Track duplicate pixel_hashes for badge updates.
        self._duplicate_hashes: set[str] = set()

        # Track cross-library pixel_hashes (Phase 5).
        self._cross_library_hashes: set[str] = set()

        # Folder path → QStandardItem mapping for incremental tree building.
        self._folder_items: dict[str, QStandardItem] = {}

        # Saved view state for persistence across reloads.
        self._saved_state: _ViewState | None = None

        self._build_ui()
        self._build_debounce_timer()

    # ── Public API ───────────────────────────────────────────────────────

    def set_session_id(self, session_id: int) -> None:
        self._session_id = session_id
        self._saved_state = None  # Fresh session — no state to restore.
        self.reload()

    def reload(self) -> None:
        """Full reload of the tree from the database."""
        # Save current view state before clearing (if tree has content).
        state = (
            self._save_view_state()
            if self._model.rowCount() > 0
            else self._saved_state
        )

        self._model.clear()
        self._model.setHorizontalHeaderLabels([self.tr("Name"), self.tr("Status")])
        self._folder_items.clear()
        self._duplicate_hashes.clear()
        self._cross_library_hashes.clear()

        if self._session_id is None:
            return

        # Load duplicate hashes.
        for row in self._db.get_duplicate_groups(self._session_id):
            self._duplicate_hashes.add(row["pixel_hash"])

        # Load cross-library hashes (Phase 5).
        for row in self._db.get_cross_library_matches(self._session_id):
            self._cross_library_hashes.add(row["pixel_hash"])

        # Enable/disable Cross-Library radio based on data availability.
        self._radio_cross.setEnabled(len(self._cross_library_hashes) > 0)

        # Load all files for this session and build the tree.
        files = self._db.get_files_for_session(self._session_id)
        for f in files:
            if f["status"] != "active":
                continue
            self._add_file_to_tree(
                file_id=f["id"],
                path=f["path"],
                pixel_hash=f["pixel_hash"],
            )

        # Compute folder-level duplication badges.
        self._compute_folder_duplication()

        # Dynamic view adjustments.
        self._adjust_indentation()
        self._fit_columns()

        # Restore saved state or apply smart expand for first load.
        if state:
            self._restore_view_state(state)
        else:
            self._smart_expand()

    def update_cross_library_data(self) -> None:
        """Refresh cross-library hashes after an import and update filter/tags.

        Called by main_window after Share > Import completes (Phase 5).
        Does a full reload to re-tag all items with updated cross-library status.
        """
        self.reload()

    # ── Scanner signal slots ─────────────────────────────────────────────

    @pyqtSlot(int, str)
    def on_file_discovered(self, file_id: int, path: str) -> None:
        """Called during Pass 1 — queue for debounced tree insert."""
        self._pending_file_ids.append(file_id)
        self._ensure_timer_running()

    @pyqtSlot(int, str)
    def on_hash_complete(self, file_id: int, pixel_hash: str) -> None:
        """Called during Pass 2 — queue for debounced badge update."""
        self._pending_hash_ids.append(file_id)
        self._ensure_timer_running()

    @pyqtSlot(list)
    def on_duplicate_found(self, file_ids: list[int]) -> None:
        """Called when a new duplicate group is confirmed."""
        # Refresh duplicate hashes from DB (cheap query).
        if self._session_id is not None:
            for row in self._db.get_duplicate_groups(self._session_id):
                self._duplicate_hashes.add(row["pixel_hash"])
        # Queue badge refresh for affected files.
        self._pending_hash_ids.extend(file_ids)
        self._ensure_timer_running()

    @pyqtSlot(str)
    def on_directory_hashed(self, dir_path: str) -> None:
        """Called after all files in a directory have been hashed.

        Forces an immediate flush of pending updates and recomputes
        folder-level duplication badges so completed directories show
        accurate results for mid-scan browsing.
        """
        self._needs_folder_recompute = True
        self._flush_pending()

    # ── Filter controls ──────────────────────────────────────────────────

    def set_filter(self, mode: str) -> None:
        """Programmatically set the filter mode."""
        self._proxy.set_filter_mode(mode)
        if mode == FILTER_ALL:
            self._radio_all.setChecked(True)
        elif mode == FILTER_DUPLICATES_ONLY:
            self._radio_dupes.setChecked(True)
        elif mode == FILTER_CROSS_LIBRARY:
            self._radio_cross.setChecked(True)

    @property
    def current_filter(self) -> str:
        return self._proxy.filter_mode

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Filter bar (plan §Workflow 2 — filter bar above the tree).
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(6, 4, 6, 0)

        self._radio_all = QRadioButton(self.tr("All"), self)
        self._radio_dupes = QRadioButton(self.tr("Duplicates Only"), self)
        self._radio_cross = QRadioButton(self.tr("Cross-Library"), self)
        self._radio_cross.setEnabled(False)  # Enabled when cross-library data exists

        self._radio_all.setChecked(True)

        self._filter_group = QButtonGroup(self)
        self._filter_group.addButton(self._radio_all, 0)
        self._filter_group.addButton(self._radio_dupes, 1)
        self._filter_group.addButton(self._radio_cross, 2)

        filter_row.addWidget(self._radio_all)
        filter_row.addWidget(self._radio_dupes)
        filter_row.addWidget(self._radio_cross)
        filter_row.addStretch()

        # Compare button (enabled when a duplicate is selected).
        self._compare_btn = QPushButton(self.tr("Compare"), self)
        self._compare_btn.setObjectName("compare_btn")
        self._compare_btn.setEnabled(False)
        filter_row.addWidget(self._compare_btn)

        layout.addLayout(filter_row)

        # Tree view.
        self._model = QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels([self.tr("Name"), self.tr("Status")])

        self._proxy = _DuplicateFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._tree = QTreeView(self)
        self._tree.setModel(self._proxy)
        self._tree.setHeaderHidden(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._tree)

        # Context menu on tree.
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        # Enable/disable Compare button based on selection.
        self._tree.selectionModel().currentChanged.connect(self._on_selection_changed)

        # Folder expansion override: when user expands a fully-duplicated folder,
        # temporarily clear the flag so children become visible.
        self._tree.expanded.connect(self._on_folder_expanded)
        self._tree.collapsed.connect(self._on_folder_collapsed)

        # Signals.
        self._filter_group.idToggled.connect(self._on_filter_changed)
        self._tree.doubleClicked.connect(self._on_item_double_clicked)
        self._compare_btn.clicked.connect(self._on_compare_clicked)

    def _build_debounce_timer(self) -> None:
        """200ms debounce timer (plan §Resource Usage — UI update rate-limiting)."""
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setInterval(_DEBOUNCE_MS)
        self._debounce_timer.setSingleShot(False)
        self._debounce_timer.timeout.connect(self._flush_pending)

    def _ensure_timer_running(self) -> None:
        if not self._debounce_timer.isActive():
            self._debounce_timer.start()

    # ── Debounce flush ───────────────────────────────────────────────────

    @pyqtSlot()
    def _flush_pending(self) -> None:
        """Process queued file discoveries and hash completions."""
        # Process new file discoveries (Pass 1).
        file_ids = self._pending_file_ids[:]
        self._pending_file_ids.clear()
        for file_id in file_ids:
            row = self._db.get_file(file_id)
            if row and row["status"] == "active":
                self._add_file_to_tree(
                    file_id=row["id"],
                    path=row["path"],
                    pixel_hash=row["pixel_hash"],
                )

        # Process hash completions / duplicate badge updates (Pass 2).
        hash_ids = self._pending_hash_ids[:]
        self._pending_hash_ids.clear()
        for file_id in hash_ids:
            self._update_file_badge(file_id)

        # Recompute folder-level duplication only at directory boundaries,
        # not on every debounce tick (O(N) tree walk is expensive mid-scan).
        if hash_ids and self._needs_folder_recompute:
            self._compute_folder_duplication()
            self._needs_folder_recompute = False

        # Auto-fit columns after incremental updates.
        if file_ids:
            self._fit_columns()

        # Stop timer if nothing pending.
        if not self._pending_file_ids and not self._pending_hash_ids:
            self._debounce_timer.stop()

    # ── Tree model helpers ───────────────────────────────────────────────

    def _add_file_to_tree(
        self, file_id: int, path: str, pixel_hash: Optional[str]
    ) -> None:
        """Insert a file leaf under its folder hierarchy."""
        # Derive folder chain from the file path.
        dir_path = os.path.dirname(path)
        filename = os.path.basename(path)

        parent_item = self._get_or_create_folder(dir_path)

        # Check if file already exists (idempotent for resume).
        for row_idx in range(parent_item.rowCount()):
            child = parent_item.child(row_idx, 0)
            if child and child.data(ROLE_FILE_ID) == file_id:
                return  # already in tree

        is_dup = pixel_hash in self._duplicate_hashes if pixel_hash else False
        is_cross = pixel_hash in self._cross_library_hashes if pixel_hash else False

        name_item = QStandardItem(filename)
        name_item.setData(file_id, ROLE_FILE_ID)
        name_item.setData(path, ROLE_FILE_PATH)
        name_item.setData(pixel_hash, ROLE_PIXEL_HASH)
        name_item.setData(is_dup, ROLE_IS_DUPLICATE)
        name_item.setData(is_cross, ROLE_IS_CROSS_LIBRARY)
        name_item.setData("file", ROLE_NODE_TYPE)
        name_item.setEditable(False)

        badge_item = QStandardItem(self.tr("\u25cf DUPLICATE") if is_dup else "")
        badge_item.setEditable(False)

        parent_item.appendRow([name_item, badge_item])

    def _get_or_create_folder(self, dir_path: str) -> QStandardItem:
        """Return (and cache) the QStandardItem for a folder node, creating parents as needed."""
        if not dir_path:
            return self._model.invisibleRootItem()

        if dir_path in self._folder_items:
            return self._folder_items[dir_path]

        # Walk up to find the nearest existing ancestor.
        parent_dir = os.path.dirname(dir_path)
        folder_name = os.path.basename(dir_path)

        # For drive roots like "C:\", basename is empty; use the full path.
        if not folder_name:
            folder_name = dir_path

        parent_item = self._get_or_create_folder(parent_dir) if parent_dir != dir_path else self._model.invisibleRootItem()

        # Check if this folder already exists under the parent.
        for row_idx in range(parent_item.rowCount()):
            child = parent_item.child(row_idx, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder" and child.text() == folder_name:
                self._folder_items[dir_path] = child
                return child

        folder_item = QStandardItem(folder_name)
        folder_item.setData("folder", ROLE_NODE_TYPE)
        folder_item.setEditable(False)

        spacer_item = QStandardItem("")
        spacer_item.setEditable(False)

        parent_item.appendRow([folder_item, spacer_item])
        self._folder_items[dir_path] = folder_item
        return folder_item

    def _update_file_badge(self, file_id: int) -> None:
        """Re-read a file's pixel_hash from DB and update its badge in the tree."""
        row = self._db.get_file(file_id)
        if not row:
            return

        pixel_hash = row["pixel_hash"]
        is_dup = pixel_hash in self._duplicate_hashes if pixel_hash else False

        item = self._find_file_item(file_id)
        if item is None:
            return

        item.setData(pixel_hash, ROLE_PIXEL_HASH)
        item.setData(is_dup, ROLE_IS_DUPLICATE)

        # Update the badge column (sibling at column 1).
        parent = item.parent() or self._model.invisibleRootItem()
        badge_item = parent.child(item.row(), 1)
        if badge_item:
            badge_item.setText(self.tr("\u25cf DUPLICATE") if is_dup else "")

    # ── Folder-level duplication detection (Feature 3d) ────────────────

    def _compute_folder_duplication(self) -> None:
        """Walk the tree bottom-up and mark folders where ALL files are duplicates."""
        self._compute_folder_dup_recursive(self._model.invisibleRootItem())

    def _compute_folder_dup_recursive(self, parent: QStandardItem) -> tuple:
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

                is_fully_dup = sub_total > 0 and sub_total == sub_dup
                child.setData(is_fully_dup, ROLE_IS_FOLDER_DUPLICATED)
                child.setData(sub_total, ROLE_FOLDER_FILE_COUNT)

                badge_item = parent.child(row, 1)
                if badge_item:
                    if is_fully_dup:
                        badge_item.setText(
                            self.tr("\u25cf DUPLICATED FOLDER ({0} files)").format(sub_total)
                        )
                    else:
                        # Clear any previous folder badge if no longer fully duplicated.
                        if badge_item.text():
                            badge_item.setText("")

        return total, duplicated

    def _find_file_item(self, file_id: int) -> Optional[QStandardItem]:
        """Linear search for a file item by file_id. Acceptable for thousands of items."""
        return self._find_file_item_recursive(self._model.invisibleRootItem(), file_id)

    def _find_file_item_recursive(
        self, parent: QStandardItem, file_id: int
    ) -> Optional[QStandardItem]:
        for row_idx in range(parent.rowCount()):
            child = parent.child(row_idx, 0)
            if child is None:
                continue
            if child.data(ROLE_NODE_TYPE) == "file" and child.data(ROLE_FILE_ID) == file_id:
                return child
            if child.data(ROLE_NODE_TYPE) == "folder":
                result = self._find_file_item_recursive(child, file_id)
                if result:
                    return result
        return None

    # ── View state persistence ──────────────────────────────────────────

    def _save_view_state(self) -> _ViewState:
        """Capture current filter, expansion, scroll, and selection."""
        state = _ViewState()
        state.filter_mode = self._proxy.filter_mode

        state.expanded_paths = set()
        self._collect_expanded(self._model.invisibleRootItem(), state.expanded_paths)

        state.scroll_value = self._tree.verticalScrollBar().value()

        idx = self._tree.currentIndex()
        if idx.isValid():
            src = self._proxy.mapToSource(idx)
            item = self._model.itemFromIndex(src)
            if item and item.data(ROLE_NODE_TYPE) == "file":
                state.selected_path = item.data(ROLE_FILE_PATH)

        return state

    def _collect_expanded(self, parent: QStandardItem, paths: set[str]) -> None:
        """Walk the tree and record expanded folder paths."""
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder":
                proxy_idx = self._proxy.mapFromSource(child.index())
                if proxy_idx.isValid() and self._tree.isExpanded(proxy_idx):
                    for path, item in self._folder_items.items():
                        if item is child:
                            paths.add(path)
                            break
                self._collect_expanded(child, paths)

    def _restore_view_state(self, state: _ViewState) -> None:
        """Restore filter, expansion, scroll, and selection from a snapshot."""
        self.set_filter(state.filter_mode)

        for folder_path, item in self._folder_items.items():
            proxy_idx = self._proxy.mapFromSource(item.index())
            if proxy_idx.isValid():
                self._tree.setExpanded(proxy_idx, folder_path in state.expanded_paths)

        QTimer.singleShot(
            0, lambda v=state.scroll_value: self._tree.verticalScrollBar().setValue(v)
        )

        if state.selected_path:
            item = self._find_file_by_path(state.selected_path)
            if item:
                proxy_idx = self._proxy.mapFromSource(item.index())
                if proxy_idx.isValid():
                    self._tree.setCurrentIndex(proxy_idx)

    def _find_file_by_path(self, path: str) -> Optional[QStandardItem]:
        """Find a file item by its ROLE_FILE_PATH."""
        return self._find_by_path_recursive(self._model.invisibleRootItem(), path)

    def _find_by_path_recursive(
        self, parent: QStandardItem, path: str
    ) -> Optional[QStandardItem]:
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child is None:
                continue
            if child.data(ROLE_NODE_TYPE) == "file" and child.data(ROLE_FILE_PATH) == path:
                return child
            if child.data(ROLE_NODE_TYPE) == "folder":
                result = self._find_by_path_recursive(child, path)
                if result:
                    return result
        return None

    # ── Dynamic view adjustment ──────────────────────────────────────────

    def _fit_columns(self) -> None:
        """Auto-fit the Name column to content, floored at viewport width."""
        self._tree.resizeColumnToContents(0)
        viewport_width = self._tree.viewport().width()
        status_width = self._tree.columnWidth(1)
        min_name_width = viewport_width - status_width - 4
        if self._tree.columnWidth(0) < min_name_width:
            self._tree.setColumnWidth(0, min_name_width)

    def _max_depth(self, parent: Optional[QStandardItem] = None, current: int = 0) -> int:
        """Return the maximum folder nesting depth in the tree."""
        effective: QStandardItem = parent if parent is not None else self._model.invisibleRootItem()
        deepest = current
        for row in range(effective.rowCount()):
            child = effective.child(row, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder":
                deepest = max(deepest, self._max_depth(child, current + 1))
        return deepest

    def _adjust_indentation(self) -> None:
        """Scale tree indentation inversely with depth."""
        depth = self._max_depth()
        if depth <= 4:
            indent = _DEFAULT_INDENT
        else:
            indent = max(_MIN_INDENT, _DEFAULT_INDENT * 4 // depth)
        self._tree.setIndentation(indent)

    # ── Smart expand/collapse ────────────────────────────────────────────

    def _smart_expand(self) -> None:
        """Expand folders based on filter mode and content."""
        mode = self._proxy.filter_mode
        if mode == FILTER_ALL:
            self._expand_to_depth(self._model.invisibleRootItem(), max_depth=2, current=0)
        elif mode in (FILTER_DUPLICATES_ONLY, FILTER_CROSS_LIBRARY):
            self._expand_paths_to_matches()

    def _expand_to_depth(
        self, parent: QStandardItem, max_depth: int, current: int
    ) -> None:
        """Expand folders up to *max_depth* levels, collapse deeper ones."""
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder":
                proxy_idx = self._proxy.mapFromSource(child.index())
                if proxy_idx.isValid():
                    self._tree.setExpanded(proxy_idx, current < max_depth)
                if current < max_depth:
                    self._expand_to_depth(child, max_depth, current + 1)

    def _expand_paths_to_matches(self) -> None:
        """Expand only folder chains leading to duplicate/cross-library files."""
        self._tree.collapseAll()
        target_hashes = (
            self._duplicate_hashes
            if self._proxy.filter_mode == FILTER_DUPLICATES_ONLY
            else self._cross_library_hashes
        )
        self._expand_ancestors_of_matches(self._model.invisibleRootItem(), target_hashes)

    def _expand_ancestors_of_matches(
        self, parent: QStandardItem, target_hashes: set[str]
    ) -> bool:
        """Recursively expand folders containing matching files."""
        has_match = False
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child is None:
                continue
            if child.data(ROLE_NODE_TYPE) == "file":
                ph = child.data(ROLE_PIXEL_HASH)
                if ph and ph in target_hashes:
                    has_match = True
            elif child.data(ROLE_NODE_TYPE) == "folder":
                if self._expand_ancestors_of_matches(child, target_hashes):
                    proxy_idx = self._proxy.mapFromSource(child.index())
                    if proxy_idx.isValid():
                        self._tree.setExpanded(proxy_idx, True)
                    has_match = True
        return has_match

    # ── Slots ────────────────────────────────────────────────────────────

    @pyqtSlot(QModelIndex)
    def _on_folder_expanded(self, proxy_index: QModelIndex) -> None:
        """When user expands a fully-duplicated folder, clear the flag so children show."""
        if self._proxy.filter_mode != FILTER_DUPLICATES_ONLY:
            return
        source = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source)
        if item and item.data(ROLE_IS_FOLDER_DUPLICATED):
            item.setData(False, ROLE_IS_FOLDER_DUPLICATED)
            self._proxy.invalidateFilter()

    @pyqtSlot(QModelIndex)
    def _on_folder_collapsed(self, proxy_index: QModelIndex) -> None:
        """When user collapses a folder that was fully duplicated, restore the flag."""
        if self._proxy.filter_mode != FILTER_DUPLICATES_ONLY:
            return
        source = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source)
        if item and item.data(ROLE_NODE_TYPE) == "folder":
            # Re-check if all children are duplicates.
            total, duped = self._compute_folder_dup_recursive(item)
            if total > 0 and total == duped:
                item.setData(True, ROLE_IS_FOLDER_DUPLICATED)
                self._proxy.invalidateFilter()

    @pyqtSlot(int, bool)
    def _on_filter_changed(self, button_id: int, checked: bool) -> None:
        if not checked:
            return
        mode_map = {0: FILTER_ALL, 1: FILTER_DUPLICATES_ONLY, 2: FILTER_CROSS_LIBRARY}
        mode = mode_map.get(button_id, FILTER_ALL)
        self._proxy.set_filter_mode(mode)
        self._smart_expand()

    @pyqtSlot(QModelIndex)
    def _on_item_double_clicked(self, proxy_index: QModelIndex) -> None:
        """Double-click a duplicate file → emit compare_view_requested(pixel_hash)."""
        source_index = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source_index)
        if item is None:
            return
        if item.data(ROLE_NODE_TYPE) != "file":
            return
        pixel_hash = item.data(ROLE_PIXEL_HASH)
        is_dup = item.data(ROLE_IS_DUPLICATE)
        if pixel_hash and is_dup:
            self.compare_view_requested.emit(pixel_hash)

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
        is_file = item.data(ROLE_NODE_TYPE) == "file"
        is_dup = bool(item.data(ROLE_IS_DUPLICATE))
        is_folder_dup = bool(item.data(ROLE_IS_FOLDER_DUPLICATED)) if item.data(ROLE_NODE_TYPE) == "folder" else False
        self._compare_btn.setEnabled((is_file and is_dup) or is_folder_dup)

    @pyqtSlot()
    def _on_compare_clicked(self) -> None:
        """Compare button clicked — emit compare signal for the selected item."""
        idx = self._tree.currentIndex()
        if not idx.isValid():
            return
        source = self._proxy.mapToSource(idx)
        item = self._model.itemFromIndex(source)
        if item is None:
            return
        if item.data(ROLE_NODE_TYPE) == "file":
            pixel_hash = item.data(ROLE_PIXEL_HASH)
            if pixel_hash and item.data(ROLE_IS_DUPLICATE):
                self.compare_view_requested.emit(pixel_hash)
        elif item.data(ROLE_NODE_TYPE) == "folder" and item.data(ROLE_IS_FOLDER_DUPLICATED):
            # Find the folder path from the folder_items mapping.
            for path, folder_item in self._folder_items.items():
                if folder_item is item:
                    self.compare_folder_requested.emit(path)
                    break

    @pyqtSlot("QPoint")
    def _on_context_menu(self, position) -> None:
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
            pixel_hash = item.data(ROLE_PIXEL_HASH)
            action = menu.addAction(self.tr("Compare Duplicates"))
            action.triggered.connect(
                lambda: self.compare_view_requested.emit(pixel_hash)
            )
            menu.exec(self._tree.viewport().mapToGlobal(position))

    # ── Helpers for tests ────────────────────────────────────────────────

    def visible_file_count(self) -> int:
        """Count visible file leaf nodes (for test assertions)."""
        return self._count_visible_files(self._proxy, QModelIndex())

    def _count_visible_files(self, model, parent: QModelIndex) -> int:
        count = 0
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            node_type = idx.data(ROLE_NODE_TYPE)
            if node_type == "file":
                count += 1
            elif node_type == "folder":
                count += self._count_visible_files(model, idx)
        return count

    def visible_items_data(self) -> list[dict]:
        """Return data for all visible file items (for test assertions)."""
        result = []
        self._collect_visible(self._proxy, QModelIndex(), result)
        return result

    def _collect_visible(self, model, parent: QModelIndex, result: list) -> None:
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            node_type = idx.data(ROLE_NODE_TYPE)
            if node_type == "file":
                badge_idx = model.index(row, 1, parent)
                result.append({
                    "file_id": idx.data(ROLE_FILE_ID),
                    "path": idx.data(ROLE_FILE_PATH),
                    "pixel_hash": idx.data(ROLE_PIXEL_HASH),
                    "is_duplicate": idx.data(ROLE_IS_DUPLICATE),
                    "is_cross_library": idx.data(ROLE_IS_CROSS_LIBRARY),
                    "badge_text": badge_idx.data(Qt.ItemDataRole.DisplayRole) or "",
                })
            elif node_type == "folder":
                self._collect_visible(model, idx, result)
