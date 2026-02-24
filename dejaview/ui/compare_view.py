"""
ui/compare_view.py — Side-by-side duplicate comparison (read-only viewer).

Shows all files sharing the same pixel_hash as tiles laid out side by side.
Each tile displays a 240×240 thumbnail and file metadata.
No action buttons — this is a read-only duplicate viewer.

Signals:
  closed  — emitted when the user clicks Close so MainWindow can restore results.
"""

import logging
import os
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tile widget — one per file in the duplicate group
# ---------------------------------------------------------------------------

class _FileTile(QWidget):
    """
    Single tile in the compare view.

    Displays: thumbnail, path, size, date.
    ``is_local=False`` shows peer name badge (remote/peer tiles are
    informational only).
    """

    def __init__(
        self,
        file_id: int,
        file_path: str,
        size: int,
        modified_at: str,
        thumbnail_path: Optional[str],
        is_local: bool = True,
        peer_name: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._file_id = file_id
        self._file_path = file_path
        self._is_local = is_local
        self._peer_name = peer_name

        self.setFixedWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Thumbnail.
        self._thumb_label = QLabel(self)
        self._thumb_label.setFixedSize(240, 240)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("border: 1px solid #ccc; background: #f0f0f0;")
        if thumbnail_path and os.path.isfile(thumbnail_path):
            pix = QPixmap(thumbnail_path)
            self._thumb_label.setPixmap(
                pix.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._thumb_label.setText(self.tr("No thumbnail"))
        layout.addWidget(self._thumb_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Metadata labels.
        if is_local:
            self._path_label = QLabel(file_path, self)
        else:
            display = peer_name or self.tr("Remote")
            self._path_label = QLabel(f"{display}", self)
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._path_label)

        if is_local:
            fname = os.path.basename(file_path)
            self._name_label = QLabel(fname, self)
            self._name_label.setStyleSheet("font-weight: bold;")
            layout.addWidget(self._name_label)

        size_str = self._format_size(size) if size else "?"
        self._size_label = QLabel(size_str, self)
        layout.addWidget(self._size_label)

        date_str = modified_at[:10] if modified_at and len(modified_at) >= 10 else "?"
        self._date_label = QLabel(date_str, self)
        layout.addWidget(self._date_label)

        # Peer label badge for remote tiles.
        if not is_local:
            if peer_name:
                peer_label = QLabel(self.tr("({0}'s copy)").format(peer_name), self)
                peer_label.setObjectName("peer_label")
                peer_label.setStyleSheet("color: #666; font-style: italic;")
                layout.addWidget(peer_label)
            ro_label = QLabel(self.tr("(read only)"), self)
            ro_label.setObjectName("read_only_label")
            ro_label.setStyleSheet("color: #999;")
            layout.addWidget(ro_label)

        layout.addStretch()

    # ── Public helpers ────────────────────────────────────────────────────

    @property
    def file_id(self) -> int:
        return self._file_id

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def is_local(self) -> bool:
        return self._is_local

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"


# ---------------------------------------------------------------------------
# CompareView — main widget (read-only)
# ---------------------------------------------------------------------------

class CompareView(QWidget):
    """
    Side-by-side comparison of a duplicate group (read-only viewer).

    Opened by ResultsPanel.compare_view_requested(pixel_hash).
    Shows all files sharing *pixel_hash* as scrollable tiles.
    """

    closed = pyqtSignal()  # so MainWindow can restore results panel

    def __init__(
        self,
        db: Database,
        session_id: int,
        pixel_hash: str,
        session_folders: list[str],
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id
        self._pixel_hash = pixel_hash
        self._tiles: list[_FileTile] = []

        self._build_ui()
        self._populate_tiles()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # Header.
        short_hash = self._pixel_hash[:8] if self._pixel_hash else "?"
        self._header = QLabel(self)
        self._header.setObjectName("compare_header")
        self._header.setStyleSheet("font-size: 14px; font-weight: bold;")
        outer.addWidget(self._header)

        # Scrollable tile area.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._tile_container = QWidget()
        self._tile_layout = QHBoxLayout(self._tile_container)
        self._tile_layout.setContentsMargins(0, 0, 0, 0)
        self._tile_layout.setSpacing(12)
        self._tile_layout.addStretch()
        scroll.setWidget(self._tile_container)
        outer.addWidget(scroll, stretch=1)

        # Bottom bar — Close button only.
        action_row = QHBoxLayout()
        action_row.addStretch()
        self._close_btn = QPushButton(self.tr("Close"), self)
        self._close_btn.setObjectName("close_btn")
        action_row.addWidget(self._close_btn)
        outer.addLayout(action_row)

        self._close_btn.clicked.connect(self._on_close)

    def _populate_tiles(self) -> None:
        # Local files in this duplicate group.
        local_files = self._db.get_files_by_pixel_hash(self._session_id, self._pixel_hash)

        # Remote matches.
        remote_matches = self._db.get_cross_library_matches(self._session_id)
        remote_for_hash = [r for r in remote_matches if r["pixel_hash"] == self._pixel_hash]

        file_count = len(local_files) + len(remote_for_hash)
        short_hash = self._pixel_hash[:8] if self._pixel_hash else "?"
        self._header.setText(
            self.tr("DUPLICATE GROUP ({0} files \u00b7 SHA: {1}\u2026)").format(
                file_count, short_hash
            )
        )

        # Remove stretch before adding tiles (re-add at end).
        stretch_item = self._tile_layout.takeAt(self._tile_layout.count() - 1)

        for f in local_files:
            tile = _FileTile(
                file_id=f["id"],
                file_path=f["path"],
                size=f["size"] or 0,
                modified_at=f["modified_at"] or "",
                thumbnail_path=f["thumbnail_path"],
                is_local=True,
                parent=self._tile_container,
            )
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        for r in remote_for_hash:
            tile = _FileTile(
                file_id=-1,  # not a real local file_id
                file_path=r["remote_path"] or r["remote_filename"] or "?",
                size=r["remote_size"] or 0,
                modified_at=r["remote_modified_at"] or "",
                thumbnail_path=None,
                is_local=False,
                peer_name=r["username"],
                parent=self._tile_container,
            )
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        self._tile_layout.addStretch()

    # ── Tile count helper (for tests) ─────────────────────────────────────

    @property
    def tiles(self) -> list[_FileTile]:
        return list(self._tiles)

    @property
    def local_tiles(self) -> list[_FileTile]:
        return [t for t in self._tiles if t.is_local]

    @property
    def remote_tiles(self) -> list[_FileTile]:
        return [t for t in self._tiles if not t.is_local]

    # ── Slots ────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_close(self) -> None:
        self.closed.emit()
