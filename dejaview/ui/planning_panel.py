"""
ui/planning_panel.py — Planning view for marking duplicate actions.

Shows duplicate/cross-library files with action buttons (Keep/Delete/Ignore).
Items disappear from the view as decisions are made.
Brave mode: one-click "Keep Newest Only" for all local duplicate groups.

Pluggable Views feature — Phase 2 (Planning) of the user workflow.
"""

import datetime
import logging
import os
from typing import Optional

from PyQt6.QtCore import (
    QModelIndex,
    QRect,
    QSize,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QStandardItem
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from data.db import Database
from ui.results_model import (
    ROLE_FILE_ID,
    ROLE_FILE_PATH,
    ROLE_IS_CROSS_LIBRARY,
    ROLE_IS_DUPLICATE,
    ROLE_IS_FOLDER_DUPLICATED,
    ROLE_NODE_TYPE,
    ROLE_PIXEL_HASH,
    PlanningFilterProxy,
    ResultsTreeModel,
    SCOPE_ALL,
    SCOPE_CROSS_LIBRARY,
    SCOPE_LOCAL_DUPLICATES,
    _DEFAULT_INDENT,
    _MIN_INDENT,
)

log = logging.getLogger(__name__)

# Action column index.
_COL_ACTION = 2

# Button geometry constants.
_BTN_WIDTH = 52
_BTN_HEIGHT = 20
_BTN_SPACING = 4
_BTN_MARGIN_LEFT = 4

# Action button labels.
_ACTIONS = [
    ("keep", "Keep"),
    ("delete", "Delete"),
    ("ignore", "Ignore"),
]

# Button colors.
_BTN_COLORS = {
    "keep": (QColor("#2e7d32"), QColor("#e8f5e9")),      # green
    "delete": (QColor("#c62828"), QColor("#ffebee")),     # red
    "ignore": (QColor("#546e7a"), QColor("#eceff1")),     # gray
}


class _ActionDelegate(QStyledItemDelegate):
    """Paints Keep/Delete/Ignore buttons in the Action column for file and folder rows.

    Uses paint() + editorEvent() rather than creating real QWidgets per row
    for performance with large trees.
    """

    action_clicked = pyqtSignal(QModelIndex, str)  # (source_index, action)

    def __init__(self, proxy, parent=None):
        super().__init__(parent)
        self._proxy = proxy
        self._hovered_btn: tuple[QModelIndex, int] | None = None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # Map to source to read roles.
        source = self._proxy.mapToSource(index)
        model = self._proxy.sourceModel()
        source_col0 = model.index(source.row(), 0, source.parent())
        node_type = source_col0.data(ROLE_NODE_TYPE)

        if index.column() != _COL_ACTION or node_type not in ("file", "folder"):
            super().paint(painter, option, index)
            return

        # Only show buttons for actionable rows.
        is_dup = bool(source_col0.data(ROLE_IS_DUPLICATE))
        is_cross = bool(source_col0.data(ROLE_IS_CROSS_LIBRARY))
        is_folder_dup = bool(source_col0.data(ROLE_IS_FOLDER_DUPLICATED))

        if node_type == "file" and not (is_dup or is_cross):
            super().paint(painter, option, index)
            return
        if node_type == "folder" and not is_folder_dup:
            super().paint(painter, option, index)
            return

        # Draw background.
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for i, (action, label) in enumerate(_ACTIONS):
            rect = self._button_rect(option.rect, i)
            border_color, bg_color = _BTN_COLORS[action]

            # Draw rounded button.
            painter.setPen(QPen(border_color, 1))
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect, 3, 3)

            # Draw label.
            painter.setPen(border_color)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if index.column() == _COL_ACTION:
            width = _BTN_MARGIN_LEFT + len(_ACTIONS) * (_BTN_WIDTH + _BTN_SPACING)
            return QSize(width, max(option.rect.height(), _BTN_HEIGHT + 4))
        return super().sizeHint(option, index)

    def editorEvent(self, event, model, option, index) -> bool:
        from PyQt6.QtCore import QEvent

        if index.column() != _COL_ACTION:
            return False
        if event.type() not in (QEvent.Type.MouseButtonRelease,):
            return False

        # Map to source to read roles.
        source = self._proxy.mapToSource(index)
        src_model = self._proxy.sourceModel()
        source_col0 = src_model.index(source.row(), 0, source.parent())
        node_type = source_col0.data(ROLE_NODE_TYPE)

        if node_type == "file":
            is_dup = bool(source_col0.data(ROLE_IS_DUPLICATE))
            is_cross = bool(source_col0.data(ROLE_IS_CROSS_LIBRARY))
            if not (is_dup or is_cross):
                return False
        elif node_type == "folder":
            if not bool(source_col0.data(ROLE_IS_FOLDER_DUPLICATED)):
                return False
        else:
            return False

        pos = event.position().toPoint()
        for i, (action, _label) in enumerate(_ACTIONS):
            rect = self._button_rect(option.rect, i)
            if rect.contains(pos):
                self.action_clicked.emit(source_col0, action)
                return True

        return False

    @staticmethod
    def _button_rect(cell_rect: QRect, btn_index: int) -> QRect:
        x = cell_rect.x() + _BTN_MARGIN_LEFT + btn_index * (_BTN_WIDTH + _BTN_SPACING)
        y = cell_rect.y() + (cell_rect.height() - _BTN_HEIGHT) // 2
        return QRect(x, y, _BTN_WIDTH, _BTN_HEIGHT)


class PlanningPanel(QWidget):
    """Planning view: mark duplicates with Keep/Delete/Ignore actions."""

    closed = pyqtSignal()
    compare_view_requested = pyqtSignal(str)  # pixel_hash
    review_requested = pyqtSignal()

    def __init__(self, db: Database, session_id: int, tree_model: ResultsTreeModel,
                 parent=None):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id
        self._tree_model = tree_model
        self._model = tree_model.model

        # Track total actionable items for progress display.
        self._total_actionable = 0

        self._build_ui()
        self._refresh_counts()

    # ── Public API ───────────────────────────────────────────────────

    @property
    def session_id(self) -> int:
        return self._session_id

    def refresh(self) -> None:
        """Reload decided IDs from DB and refresh the filter."""
        decided = self._db.get_decided_file_ids(self._session_id)
        self._proxy.set_decided_file_ids(decided)
        self._refresh_counts()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Top bar: back button, title, brave mode.
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(6, 4, 6, 0)

        self._back_btn = QPushButton(self.tr("\u2190 Back to Results"), self)
        self._back_btn.setObjectName("back_btn")
        top_bar.addWidget(self._back_btn)

        top_bar.addStretch()

        title = QLabel(self.tr("Planning Mode"), self)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        top_bar.addWidget(title)

        top_bar.addStretch()

        self._brave_btn = QPushButton(self.tr("Keep Newest Only"), self)
        self._brave_btn.setObjectName("brave_btn")
        self._brave_btn.setToolTip(
            self.tr("Automatically mark all older copies for deletion,\n"
                     "keeping only the newest copy of each duplicate group.")
        )
        top_bar.addWidget(self._brave_btn)

        layout.addLayout(top_bar)

        # Scope filter bar.
        scope_bar = QHBoxLayout()
        scope_bar.setContentsMargins(6, 2, 6, 0)

        self._radio_local = QRadioButton(self.tr("Local Duplicates"), self)
        self._radio_cross = QRadioButton(self.tr("Cross-Library"), self)
        self._radio_all = QRadioButton(self.tr("All"), self)
        self._radio_local.setChecked(True)

        self._scope_group = QButtonGroup(self)
        self._scope_group.addButton(self._radio_local, 0)
        self._scope_group.addButton(self._radio_cross, 1)
        self._scope_group.addButton(self._radio_all, 2)

        scope_bar.addWidget(self._radio_local)
        scope_bar.addWidget(self._radio_cross)
        scope_bar.addWidget(self._radio_all)
        scope_bar.addStretch()

        layout.addLayout(scope_bar)

        # Tree view with 3 columns.
        self._proxy = PlanningFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.set_scope(SCOPE_LOCAL_DUPLICATES)

        # Load decided IDs from DB.
        decided = self._db.get_decided_file_ids(self._session_id)
        self._proxy.set_decided_file_ids(decided)

        self._tree = QTreeView(self)
        self._tree.setModel(self._proxy)
        self._tree.setHeaderHidden(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)

        # Action delegate for column 2.
        self._action_delegate = _ActionDelegate(self._proxy, self)
        self._tree.setItemDelegateForColumn(_COL_ACTION, self._action_delegate)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        # Action column: fixed width for the 3 buttons.
        action_width = _BTN_MARGIN_LEFT + len(_ACTIONS) * (_BTN_WIDTH + _BTN_SPACING) + 8
        self._tree.setColumnWidth(_COL_ACTION, action_width)
        header.setSectionResizeMode(_COL_ACTION, QHeaderView.ResizeMode.Fixed)

        layout.addWidget(self._tree)

        # Summary bar.
        summary_bar = QHBoxLayout()
        summary_bar.setContentsMargins(6, 2, 6, 4)

        self._summary_label = QLabel(self)
        summary_bar.addWidget(self._summary_label)

        summary_bar.addStretch()

        self._review_btn = QPushButton(self.tr("Review Plan \u00bb"), self)
        self._review_btn.setObjectName("review_btn")
        self._review_btn.setEnabled(False)  # Future: enable when items are decided
        summary_bar.addWidget(self._review_btn)

        layout.addLayout(summary_bar)

        # Wire signals.
        self._back_btn.clicked.connect(self._on_back)
        self._brave_btn.clicked.connect(self._on_brave_mode)
        self._scope_group.idToggled.connect(self._on_scope_changed)
        self._action_delegate.action_clicked.connect(self._on_action_clicked)
        self._tree.doubleClicked.connect(self._on_item_double_clicked)
        self._review_btn.clicked.connect(self.review_requested.emit)

        # Expand tree to show matches.
        self._smart_expand()
        self._adjust_indentation()

    # ── Action handling ──────────────────────────────────────────────

    @pyqtSlot(QModelIndex, str)
    def _on_action_clicked(self, source_index: QModelIndex, action: str) -> None:
        """Handle a Keep/Delete/Ignore button click on a tree item."""
        item = self._model.itemFromIndex(source_index)
        if item is None:
            return

        node_type = item.data(ROLE_NODE_TYPE)
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if node_type == "file":
            file_id = item.data(ROLE_FILE_ID)
            self._db.set_file_action(
                self._session_id, file_id, action, scope="file", decided_at=ts
            )
            self._proxy.add_decided_file_id(file_id)

            # Sibling auto-actions for duplicate groups.
            self._handle_sibling_actions(file_id, action, ts)

        elif node_type == "folder":
            # Folder-level decision: apply action to all files under this folder.
            self._apply_folder_action(item, action, ts)

        self._refresh_counts()

    def _apply_folder_action(self, folder_item: QStandardItem, action: str, ts: str) -> None:
        """Recursively apply an action to all files under a folder."""
        file_ids = []
        self._collect_file_ids(folder_item, file_ids)

        if not file_ids:
            return

        batch = [
            (self._session_id, fid, action, "folder", ts)
            for fid in file_ids
        ]
        self._db.set_file_actions_batch(batch)

        # Update proxy in one shot.
        decided = self._proxy._decided_file_ids | set(file_ids)
        self._proxy.set_decided_file_ids(decided)

    def _handle_sibling_actions(self, file_id: int, action: str, ts: str) -> None:
        """Auto-mark siblings in duplicate groups after a user action.

        Issue 6: When deleting one of exactly 2 copies, auto-keep the other.
        Issue 7: When keeping one of 3+ copies, prompt to delete all others.
        """
        file_row = self._db.get_file(file_id)
        if file_row is None or file_row["pixel_hash"] is None:
            return

        siblings = self._db.get_cluster_files(self._session_id, file_row["pixel_hash"])
        if len(siblings) < 2:
            return

        decided = self._db.get_decided_file_ids(self._session_id)

        if action == "delete" and len(siblings) == 2:
            # Auto-keep the other copy if it's undecided.
            for sib in siblings:
                if sib["id"] != file_id and sib["id"] not in decided:
                    self._db.set_file_action(
                        self._session_id, sib["id"], "keep", scope="file", decided_at=ts
                    )
                    self._proxy.add_decided_file_id(sib["id"])

        elif action == "keep" and len(siblings) >= 3:
            # Prompt to delete all undecided siblings.
            undecided = [s for s in siblings if s["id"] != file_id and s["id"] not in decided]
            if not undecided:
                return

            kept_name = os.path.basename(file_row["path"])
            reply = QMessageBox.question(
                self,
                self.tr("Mark Others for Deletion?"),
                self.tr(
                    "You kept {0}.\n\nMark the other {1} copies for deletion?"
                ).format(kept_name, len(undecided)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                batch = [
                    (self._session_id, s["id"], "delete", "file", ts)
                    for s in undecided
                ]
                self._db.set_file_actions_batch(batch)
                new_decided = self._proxy._decided_file_ids | {s["id"] for s in undecided}
                self._proxy.set_decided_file_ids(new_decided)

    def _collect_file_ids(self, parent: QStandardItem, file_ids: list[int]) -> None:
        """Recursively collect all file_ids under a folder item."""
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child is None:
                continue
            if child.data(ROLE_NODE_TYPE) == "file":
                fid = child.data(ROLE_FILE_ID)
                if fid is not None:
                    file_ids.append(fid)
            elif child.data(ROLE_NODE_TYPE) == "folder":
                self._collect_file_ids(child, file_ids)

    # ── Brave mode (UC3) ─────────────────────────────────────────────

    @pyqtSlot()
    def _on_brave_mode(self) -> None:
        """Keep Newest Only: auto-mark all older copies for deletion."""
        groups = self._db.get_all_duplicate_file_ids(self._session_id)
        if not groups:
            return

        # Count affected files (all except the newest in each group).
        total_affected = 0
        for _hash, fids in groups.items():
            if len(fids) > 1:
                total_affected += len(fids) - 1

        reply = QMessageBox.question(
            self,
            self.tr("Keep Newest Only"),
            self.tr(
                "This will mark {0} older copies for deletion, keeping only "
                "the newest copy of each duplicate group.\n\n"
                "Cross-library matches are excluded.\n\n"
                "Continue?"
            ).format(total_affected),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        batch_keep = []
        batch_delete = []

        for _hash, file_ids in groups.items():
            if len(file_ids) < 2:
                continue

            # Find the newest file by modified_at.
            files = []
            for fid in file_ids:
                f = self._db.get_file(fid)
                if f:
                    files.append(f)

            if not files:
                continue

            # Sort by modified_at descending; keep the newest.
            files.sort(key=lambda f: f["modified_at"] or "", reverse=True)
            newest_id = files[0]["id"]

            batch_keep.append((self._session_id, newest_id, "keep", "file", ts))
            for f in files[1:]:
                batch_delete.append((self._session_id, f["id"], "delete", "file", ts))

        if batch_keep or batch_delete:
            self._db.set_file_actions_batch(batch_keep + batch_delete)
            # Refresh filter.
            decided = self._db.get_decided_file_ids(self._session_id)
            self._proxy.set_decided_file_ids(decided)
            self._refresh_counts()

    # ── Scope filter ─────────────────────────────────────────────────

    @pyqtSlot(int, bool)
    def _on_scope_changed(self, button_id: int, checked: bool) -> None:
        if not checked:
            return
        scope_map = {0: SCOPE_LOCAL_DUPLICATES, 1: SCOPE_CROSS_LIBRARY, 2: SCOPE_ALL}
        scope = scope_map.get(button_id, SCOPE_LOCAL_DUPLICATES)
        self._proxy.set_scope(scope)
        self._smart_expand()

    # ── Summary / counts ─────────────────────────────────────────────

    def _refresh_counts(self) -> None:
        """Update the summary label with decided/total counts."""
        decided_count = len(self._db.get_decided_file_ids(self._session_id))
        total = self._count_actionable_files()
        self._total_actionable = total

        if total == 0:
            self._summary_label.setText(self.tr("No actionable items"))
        elif decided_count >= total:
            self._summary_label.setText(
                self.tr("All {0} items decided").format(total)
            )
        else:
            self._summary_label.setText(
                self.tr("{0} / {1} decided").format(decided_count, total)
            )

        self._review_btn.setEnabled(decided_count > 0)

    def _count_actionable_files(self) -> int:
        """Count total files that are duplicates or cross-library (the planning universe)."""
        ref = [0]
        self._count_actionable_recursive(self._model.invisibleRootItem(), ref)
        return ref[0]

    def _count_actionable_recursive(self, parent: QStandardItem, ref: list[int]) -> None:
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child is None:
                continue
            if child.data(ROLE_NODE_TYPE) == "file":
                if child.data(ROLE_IS_DUPLICATE) or child.data(ROLE_IS_CROSS_LIBRARY):
                    ref[0] += 1
            elif child.data(ROLE_NODE_TYPE) == "folder":
                self._count_actionable_recursive(child, ref)

    # ── Tree helpers ─────────────────────────────────────────────────

    def _smart_expand(self) -> None:
        """Expand folders that contain visible items."""
        self._tree.expandAll()

    def _adjust_indentation(self) -> None:
        """Scale tree indentation inversely with depth."""
        depth = self._tree_model.max_depth()
        if depth <= 4:
            indent = _DEFAULT_INDENT
        else:
            indent = max(_MIN_INDENT, _DEFAULT_INDENT * 4 // depth)
        self._tree.setIndentation(indent)

    @pyqtSlot(QModelIndex)
    def _on_item_double_clicked(self, proxy_index: QModelIndex) -> None:
        """Double-click a duplicate file → emit compare_view_requested."""
        source_index = self._proxy.mapToSource(proxy_index)
        source_col0 = self._model.index(source_index.row(), 0, source_index.parent())
        item = self._model.itemFromIndex(source_col0)
        if item is None:
            return
        if item.data(ROLE_NODE_TYPE) != "file":
            return
        pixel_hash = item.data(ROLE_PIXEL_HASH)
        if pixel_hash and (item.data(ROLE_IS_DUPLICATE) or item.data(ROLE_IS_CROSS_LIBRARY)):
            self.compare_view_requested.emit(pixel_hash)

    @pyqtSlot()
    def _on_back(self) -> None:
        self.closed.emit()

    # ── Test helpers ─────────────────────────────────────────────────

    def visible_file_count(self) -> int:
        """Count visible file leaf nodes (for test assertions)."""
        return self._count_visible(self._proxy, QModelIndex())

    def _count_visible(self, model, parent: QModelIndex) -> int:
        count = 0
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            node_type = idx.data(ROLE_NODE_TYPE)
            if node_type == "file":
                count += 1
            elif node_type == "folder":
                count += self._count_visible(model, idx)
        return count

    @property
    def summary_text(self) -> str:
        """Return the current summary label text (for tests)."""
        return self._summary_label.text()
