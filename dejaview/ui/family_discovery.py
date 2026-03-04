"""
ui/family_discovery.py — Family Discovery screen (Phase 4).

Grid view of "Family Treasures" — photos that family members have but the
current user does not.  Users can select photos and request them from peers.

Uses QListView in IconMode with a custom QAbstractListModel for virtual
scrolling.  Placeholder thumbnails are shown since remote files have no
local thumbnails.
"""

import logging
from datetime import datetime, timezone

from PyQt6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSize,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

log = logging.getLogger(__name__)

# Thumbnail placeholder size
_THUMB_SIZE = 96
_ITEM_SIZE = QSize(_THUMB_SIZE + 16, _THUMB_SIZE + 48)

# Custom roles
ROLE_PIXEL_HASH = Qt.ItemDataRole.UserRole + 1
ROLE_PEER_USERNAME = Qt.ItemDataRole.UserRole + 2
ROLE_REMOTE_FILE_ID = Qt.ItemDataRole.UserRole + 3
ROLE_IS_REQUESTED = Qt.ItemDataRole.UserRole + 4
ROLE_FILENAME = Qt.ItemDataRole.UserRole + 5
ROLE_FILE_SIZE = Qt.ItemDataRole.UserRole + 6


def _format_size(size_bytes: int | None) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes is None:
        return ""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class FamilyTreasureModel(QAbstractListModel):
    """Model backing the family treasures grid.

    Each item represents a remote file not present in the local library.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def load(self, rows: list) -> None:
        """Replace all items from DB rows."""
        self.beginResetModel()
        self._items = [
            {
                "remote_file_id": r["remote_file_id"],
                "pixel_hash": r["pixel_hash"],
                "filename": r["filename"] or "",
                "remote_path": r["remote_path"] or "",
                "size": r["size"],
                "modified_at": r["modified_at"],
                "peer_username": r["peer_username"],
                "requested": False,
            }
            for r in rows
        ]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            name = item["filename"] or item["pixel_hash"][:12] + "…"
            return name
        elif role == Qt.ItemDataRole.ToolTipRole:
            parts = [f"From: {item['peer_username']}"]
            if item["filename"]:
                parts.append(f"File: {item['filename']}")
            if item["size"]:
                parts.append(f"Size: {_format_size(item['size'])}")
            return "\n".join(parts)
        elif role == ROLE_PIXEL_HASH:
            return item["pixel_hash"]
        elif role == ROLE_PEER_USERNAME:
            return item["peer_username"]
        elif role == ROLE_REMOTE_FILE_ID:
            return item["remote_file_id"]
        elif role == ROLE_IS_REQUESTED:
            return item["requested"]
        elif role == ROLE_FILENAME:
            return item["filename"]
        elif role == ROLE_FILE_SIZE:
            return item["size"]
        elif role == Qt.ItemDataRole.DecorationRole:
            return self._placeholder_icon()
        return None

    def set_requested(self, row: int, requested: bool) -> None:
        """Mark an item as requested/unrequested."""
        if 0 <= row < len(self._items):
            self._items[row]["requested"] = requested
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [ROLE_IS_REQUESTED])

    def mark_requested_hashes(self, requested_set: set[tuple[str, str]]) -> None:
        """Mark items whose (pixel_hash, peer) is in the set."""
        for i, item in enumerate(self._items):
            key = (item["pixel_hash"], item["peer_username"])
            item["requested"] = key in requested_set
        if self._items:
            self.dataChanged.emit(
                self.index(0),
                self.index(len(self._items) - 1),
                [ROLE_IS_REQUESTED],
            )

    def get_item(self, row: int) -> dict | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        default = super().flags(index)
        return default | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    @staticmethod
    def _placeholder_icon() -> QIcon:
        """Generate a simple placeholder thumbnail icon."""
        pm = QPixmap(_THUMB_SIZE, _THUMB_SIZE)
        pm.fill(QColor("#e5e7eb"))
        painter = QPainter(pm)
        painter.setPen(QColor("#9ca3af"))
        font = QFont()
        font.setPointSize(24)
        painter.setFont(font)
        painter.drawText(
            pm.rect(), Qt.AlignmentFlag.AlignCenter, "\U0001f4f7"
        )
        painter.end()
        return QIcon(pm)


# ---------------------------------------------------------------------------
# Delegate
# ---------------------------------------------------------------------------

class _TreasureDelegate(QStyledItemDelegate):
    """Paints each treasure item with a heart overlay for requested state."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        super().paint(painter, option, index)

        requested = index.data(ROLE_IS_REQUESTED)
        if requested:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # Draw a green heart indicator in the bottom-right corner
            heart_rect = option.rect.adjusted(
                option.rect.width() - 24, option.rect.height() - 24, -4, -4
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#22c55e"))
            font = QFont()
            font.setPointSize(14)
            painter.setFont(font)
            painter.setPen(QColor("#22c55e"))
            painter.drawText(
                heart_rect, Qt.AlignmentFlag.AlignCenter, "\u2764"
            )
            painter.restore()

        # Draw peer label at the bottom
        peer = index.data(ROLE_PEER_USERNAME)
        if peer:
            painter.save()
            painter.setPen(QColor("#6b7280"))
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            label_rect = option.rect.adjusted(4, option.rect.height() - 20, -4, 0)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                f"From: {peer}",
            )
            painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return _ITEM_SIZE


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

class FamilyDiscoveryScreen(QWidget):
    """Family Discovery screen — browse and request family treasures.

    Signals:
        back_requested:     user wants to go back to the dashboard
        requests_changed:   requests were added/removed (refresh plan review)
    """

    back_requested = pyqtSignal()
    requests_changed = pyqtSignal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self._session_id: int | None = None
        self._model = FamilyTreasureModel(self)

        self._build_ui()

    def set_session_id(self, session_id: int | None) -> None:
        self._session_id = session_id

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._back_btn = QPushButton(self.tr("\u2190 Dashboard"))
        self._back_btn.setObjectName("back_btn")
        self._back_btn.clicked.connect(self.back_requested)
        top_bar.addWidget(self._back_btn)

        top_bar.addStretch()

        title = QLabel(self.tr("Family Photos"))
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(14)
        title.setFont(title_font)
        top_bar.addWidget(title)

        top_bar.addStretch()

        self._request_btn = QPushButton(self.tr("Request Selected (0)"))
        self._request_btn.setObjectName("request_btn")
        self._request_btn.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #e0e0e0; color: #9e9e9e; }
        """)
        self._request_btn.setEnabled(False)
        self._request_btn.clicked.connect(self._on_request_selected)
        top_bar.addWidget(self._request_btn)

        root.addLayout(top_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel(self.tr("Filter:")))

        self._peer_filter = QComboBox()
        self._peer_filter.setMinimumWidth(140)
        self._peer_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._peer_filter)

        self._status_filter = QComboBox()
        self._status_filter.addItem(self.tr("All"), "all")
        self._status_filter.addItem(self.tr("Not Requested"), "not_requested")
        self._status_filter.addItem(self.tr("Requested"), "requested")
        self._status_filter.setMinimumWidth(140)
        self._status_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._status_filter)

        filter_row.addStretch()

        root.addLayout(filter_row)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep2)

        # Grid view
        self._grid = QListView()
        self._grid.setObjectName("treasure_grid")
        self._grid.setViewMode(QListView.ViewMode.IconMode)
        self._grid.setFlow(QListView.Flow.LeftToRight)
        self._grid.setWrapping(True)
        self._grid.setResizeMode(QListView.ResizeMode.Adjust)
        self._grid.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._grid.setUniformItemSizes(True)
        self._grid.setGridSize(_ITEM_SIZE + QSize(8, 8))
        self._grid.setSpacing(4)
        self._grid.setModel(self._model)
        self._grid.setItemDelegate(_TreasureDelegate(self))
        self._grid.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        self._grid.doubleClicked.connect(self._on_item_double_clicked)

        root.addWidget(self._grid, stretch=1)

        # Status bar
        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        root.addWidget(self._status_label)

    # ── Data refresh ──────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the family treasures from the database."""
        if self._session_id is None:
            self._model.load([])
            self._update_status()
            return

        rows = self._db.get_family_treasures(self._session_id)

        # Build set of already-requested (hash, peer) combos
        requests = self._db.get_requests_for_session(self._session_id)
        requested_set = {
            (r["pixel_hash"], r["target_peer"])
            for r in requests
            if r["status"] in ("pending", "approved")
        }

        self._model.load(rows)
        self._model.mark_requested_hashes(requested_set)

        # Populate peer filter
        self._peer_filter.blockSignals(True)
        current = self._peer_filter.currentData()
        self._peer_filter.clear()
        self._peer_filter.addItem(self.tr("All Providers"), "all")
        peers = sorted({r["peer_username"] for r in rows})
        for peer in peers:
            self._peer_filter.addItem(peer, peer)
        # Restore selection
        idx = self._peer_filter.findData(current)
        if idx >= 0:
            self._peer_filter.setCurrentIndex(idx)
        self._peer_filter.blockSignals(False)

        self._update_status()

    def _update_status(self) -> None:
        """Update the status label with counts."""
        total = self._model.rowCount()
        peers = set()
        for i in range(total):
            idx = self._model.index(i)
            peer = self._model.data(idx, ROLE_PEER_USERNAME)
            if peer:
                peers.add(peer)
        self._status_label.setText(
            self.tr("Showing {0} family photos from {1} providers").format(
                total, len(peers)
            )
        )

    # ── Filter logic ──────────────────────────────────────────────────

    @pyqtSlot(int)
    def _on_filter_changed(self, _index: int) -> None:
        """Re-filter the grid based on combo selections."""
        if self._session_id is None:
            return
        # Reload full data and apply filters
        rows = self._db.get_family_treasures(self._session_id)

        peer_filter = self._peer_filter.currentData()
        if peer_filter and peer_filter != "all":
            rows = [r for r in rows if r["peer_username"] == peer_filter]

        requests = self._db.get_requests_for_session(self._session_id)
        requested_set = {
            (r["pixel_hash"], r["target_peer"])
            for r in requests
            if r["status"] in ("pending", "approved")
        }

        status_filter = self._status_filter.currentData()
        if status_filter == "not_requested":
            rows = [
                r for r in rows
                if (r["pixel_hash"], r["peer_username"]) not in requested_set
            ]
        elif status_filter == "requested":
            rows = [
                r for r in rows
                if (r["pixel_hash"], r["peer_username"]) in requested_set
            ]

        self._model.load(rows)
        self._model.mark_requested_hashes(requested_set)
        self._update_status()

    # ── Selection handling ────────────────────────────────────────────

    @pyqtSlot()
    def _on_selection_changed(self) -> None:
        """Update the request button label when selection changes."""
        count = len(self._grid.selectionModel().selectedIndexes())
        self._request_btn.setText(
            self.tr("Request Selected ({0})").format(count)
        )
        self._request_btn.setEnabled(count > 0)

    @pyqtSlot()
    def _on_request_selected(self) -> None:
        """Request all selected photos."""
        if self._session_id is None:
            return

        now = datetime.now(timezone.utc).isoformat()
        batch = []
        for idx in self._grid.selectionModel().selectedIndexes():
            pixel_hash = self._model.data(idx, ROLE_PIXEL_HASH)
            peer = self._model.data(idx, ROLE_PEER_USERNAME)
            if pixel_hash and peer:
                batch.append((self._session_id, pixel_hash, peer, now))

        if batch:
            self._db.create_requests_batch(batch)
            # Update model to reflect requested state
            requests = self._db.get_requests_for_session(self._session_id)
            requested_set = {
                (r["pixel_hash"], r["target_peer"])
                for r in requests
                if r["status"] in ("pending", "approved")
            }
            self._model.mark_requested_hashes(requested_set)
            self._grid.selectionModel().clearSelection()
            self.requests_changed.emit()

    @pyqtSlot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        """Toggle request status on double-click (heart toggle)."""
        if self._session_id is None:
            return

        pixel_hash = self._model.data(index, ROLE_PIXEL_HASH)
        peer = self._model.data(index, ROLE_PEER_USERNAME)
        is_requested = self._model.data(index, ROLE_IS_REQUESTED)

        if not pixel_hash or not peer:
            return

        if is_requested:
            self._db.delete_request(self._session_id, pixel_hash, peer)
            self._model.set_requested(index.row(), False)
        else:
            now = datetime.now(timezone.utc).isoformat()
            self._db.create_request(
                self._session_id, pixel_hash, peer, now
            )
            self._model.set_requested(index.row(), True)

        self.requests_changed.emit()

    # ── Events ────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        """Auto-refresh when the screen becomes visible."""
        super().showEvent(event)
        self.refresh()
