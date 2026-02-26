"""
ui/folder_panel.py — Scan folder list panel (plan Req 4.1).

Shows the user's selected scan folders.
Provides "+ Add..." and "- Remove" buttons.
Persists additions/removals to session_folders via db.py when a session_id is set.
Emits folders_changed(list[str]) whenever the list changes.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data.db import Database

log = logging.getLogger(__name__)


class FolderPanel(QWidget):
    """
    Left panel: shows scan-scope folders (plan §UI Layout).

    session_id may be None at construction time (no active session yet).
    Call set_session_id() when a session is created or restored by MainWindow.
    add_folder() / remove_folder() persist to the DB only when session_id is set
    and persist=True.
    """

    folders_changed = pyqtSignal(list)  # list[str]

    def __init__(
        self,
        db: Database,
        session_id: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._session_id = session_id
        self._build_ui()

    # ── Public API ───────────────────────────────────────────────────────

    def set_session_id(self, session_id: int) -> None:
        """Called by MainWindow when a session is created or restored."""
        self._session_id = session_id

    def add_folder(self, path: str, persist: bool = True) -> None:
        """
        Add a folder to the list.  No-op if already present.
        If persist=True and session_id is set, writes to session_folders.
        Plan §UI Tests: test_duplicate_folder_not_added_twice.
        """
        path = str(Path(path))  # normalise separators
        for i in range(self._list.count()):
            if self._list.item(i).text() == path:
                return  # already present

        self._list.addItem(QListWidgetItem(path))

        if persist and self._session_id is not None:
            self._db.add_session_folder(self._session_id, path)

        self.folders_changed.emit(self.folders())

    def remove_folder(self, path: str, persist: bool = True) -> None:
        """
        Remove a folder from the list.
        If persist=True and session_id is set, removes the row from DB and
        marks its files inactive (plan §Post-Action Cleanup — removing a folder).
        """
        path = str(Path(path))
        for i in range(self._list.count()):
            if self._list.item(i).text() == path:
                self._list.takeItem(i)
                break

        if persist and self._session_id is not None:
            self._db.remove_session_folder(self._session_id, path)
            self._db.deactivate_files_under_folder(self._session_id, path)

        self.folders_changed.emit(self.folders())

    def folders(self) -> list[str]:
        """Return the current list of folder paths in display order."""
        return [self._list.item(i).text() for i in range(self._list.count())]

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        label = QLabel(self.tr("Scan Folders"), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton(self.tr("+ Add\u2026"), self)
        self._remove_btn = QPushButton(self.tr("- Remove"), self)
        self._remove_btn.setEnabled(False)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        layout.addLayout(btn_row)

        self._add_btn.clicked.connect(self._on_add)
        self._remove_btn.clicked.connect(self._on_remove)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)

    # ── Slots ────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Select Folder to Scan")
        )
        if folder:
            self.add_folder(folder)

    def _on_remove(self) -> None:
        items = self._list.selectedItems()
        if items:
            self.remove_folder(items[0].text())

    def _on_selection_changed(self) -> None:
        self._remove_btn.setEnabled(bool(self._list.selectedItems()))

    # ── Scan progress display ─────────────────────────────────────────

    @pyqtSlot(str)
    def on_directory_hashed(self, dir_path: str) -> None:
        """Update file counts for the root folder containing *dir_path*."""
        if self._session_id is None:
            return
        norm = str(Path(dir_path))
        for i in range(self._list.count()):
            item = self._list.item(i)
            folder = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if norm.startswith(folder):
                total, hashed = self._db.get_folder_file_counts(
                    self._session_id, folder
                )
                item.setText(f"{folder} ({total} files, {hashed} hashed)")
                item.setData(Qt.ItemDataRole.UserRole, folder)
                break

    def update_all_counts(self) -> None:
        """Show initial file counts for all root folders (called after Pass 1)."""
        if self._session_id is None:
            return
        for i in range(self._list.count()):
            item = self._list.item(i)
            folder = item.data(Qt.ItemDataRole.UserRole) or item.text()
            total, hashed = self._db.get_folder_file_counts(
                self._session_id, folder
            )
            item.setText(f"{folder} ({total} files, {hashed} hashed)")
            item.setData(Qt.ItemDataRole.UserRole, folder)

    def reset_display_text(self) -> None:
        """Revert items to plain folder paths (called on scan complete/stop)."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            folder = item.data(Qt.ItemDataRole.UserRole)
            if folder:
                item.setText(folder)
                item.setData(Qt.ItemDataRole.UserRole, None)
