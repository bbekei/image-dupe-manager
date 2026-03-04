"""
ui/similarity_compare.py — Side-by-side thumbnail comparison widget.

Shows thumbnails + metadata for all files in a selected similarity group,
with recommendation badges and keep/delete action buttons.

Plan reference: §S4.2.
"""

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class _FileCard(QFrame):
    """Card showing one file in a similarity group."""

    keep_clicked = pyqtSignal(int)    # file_id
    delete_clicked = pyqtSignal(int)  # file_id

    def __init__(self, file_data: dict, parent=None):
        super().__init__(parent)
        self._file_id = file_data["file_id"]
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        is_rec = file_data.get("is_recommended", False)
        border_color = "#f59e0b" if is_rec else "#d1d5db"
        self.setStyleSheet(f"""
            QFrame {{
                border: 2px solid {border_color};
                border-radius: 6px;
                background: palette(base);
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setFixedSize(160, 120)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet("border: none;")
        thumb_path = file_data.get("thumbnail_path", "")
        if thumb_path and os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                thumb_label.setPixmap(
                    pixmap.scaled(
                        160, 120,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                thumb_label.setText(self.tr("No preview"))
        else:
            thumb_label.setText(self.tr("No preview"))
        layout.addWidget(thumb_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Recommendation badge
        if is_rec:
            badge = QLabel(self.tr("\u2605 RECOMMENDED"))
            badge.setStyleSheet(
                "color: #f59e0b; font-weight: bold; font-size: 11px; border: none;"
            )
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(badge)

        # Filename
        name_label = QLabel(os.path.basename(file_data.get("path", "")))
        name_label.setStyleSheet("font-weight: bold; border: none;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        # Metadata
        w = file_data.get("width", 0) or 0
        h = file_data.get("height", 0) or 0
        if w and h:
            res_label = QLabel(f"{w}\u00d7{h}")
            res_label.setStyleSheet("color: #6b7280; font-size: 11px; border: none;")
            layout.addWidget(res_label)

        size_label = QLabel(_format_size(file_data.get("size", 0) or 0))
        size_label.setStyleSheet("color: #6b7280; font-size: 11px; border: none;")
        layout.addWidget(size_label)

        mod = file_data.get("modified_at", "")
        if mod:
            date_label = QLabel(mod[:10])
            date_label.setStyleSheet("color: #6b7280; font-size: 11px; border: none;")
            layout.addWidget(date_label)

        dist = file_data.get("distance", 0)
        dist_label = QLabel(self.tr("distance: {0}").format(dist))
        dist_label.setStyleSheet("color: #9ca3af; font-size: 10px; border: none;")
        layout.addWidget(dist_label)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        keep_btn = QPushButton(self.tr("Keep"))
        keep_btn.setStyleSheet("border: 1px solid #22c55e; color: #22c55e;")
        keep_btn.clicked.connect(lambda: self.keep_clicked.emit(self._file_id))
        btn_row.addWidget(keep_btn)

        del_btn = QPushButton(self.tr("Delete"))
        del_btn.setStyleSheet("border: 1px solid #ef4444; color: #ef4444;")
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._file_id))
        btn_row.addWidget(del_btn)

        layout.addLayout(btn_row)


class SimilarityComparePanel(QWidget):
    """Side-by-side comparison panel for a similarity group."""

    keep_file = pyqtSignal(int)    # file_id
    delete_file = pyqtSignal(int)  # file_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Recommendation header
        self._rec_label = QLabel()
        self._rec_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
        layout.addWidget(self._rec_label)

        # Scrollable card area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._cards_container = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)
        self._cards_layout.addStretch()
        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll)

        # Empty state
        self._empty_label = QLabel(self.tr("Select a similarity group to compare"))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #9ca3af;")
        layout.addWidget(self._empty_label)

    def show_group(self, files: list[dict], recommendation: str = "") -> None:
        """Display file cards for a similarity group.

        Args:
            files: List of dicts with keys: file_id, path, size, modified_at,
                   thumbnail_path, width, height, distance, is_recommended.
            recommendation: Text like "Keep IMG_1234.jpg (highest resolution)".
        """
        # Clear existing cards.
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._empty_label.setVisible(not files)
        self._rec_label.setText(recommendation)
        self._rec_label.setVisible(bool(recommendation))

        for f in files:
            card = _FileCard(f, parent=self)
            card.keep_clicked.connect(self.keep_file)
            card.delete_clicked.connect(self.delete_file)
            # Insert before the stretch.
            self._cards_layout.insertWidget(
                self._cards_layout.count() - 1, card
            )

    def clear(self) -> None:
        """Reset to empty state."""
        self.show_group([], "")
