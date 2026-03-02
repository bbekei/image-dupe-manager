"""
ui/results_model.py — Shared tree model for results views.

Extracted from results_panel.py to support pluggable views (Pluggable Views feature).
Contains data roles, filter constants, the duplicate filter proxy, and the
ResultsTreeModel that builds/manages the QStandardItemModel tree.

Multiple views (ResultsPanel, PlanningPanel) share a ResultsTreeModel instance
while each maintaining their own proxy filter and QTreeView.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import (
    QCoreApplication,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PyQt6.QtGui import QStandardItem, QStandardItemModel

from core.selection import get_master_copies
from data.db import Database

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom data roles stored on each tree item.
# ---------------------------------------------------------------------------

ROLE_FILE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_FILE_PATH = Qt.ItemDataRole.UserRole + 2
ROLE_PIXEL_HASH = Qt.ItemDataRole.UserRole + 3
ROLE_IS_DUPLICATE = Qt.ItemDataRole.UserRole + 4
ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 5  # "folder" or "file"
ROLE_IS_CROSS_LIBRARY = Qt.ItemDataRole.UserRole + 6
ROLE_IS_FOLDER_DUPLICATED = Qt.ItemDataRole.UserRole + 7
ROLE_FOLDER_FILE_COUNT = Qt.ItemDataRole.UserRole + 8
ROLE_FOLDER_DUP_COUNT = Qt.ItemDataRole.UserRole + 9

# Planning-phase roles.
ROLE_ACTION = Qt.ItemDataRole.UserRole + 10       # "keep" | "delete" | "ignore" | None
ROLE_HAS_DECISION = Qt.ItemDataRole.UserRole + 11  # bool

# Cross-library peer info.
ROLE_PEER_USERNAMES = Qt.ItemDataRole.UserRole + 12  # list[str] of peer names

# Phase 5: Master Copy badge.
ROLE_IS_MASTER = Qt.ItemDataRole.UserRole + 13  # bool — best copy in cluster

# ---------------------------------------------------------------------------
# Filter modes
# ---------------------------------------------------------------------------

FILTER_ALL = "all"
FILTER_DUPLICATES_ONLY = "duplicates_only"
FILTER_CROSS_LIBRARY = "cross_library"

# ---------------------------------------------------------------------------
# UI constants
# ---------------------------------------------------------------------------

_DEBOUNCE_MS = 200
_DEFAULT_INDENT = 20
_MIN_INDENT = 8


# ---------------------------------------------------------------------------
# View state snapshot
# ---------------------------------------------------------------------------

@dataclass
class ViewState:
    """Snapshot of user-adjustable view settings, saved/restored across reloads."""

    filter_mode: str = FILTER_ALL
    expanded_paths: set[str] = field(default_factory=set)
    scroll_value: int = 0
    selected_path: str | None = None


# ---------------------------------------------------------------------------
# Duplicate filter proxy
# ---------------------------------------------------------------------------

class DuplicateFilterProxy(QSortFilterProxyModel):
    """Proxy that hides non-duplicate files when Duplicates Only filter is active.

    Shows files in their original folder context:
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


# ---------------------------------------------------------------------------
# Shared tree model
# ---------------------------------------------------------------------------

def _tr(source: str, disambiguation: str | None = None) -> str:
    """Translate using the ResultsPanel context for backward-compatible badge strings."""
    return QCoreApplication.translate("ResultsPanel", source, disambiguation)


def _file_badge_text(
    is_dup: bool, is_cross: bool, peers: list[str], is_master: bool = False
) -> str:
    """Return the badge column text for a file item."""
    parts = []
    if is_master:
        parts.append(_tr("\u2605 MASTER"))
    if is_dup and is_cross:
        parts.append(_tr("\u25cf DUPLICATE") + " \u2726 " + ", ".join(peers))
    elif is_cross:
        parts.append(_tr("\u2726 CROSS-LIB ({0})").format(", ".join(peers)))
    elif is_dup:
        parts.append(_tr("\u25cf DUPLICATE"))
    return " ".join(parts)


class ResultsTreeModel:
    """Manages the QStandardItemModel tree shared between views.

    This is a plain Python object (not a QWidget). It owns the source model,
    lookup dictionaries, and hash sets, and provides methods for tree building,
    badge updates, and folder-duplication computation.
    """

    def __init__(self):
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([_tr("Name"), _tr("Status"), _tr("Action")])

        self.folder_items: dict[str, QStandardItem] = {}
        self.file_id_to_item: dict[int, QStandardItem] = {}
        self.duplicate_hashes: set[str] = set()
        self.cross_library_hashes: set[str] = set()
        self.cross_library_peers: dict[str, set[str]] = {}  # pixel_hash → {username, ...}
        self.master_file_ids: set[int] = set()  # Phase 5: master copy file IDs
        self._bulk_loading: bool = False  # True during load_from_db to skip O(n²) checks

    # ── Loading ───────────────────────────────────────────────────────

    def load_from_db(self, db: Database, session_id: int | None) -> None:
        """Full rebuild of the tree from the database."""
        self.model.clear()
        self.model.setHorizontalHeaderLabels([_tr("Name"), _tr("Status"), _tr("Action")])
        self.folder_items.clear()
        self.file_id_to_item.clear()
        self.duplicate_hashes.clear()
        self.cross_library_hashes.clear()
        self.cross_library_peers.clear()
        self.master_file_ids.clear()

        if session_id is None:
            return

        # Load duplicate hashes.
        for row in db.get_duplicate_groups(session_id):
            self.duplicate_hashes.add(row["pixel_hash"])

        # Load cross-library hashes and peer usernames.
        for row in db.get_cross_library_matches(session_id):
            h = row["pixel_hash"]
            self.cross_library_hashes.add(h)
            self.cross_library_peers.setdefault(h, set()).add(row["username"])

        # Phase 5: Compute master copies for badge display.
        masters = get_master_copies(db, session_id)
        self.master_file_ids = set(masters.values())

        # Load all files for this session and build the tree.
        # Block signals during bulk load to prevent Qt from processing
        # thousands of layout-change events (one per appendRow call).
        self.model.blockSignals(True)
        self._bulk_loading = True
        try:
            files = db.get_files_for_session(session_id)
            for f in files:
                if f["status"] != "active":
                    continue
                self.add_file_to_tree(
                    file_id=f["id"],
                    path=f["path"],
                    pixel_hash=f["pixel_hash"],
                )

            # Compute folder-level duplication badges.
            self.compute_folder_duplication()
        finally:
            self._bulk_loading = False
            self.model.blockSignals(False)

        # Notify views that the model has been fully rebuilt.
        self.model.layoutChanged.emit()

    # ── Tree building ─────────────────────────────────────────────────

    def add_file_to_tree(
        self, file_id: int, path: str, pixel_hash: Optional[str]
    ) -> None:
        """Insert a file leaf under its folder hierarchy."""
        dir_path = os.path.dirname(path)
        filename = os.path.basename(path)

        parent_item = self.get_or_create_folder(dir_path)

        # Check if file already exists (idempotent for resume).
        # Skipped during bulk load_from_db — the model is always cleared first,
        # so duplicates are impossible and the O(n) scan per file is wasteful.
        if not self._bulk_loading:
            for row_idx in range(parent_item.rowCount()):
                child = parent_item.child(row_idx, 0)
                if child and child.data(ROLE_FILE_ID) == file_id:
                    return  # already in tree

        is_dup = pixel_hash in self.duplicate_hashes if pixel_hash else False
        is_cross = pixel_hash in self.cross_library_hashes if pixel_hash else False
        is_master = file_id in self.master_file_ids
        peers = sorted(self.cross_library_peers.get(pixel_hash, set())) if is_cross else []

        name_item = QStandardItem(filename)
        name_item.setData(file_id, ROLE_FILE_ID)
        name_item.setData(path, ROLE_FILE_PATH)
        name_item.setData(pixel_hash, ROLE_PIXEL_HASH)
        name_item.setData(is_dup, ROLE_IS_DUPLICATE)
        name_item.setData(is_cross, ROLE_IS_CROSS_LIBRARY)
        name_item.setData(is_master, ROLE_IS_MASTER)
        name_item.setData(peers, ROLE_PEER_USERNAMES)
        name_item.setData("file", ROLE_NODE_TYPE)
        name_item.setEditable(False)

        badge_item = QStandardItem(_file_badge_text(is_dup, is_cross, peers, is_master))
        badge_item.setEditable(False)

        action_item = QStandardItem("")
        action_item.setEditable(False)

        parent_item.appendRow([name_item, badge_item, action_item])
        self.file_id_to_item[file_id] = name_item

    def get_or_create_folder(self, dir_path: str) -> QStandardItem:
        """Return (and cache) the QStandardItem for a folder node, creating parents as needed."""
        if not dir_path:
            return self.model.invisibleRootItem()

        if dir_path in self.folder_items:
            return self.folder_items[dir_path]

        parent_dir = os.path.dirname(dir_path)
        folder_name = os.path.basename(dir_path)

        # For drive roots like "C:\", basename is empty; use the full path.
        if not folder_name:
            folder_name = dir_path

        parent_item = (
            self.get_or_create_folder(parent_dir)
            if parent_dir != dir_path
            else self.model.invisibleRootItem()
        )

        # Check if this folder already exists under the parent.
        for row_idx in range(parent_item.rowCount()):
            child = parent_item.child(row_idx, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder" and child.text() == folder_name:
                self.folder_items[dir_path] = child
                return child

        folder_item = QStandardItem(folder_name)
        folder_item.setData("folder", ROLE_NODE_TYPE)
        folder_item.setEditable(False)

        spacer_item = QStandardItem("")
        spacer_item.setEditable(False)

        action_spacer = QStandardItem("")
        action_spacer.setEditable(False)

        parent_item.appendRow([folder_item, spacer_item, action_spacer])
        self.folder_items[dir_path] = folder_item
        return folder_item

    # ── Badge updates ─────────────────────────────────────────────────

    def update_file_badge(self, file_id: int, pixel_hash: str) -> None:
        """Update a file's duplicate / cross-library / master badge in the tree."""
        is_dup = pixel_hash in self.duplicate_hashes if pixel_hash else False
        is_cross = pixel_hash in self.cross_library_hashes if pixel_hash else False
        is_master = file_id in self.master_file_ids
        peers = sorted(self.cross_library_peers.get(pixel_hash, set())) if is_cross else []

        item = self.find_file_item(file_id)
        if item is None:
            return

        item.setData(pixel_hash, ROLE_PIXEL_HASH)
        item.setData(is_dup, ROLE_IS_DUPLICATE)
        item.setData(is_cross, ROLE_IS_CROSS_LIBRARY)
        item.setData(is_master, ROLE_IS_MASTER)
        item.setData(peers, ROLE_PEER_USERNAMES)

        parent = item.parent() or self.model.invisibleRootItem()
        badge_item = parent.child(item.row(), 1)
        if badge_item:
            badge_item.setText(_file_badge_text(is_dup, is_cross, peers, is_master))

    def find_file_item(self, file_id: int) -> Optional[QStandardItem]:
        """O(1) lookup for a file item by file_id."""
        return self.file_id_to_item.get(file_id)

    # ── Folder-level duplication ──────────────────────────────────────

    def compute_folder_duplication(self) -> None:
        """Walk the tree bottom-up and mark folders where ALL files are duplicates."""
        self._compute_folder_dup_recursive(self.model.invisibleRootItem())

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
                child.setData(sub_dup, ROLE_FOLDER_DUP_COUNT)

                badge_item = parent.child(row, 1)
                if badge_item:
                    if is_fully_dup:
                        badge_item.setText(
                            _tr("\u25cf DUPLICATED FOLDER ({0} files)").format(sub_total)
                        )
                    else:
                        if badge_item.text():
                            badge_item.setText("")

        return total, duplicated

    def compute_folder_dup_single(self, parent: QStandardItem) -> tuple:
        """Returns (total_file_count, duplicate_file_count) for a single folder's children."""
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
                total += child.data(ROLE_FOLDER_FILE_COUNT) or 0
                duplicated += child.data(ROLE_FOLDER_DUP_COUNT) or 0
        return total, duplicated

    def recompute_folder_chain(self, dir_path: str) -> None:
        """Recompute duplication badge for *dir_path* and its ancestors."""
        folder_item = self.folder_items.get(dir_path)
        if folder_item is None:
            return

        item = folder_item
        while item is not None:
            total, dup = self.compute_folder_dup_single(item)

            is_fully_dup = total > 0 and total == dup
            item.setData(is_fully_dup, ROLE_IS_FOLDER_DUPLICATED)
            item.setData(total, ROLE_FOLDER_FILE_COUNT)
            item.setData(dup, ROLE_FOLDER_DUP_COUNT)

            parent = item.parent() or self.model.invisibleRootItem()
            badge_item = parent.child(item.row(), 1)
            if badge_item:
                if is_fully_dup:
                    badge_item.setText(
                        _tr("\u25cf DUPLICATED FOLDER ({0} files)").format(total)
                    )
                else:
                    if badge_item.text():
                        badge_item.setText("")

            item = item.parent()
            if item is None:
                break

    # ── View helpers ──────────────────────────────────────────────────

    def max_depth(self, parent: Optional[QStandardItem] = None, current: int = 0) -> int:
        """Return the maximum folder nesting depth in the tree."""
        effective = parent if parent is not None else self.model.invisibleRootItem()
        deepest = current
        for row in range(effective.rowCount()):
            child = effective.child(row, 0)
            if child and child.data(ROLE_NODE_TYPE) == "folder":
                deepest = max(deepest, self.max_depth(child, current + 1))
        return deepest


# ---------------------------------------------------------------------------
# Planning filter proxy
# ---------------------------------------------------------------------------

# Planning scope modes (which items to show before hiding decided ones).
SCOPE_LOCAL_DUPLICATES = "local_duplicates"
SCOPE_CROSS_LIBRARY = "cross_library"
SCOPE_ALL = "all"


class PlanningFilterProxy(DuplicateFilterProxy):
    """Extended filter that combines scope filtering with hiding decided items.

    Used by the PlanningPanel to show only actionable (undecided) items.
    Scope determines which category of items is shown (local duplicates,
    cross-library, or both), then decided items are hidden on top of that.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._decided_file_ids: set[int] = set()
        self._scope: str = SCOPE_LOCAL_DUPLICATES

    @property
    def scope(self) -> str:
        return self._scope

    def set_scope(self, scope: str) -> None:
        """Set which category of items to show."""
        self._scope = scope
        # Map scope to the underlying filter mode.
        if scope == SCOPE_LOCAL_DUPLICATES:
            self._filter_mode = FILTER_DUPLICATES_ONLY
        elif scope == SCOPE_CROSS_LIBRARY:
            self._filter_mode = FILTER_CROSS_LIBRARY
        elif scope == SCOPE_ALL:
            # Show both duplicates and cross-library — use ALL then filter manually.
            self._filter_mode = FILTER_ALL
        self.invalidateFilter()

    def set_decided_file_ids(self, ids: set[int]) -> None:
        """Update the set of file_ids that have decisions (to be hidden)."""
        self._decided_file_ids = ids
        self.invalidateFilter()

    def add_decided_file_id(self, file_id: int) -> None:
        """Mark a single file as decided (hides it immediately)."""
        self._decided_file_ids.add(file_id)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        idx = self.sourceModel().index(source_row, 0, source_parent)
        node_type = idx.data(ROLE_NODE_TYPE)

        if node_type == "file":
            # Hide decided files.
            file_id = idx.data(ROLE_FILE_ID)
            if file_id in self._decided_file_ids:
                return False

            # Apply scope filter.
            if self._scope == SCOPE_LOCAL_DUPLICATES:
                return bool(idx.data(ROLE_IS_DUPLICATE))
            elif self._scope == SCOPE_CROSS_LIBRARY:
                return bool(idx.data(ROLE_IS_CROSS_LIBRARY))
            elif self._scope == SCOPE_ALL:
                # Show files that are either duplicates or cross-library.
                return bool(idx.data(ROLE_IS_DUPLICATE)) or bool(idx.data(ROLE_IS_CROSS_LIBRARY))
            return True

        if node_type == "folder":
            # Show folder only if it has at least one visible descendant.
            model = self.sourceModel()
            for child_row in range(model.rowCount(idx)):
                if self.filterAcceptsRow(child_row, idx):
                    return True
            return False

        return False
