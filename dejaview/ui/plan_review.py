"""
ui/plan_review.py — Plan Review screen (the "Shopping Cart").

Two-column layout showing files marked for deletion (left) and
files requested from family (right, placeholder until Phase 4).
Impact totals at the bottom with an "Apply Changes" button.

This is the safety gate before any filesystem operations occur.
"""

import logging
import os

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

log = logging.getLogger(__name__)


def _format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


_REMOVE_BTN_SIZE = 28
_REMOVE_CIRCLE_RADIUS = 10


class _RemoveDelegate(QStyledItemDelegate):
    """Paints a red "✖" circle in column 2 for removable items.

    Uses paint()/editorEvent() instead of real QPushButton widgets —
    O(0) widget allocations regardless of row count.
    """

    remove_clicked = pyqtSignal(object)  # list[int] (folder action_ids) or int (file_id)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        # Only draw the remove button in column 2 for items with data.
        data = index.data(Qt.ItemDataRole.UserRole)
        if index.column() != 2 or data is None:
            super().paint(painter, option, index)
            return

        # Draw background.
        style = option.widget.style() if option.widget else None
        if style:
            from PyQt6.QtWidgets import QStyle
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._button_rect(option.rect)

        # Red circle background.
        painter.setPen(QPen(QColor("#c62828"), 1))
        painter.setBrush(QColor("#ffebee"))
        painter.drawEllipse(rect)

        # "✖" text.
        painter.setPen(QColor("#c62828"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "\u2716")

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        if index.column() == 2:
            return QSize(_REMOVE_BTN_SIZE, _REMOVE_BTN_SIZE)
        return super().sizeHint(option, index)

    def editorEvent(self, event, model, option, index) -> bool:
        if index.column() != 2:
            return False
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False

        data = index.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return False

        pos = event.position().toPoint()
        rect = self._button_rect(option.rect)
        if rect.contains(pos):
            self.remove_clicked.emit(data)
            return True
        return False

    @staticmethod
    def _button_rect(cell_rect: QRect) -> QRect:
        x = cell_rect.x() + (cell_rect.width() - _REMOVE_CIRCLE_RADIUS * 2) // 2
        y = cell_rect.y() + (cell_rect.height() - _REMOVE_CIRCLE_RADIUS * 2) // 2
        return QRect(x, y, _REMOVE_CIRCLE_RADIUS * 2, _REMOVE_CIRCLE_RADIUS * 2)


class PlanReviewScreen(QWidget):
    """Final review screen before committing file operations.

    Signals:
        back_requested:     user wants to go back to planning
        commit_requested:   user confirmed the plan — proceed to execution
        clear_requested:    user wants to clear the entire plan
    """

    back_requested = pyqtSignal()
    commit_requested = pyqtSignal()
    clear_requested = pyqtSignal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self._session_id: int | None = None

        self._build_ui()

    def set_session_id(self, session_id: int | None) -> None:
        self._session_id = session_id

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # Top bar: back button, title, clear button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._back_btn = QPushButton(self.tr("\u2190 Back to Planning"))
        self._back_btn.setObjectName("back_btn")
        self._back_btn.clicked.connect(self.back_requested)
        top_bar.addWidget(self._back_btn)

        top_bar.addStretch()

        title = QLabel(self.tr("Plan Review"))
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(14)
        title.setFont(title_font)
        top_bar.addWidget(title)

        top_bar.addStretch()

        self._clear_btn = QPushButton(self.tr("Clear Plan"))
        self._clear_btn.setObjectName("clear_btn")
        self._clear_btn.clicked.connect(self._on_clear)
        top_bar.addWidget(self._clear_btn)

        root.addLayout(top_bar)

        # Two-column area
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # Left column: files to delete
        left_col = QVBoxLayout()
        left_col.setSpacing(4)

        self._delete_header = QLabel(self.tr("Files to Delete (0)"))
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(11)
        self._delete_header.setFont(header_font)
        self._delete_header.setStyleSheet("color: #c62828;")
        left_col.addWidget(self._delete_header)

        self._delete_tree = QTreeWidget(self)
        self._delete_tree.setObjectName("delete_tree")
        self._delete_tree.setHeaderLabels(
            [self.tr("Path"), self.tr("Size"), ""]
        )
        self._delete_tree.setRootIsDecorated(True)
        self._delete_tree.setAlternatingRowColors(True)
        header = self._delete_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._delete_tree.setColumnWidth(2, _REMOVE_BTN_SIZE + 8)

        # Painted delegate for remove buttons (no real widgets per row).
        self._remove_delegate = _RemoveDelegate(self)
        self._delete_tree.setItemDelegateForColumn(2, self._remove_delegate)
        self._remove_delegate.remove_clicked.connect(self._on_remove_clicked)

        left_col.addWidget(self._delete_tree)

        columns.addLayout(left_col, stretch=1)

        # Vertical separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        columns.addWidget(sep)

        # Right column: files to request (placeholder)
        right_col = QVBoxLayout()
        right_col.setSpacing(4)

        self._request_header = QLabel(self.tr("Files to Request (0)"))
        req_font = QFont()
        req_font.setBold(True)
        req_font.setPointSize(11)
        self._request_header.setFont(req_font)
        self._request_header.setStyleSheet("color: #2e7d32;")
        right_col.addWidget(self._request_header)

        self._request_placeholder = QLabel(
            self.tr("Request queue will be available\nafter Family Discovery is enabled.")
        )
        self._request_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._request_placeholder.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self._request_placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        right_col.addWidget(self._request_placeholder)

        columns.addLayout(right_col, stretch=1)

        root.addLayout(columns, stretch=1)

        # Impact totals bar
        totals_frame = QFrame()
        totals_frame.setFrameShape(QFrame.Shape.StyledPanel)
        totals_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                background: palette(alternate-base);
                padding: 8px;
            }
        """)
        totals_layout = QHBoxLayout(totals_frame)
        totals_layout.setContentsMargins(12, 8, 12, 8)
        totals_layout.setSpacing(24)

        self._delete_total_label = QLabel(self.tr("Storage saved: 0 B"))
        self._delete_total_label.setStyleSheet("font-weight: bold; color: #c62828;")
        totals_layout.addWidget(self._delete_total_label)

        self._keep_total_label = QLabel(self.tr("Files kept: 0"))
        self._keep_total_label.setStyleSheet("color: #2e7d32;")
        totals_layout.addWidget(self._keep_total_label)

        totals_layout.addStretch()

        self._apply_btn = QPushButton(self.tr("Apply Changes \u00bb"))
        self._apply_btn.setObjectName("apply_btn")
        self._apply_btn.setMinimumHeight(36)
        self._apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #c62828;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #b71c1c; }
            QPushButton:disabled { background-color: #e0e0e0; color: #9e9e9e; }
        """)
        self._apply_btn.clicked.connect(self.commit_requested)
        self._apply_btn.setEnabled(False)
        totals_layout.addWidget(self._apply_btn)

        root.addWidget(totals_frame)

    # ── Data refresh ──────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the plan data from the database."""
        self._delete_tree.clear()

        if self._session_id is None:
            self._delete_header.setText(self.tr("Files to Delete (0)"))
            self._delete_total_label.setText(self.tr("Storage saved: 0 B"))
            self._keep_total_label.setText(self.tr("Files kept: 0"))
            self._apply_btn.setEnabled(False)
            return

        # Get plan summary
        summary = self._db.get_plan_summary(self._session_id)
        delete_count = summary["delete_count"]
        delete_bytes = summary["delete_bytes"]
        keep_count = summary["keep_count"]

        self._delete_header.setText(
            self.tr("Files to Delete ({0})").format(delete_count)
        )
        self._delete_total_label.setText(
            self.tr("Storage saved: {0}").format(_format_size(delete_bytes))
        )
        self._keep_total_label.setText(
            self.tr("Files kept: {0}").format(keep_count)
        )

        # Populate deletion tree
        delete_rows = self._db.get_delete_actions_with_paths(self._session_id)
        self._populate_delete_tree(delete_rows)

        self._apply_btn.setEnabled(delete_count > 0)

    def _populate_delete_tree(self, rows: list) -> None:
        """Build the deletion tree, grouping folder-scoped items.

        Uses blockSignals + expandAll for performance (no per-item setExpanded).
        Remove buttons are painted by _RemoveDelegate (no real QPushButton widgets).
        """
        self._delete_tree.blockSignals(True)
        try:
            # Group by folder for folder-scoped actions
            folder_groups: dict[str, list] = {}
            file_items: list = []

            for row in rows:
                if row["scope"] == "folder":
                    folder = os.path.dirname(row["path"])
                    folder_groups.setdefault(folder, []).append(row)
                else:
                    file_items.append(row)

            # Add folder groups as collapsible items
            for folder_path, children in sorted(folder_groups.items()):
                folder_size = sum(c["size"] or 0 for c in children)
                folder_item = QTreeWidgetItem(self._delete_tree)
                folder_item.setText(0, folder_path)
                folder_item.setText(1, _format_size(folder_size))
                folder_item.setData(0, Qt.ItemDataRole.UserRole, "folder")

                # Store action IDs in column 2 for the delegate + removal handler.
                action_ids = [c["action_id"] for c in children]
                folder_item.setData(2, Qt.ItemDataRole.UserRole, action_ids)

                for child_row in children:
                    child_item = QTreeWidgetItem(folder_item)
                    child_item.setText(0, os.path.basename(child_row["path"]))
                    child_item.setText(1, _format_size(child_row["size"] or 0))
                    child_item.setData(
                        0, Qt.ItemDataRole.UserRole, child_row["file_id"]
                    )

            # Add individual file items
            for row in file_items:
                item = QTreeWidgetItem(self._delete_tree)
                item.setText(0, row["path"])
                item.setText(1, _format_size(row["size"] or 0))
                item.setData(0, Qt.ItemDataRole.UserRole, row["file_id"])
                # Store file_id in column 2 for the delegate.
                item.setData(2, Qt.ItemDataRole.UserRole, row["file_id"])
        finally:
            self._delete_tree.blockSignals(False)

        # Single expandAll after all items are added (not per-item).
        self._delete_tree.expandAll()

    # ── Action removal ────────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_remove_clicked(self, data) -> None:
        """Dispatch delegate click: list[int] → folder removal, int → single file."""
        if isinstance(data, list):
            self._remove_actions(data)
        elif isinstance(data, int):
            self._remove_file_action(data)

    def _remove_file_action(self, file_id: int) -> None:
        """Remove a single file's delete action and refresh."""
        if self._session_id is None:
            return
        self._db.clear_file_action(self._session_id, file_id)
        self.refresh()

    def _remove_actions(self, action_ids: list[int]) -> None:
        """Remove multiple file actions (folder group) and refresh."""
        if self._session_id is None:
            return
        # Get file_ids for these actions, then clear them
        rows = self._db.get_delete_actions_with_paths(self._session_id)
        file_ids_to_clear = [
            r["file_id"] for r in rows if r["action_id"] in action_ids
        ]
        for fid in file_ids_to_clear:
            self._db.clear_file_action(self._session_id, fid)
        self.refresh()

    @pyqtSlot()
    def _on_clear(self) -> None:
        """Clear the entire plan."""
        if self._session_id is not None:
            self._db.clear_all_actions(self._session_id)
        self.refresh()
        self.clear_requested.emit()

    # ── Events ────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        """Auto-refresh when the screen becomes visible."""
        super().showEvent(event)
        self.refresh()
