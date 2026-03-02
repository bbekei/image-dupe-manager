"""
ui/dashboard.py — Family Activity Dashboard (Home View).

The entry point after launching DejaView.  Shows status summary cards
for Local Duplicates, Family Photos, and Pending Requests, plus a
sync status row and a quick-action to start a new scan.

Cards are clickable — each emits a navigation signal handled by
MainWindow / NavigationController.
"""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status card widget
# ---------------------------------------------------------------------------

class _StatusCard(QFrame):
    """Clickable summary card with a title, value, and subtitle."""

    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        value: str = "—",
        subtitle: str = "",
        color: str = "#3b82f6",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("status_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.setStyleSheet(f"""
            QFrame#status_card {{
                border: 1px solid #d1d5db;
                border-top: 3px solid {color};
                border-radius: 6px;
                background: palette(base);
                padding: 16px;
            }}
            QFrame#status_card:hover {{
                border-color: {color};
                background: palette(alternate-base);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._title_label)

        self._value_label = QLabel(value)
        value_font = QFont()
        value_font.setPointSize(22)
        value_font.setBold(True)
        self._value_label.setFont(value_font)
        layout.addWidget(self._value_label)

        self._subtitle_label = QLabel(subtitle)
        self._subtitle_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        self._subtitle_label.setWordWrap(True)
        layout.addWidget(self._subtitle_label)

        layout.addStretch()

    # ── Public API ────────────────────────────────────────────────────

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)

    def set_subtitle(self, text: str) -> None:
        self._subtitle_label.setText(text)

    def set_title(self, text: str) -> None:
        self._title_label.setText(text)

    # ── Events ────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class Dashboard(QWidget):
    """Home screen with status cards, sync status, and quick actions.

    Signals:
        duplicate_card_clicked:  user wants to navigate to the cleanup screen
        family_card_clicked:     user wants to browse family treasures
        request_card_clicked:    user wants to see pending requests
        scan_requested:          user wants to start a new scan
        sync_requested:          user clicked "Sync Now"
    """

    duplicate_card_clicked = pyqtSignal()
    family_card_clicked = pyqtSignal()
    request_card_clicked = pyqtSignal()
    scan_requested = pyqtSignal()
    sync_requested = pyqtSignal()

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
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(20)

        # Header
        header = QLabel(self.tr("DejaView"))
        header_font = QFont()
        header_font.setPointSize(20)
        header_font.setBold(True)
        header.setFont(header_font)
        root.addWidget(header)

        subtitle = QLabel(
            self.tr("Family photo deduplication and synchronization")
        )
        subtitle.setStyleSheet("color: #6b7280; font-size: 13px;")
        root.addWidget(subtitle)

        # Cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        self._dup_card = _StatusCard(
            title=self.tr("Local Duplicates"),
            color="#ef4444",
            parent=self,
        )
        self._dup_card.clicked.connect(self.duplicate_card_clicked)
        cards_row.addWidget(self._dup_card)

        self._family_card = _StatusCard(
            title=self.tr("Family Photos"),
            color="#22c55e",
            parent=self,
        )
        self._family_card.clicked.connect(self.family_card_clicked)
        cards_row.addWidget(self._family_card)

        self._request_card = _StatusCard(
            title=self.tr("Pending Requests"),
            color="#a855f7",
            parent=self,
        )
        self._request_card.clicked.connect(self.request_card_clicked)
        cards_row.addWidget(self._request_card)

        root.addLayout(cards_row)

        # Sync status row
        sync_row = QHBoxLayout()
        sync_row.setSpacing(12)
        self._sync_label = QLabel(self.tr("Last synced: never"))
        self._sync_label.setStyleSheet("color: #6b7280;")
        sync_row.addWidget(self._sync_label)
        sync_row.addStretch()

        self._sync_btn = QPushButton(self.tr("Sync Now"))
        self._sync_btn.clicked.connect(self.sync_requested)
        sync_row.addWidget(self._sync_btn)

        root.addLayout(sync_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        # Quick actions
        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)

        self._scan_btn = QPushButton(self.tr("Start New Scan"))
        self._scan_btn.setMinimumHeight(36)
        self._scan_btn.clicked.connect(self.scan_requested)
        actions_row.addWidget(self._scan_btn)
        actions_row.addStretch()

        root.addLayout(actions_row)

        # Spacer to push content to top
        root.addStretch(1)

    # ── Data refresh ──────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload card values from the database."""
        if self._session_id is None:
            self._dup_card.set_value("—")
            self._dup_card.set_subtitle(self.tr("No scan yet"))
            self._family_card.set_value("—")
            self._family_card.set_subtitle(self.tr("No scan yet"))
            self._request_card.set_value("—")
            self._request_card.set_subtitle("")
            return

        # Duplicates
        dup_groups = self._db.get_duplicate_groups(self._session_id)
        group_count = len(dup_groups)
        dup_file_count = sum(g["file_count"] for g in dup_groups)
        if group_count > 0:
            self._dup_card.set_value(str(dup_file_count))
            self._dup_card.set_subtitle(
                self.tr("{0} duplicate groups").format(group_count)
            )
        else:
            self._dup_card.set_value("0")
            self._dup_card.set_subtitle(self.tr("No duplicates found"))

        # Family treasures
        treasure_count = self._db.get_family_treasure_count(self._session_id)
        self._family_card.set_value(str(treasure_count))
        if treasure_count > 0:
            self._family_card.set_subtitle(
                self.tr("Photos your family has that you don't")
            )
        else:
            self._family_card.set_subtitle(
                self.tr("Import or sync to discover family photos")
            )

        # Requests (placeholder — requests table doesn't exist yet)
        self._request_card.set_value("0")
        self._request_card.set_subtitle(
            self.tr("No pending requests")
        )

        # Sync status
        config = self._db.get_sync_config()
        if config and config["last_imported_at"]:
            self._sync_label.setText(
                self.tr("Last synced: {0}").format(
                    config["last_imported_at"][:16].replace("T", " ")
                )
            )
        else:
            self._sync_label.setText(self.tr("Last synced: never"))

    def showEvent(self, event):
        """Auto-refresh card data whenever the dashboard becomes visible."""
        super().showEvent(event)
        self.refresh()
