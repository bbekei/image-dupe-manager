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

# Filter modes
FILTER_ALL = "all"
FILTER_DUPLICATES_ONLY = "duplicates_only"
FILTER_CROSS_LIBRARY = "cross_library"  # Phase 5

# Debounce interval (plan §Resource Usage — UI update rate-limiting).
_DEBOUNCE_MS = 200


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
            if self._filter_mode == FILTER_DUPLICATES_ONLY:
                return bool(idx.data(ROLE_IS_DUPLICATE))
            if self._filter_mode == FILTER_CROSS_LIBRARY:
                return bool(idx.data(ROLE_IS_CROSS_LIBRARY))
            return True

        # Folder node: accept if any child is accepted (recursive).
        model = self.sourceModel()
        row_count = model.rowCount(idx)
        for child_row in range(row_count):
            if self.filterAcceptsRow(child_row, idx):
                return True
        return False


class ResultsPanel(QWidget):
    """
    Right pane: folder tree with filters and duplicate badges (plan §UI Layout).
    """

    compare_view_requested = pyqtSignal(str)  # pixel_hash

    def __init__(self, db: Database, session_id: int | None = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id

        # Pending updates queued by scanner signals, flushed by debounce timer.
        self._pending_file_ids: list[int] = []
        self._pending_hash_ids: list[int] = []

        # Track duplicate pixel_hashes for badge updates.
        self._duplicate_hashes: set[str] = set()

        # Track cross-library pixel_hashes (Phase 5).
        self._cross_library_hashes: set[str] = set()

        # Folder path → QStandardItem mapping for incremental tree building.
        self._folder_items: dict[str, QStandardItem] = {}

        self._build_ui()
        self._build_debounce_timer()

    # ── Public API ───────────────────────────────────────────────────────

    def set_session_id(self, session_id: int) -> None:
        self._session_id = session_id
        self.reload()

    def reload(self) -> None:
        """Full reload of the tree from the database."""
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

        self._tree.expandAll()

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
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._tree)

        # Signals.
        self._filter_group.idToggled.connect(self._on_filter_changed)
        self._tree.doubleClicked.connect(self._on_item_double_clicked)

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

    # ── Slots ────────────────────────────────────────────────────────────

    @pyqtSlot(int, bool)
    def _on_filter_changed(self, button_id: int, checked: bool) -> None:
        if not checked:
            return
        mode_map = {0: FILTER_ALL, 1: FILTER_DUPLICATES_ONLY, 2: FILTER_CROSS_LIBRARY}
        mode = mode_map.get(button_id, FILTER_ALL)
        self._proxy.set_filter_mode(mode)

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
