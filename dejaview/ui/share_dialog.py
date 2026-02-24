"""
ui/share_dialog.py — Configure Sync dialog for DejaView (plan §Workflow 5, Phase 6).

Layout (plan §Architecture):
  - Display name (local_username) text field
  - Sign In with Google button (triggers OAuth2 desktop flow via DriveSync)
  - Drive folder ID text field with inline validation
  - Privacy level combo box (hash_only / filename / full_path)
  - Synced peers list with Remove button
  - Sync Now button
  - Save / Cancel buttons

All UI text uses self.tr() for i18n (plan §Language / Localization).
"""

import logging
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from data.db import Database
    from data.sync import DriveSync

log = logging.getLogger(__name__)


class ShareDialog(QDialog):
    """Configure Sync dialog (plan §Workflow 5 — Setting Up Library Sync).

    Signals:
        sign_in_requested: Emitted when user clicks Sign In with Google.
        sync_requested: Emitted when user clicks Sync Now.
        peer_removed(str): Emitted when user removes a peer by username.
        settings_saved: Emitted after Save with validated settings.
    """

    sign_in_requested = pyqtSignal()
    sync_requested = pyqtSignal()
    peer_removed = pyqtSignal(str)
    settings_saved = pyqtSignal()

    def __init__(
        self,
        db: "Database",
        drive_sync: Optional["DriveSync"] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._drive_sync = drive_sync

        self.setWindowTitle(self.tr("Configure Sync"))
        self.setMinimumWidth(480)
        self.setModal(True)

        self._build_ui()
        self._load_config()
        self._load_peers()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # -- Identity group -----------------------------------------------
        identity_group = QGroupBox(self.tr("Identity"), self)
        identity_layout = QVBoxLayout(identity_group)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(self.tr("Display name:"), self))
        self._username_edit = QLineEdit(self)
        self._username_edit.setPlaceholderText(self.tr("e.g. alice"))
        self._username_edit.setMaxLength(64)
        self._username_edit.setObjectName("username_edit")
        name_row.addWidget(self._username_edit)
        identity_layout.addLayout(name_row)

        layout.addWidget(identity_group)

        # -- Google Drive group -------------------------------------------
        drive_group = QGroupBox(self.tr("Google Drive"), self)
        drive_layout = QVBoxLayout(drive_group)

        # Sign-in button
        sign_in_row = QHBoxLayout()
        self._sign_in_btn = QPushButton(self.tr("Sign in with Google"), self)
        self._sign_in_btn.setObjectName("sign_in_btn")
        self._sign_in_btn.clicked.connect(self._on_sign_in)
        sign_in_row.addWidget(self._sign_in_btn)
        self._auth_status_label = QLabel("", self)
        self._auth_status_label.setObjectName("auth_status_label")
        sign_in_row.addWidget(self._auth_status_label)
        sign_in_row.addStretch()
        drive_layout.addLayout(sign_in_row)

        # Folder ID
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(self.tr("Shared folder ID:"), self))
        self._folder_id_edit = QLineEdit(self)
        self._folder_id_edit.setPlaceholderText(
            self.tr("Paste Google Drive folder ID here")
        )
        self._folder_id_edit.setObjectName("folder_id_edit")
        folder_row.addWidget(self._folder_id_edit)
        drive_layout.addLayout(folder_row)

        self._folder_id_error = QLabel("", self)
        self._folder_id_error.setObjectName("folder_id_error")
        self._folder_id_error.setStyleSheet("color: red;")
        self._folder_id_error.hide()
        drive_layout.addWidget(self._folder_id_error)

        layout.addWidget(drive_group)

        # -- Privacy group ------------------------------------------------
        privacy_group = QGroupBox(self.tr("Privacy"), self)
        privacy_layout = QHBoxLayout(privacy_group)
        privacy_layout.addWidget(QLabel(self.tr("Export privacy level:"), self))
        self._privacy_combo = QComboBox(self)
        self._privacy_combo.setObjectName("privacy_combo")
        self._privacy_combo.addItem(self.tr("Filename only"), "filename")
        self._privacy_combo.addItem(self.tr("Hash only"), "hash_only")
        self._privacy_combo.addItem(self.tr("Full path"), "full_path")
        privacy_layout.addWidget(self._privacy_combo)
        privacy_layout.addStretch()

        layout.addWidget(privacy_group)

        # -- Peers group --------------------------------------------------
        peers_group = QGroupBox(self.tr("Synced Libraries"), self)
        peers_layout = QVBoxLayout(peers_group)

        self._peer_list = QListWidget(self)
        self._peer_list.setObjectName("peer_list")
        peers_layout.addWidget(self._peer_list)

        peer_btn_row = QHBoxLayout()
        self._remove_peer_btn = QPushButton(self.tr("Remove Peer"), self)
        self._remove_peer_btn.setObjectName("remove_peer_btn")
        self._remove_peer_btn.clicked.connect(self._on_remove_peer)
        peer_btn_row.addWidget(self._remove_peer_btn)
        peer_btn_row.addStretch()
        peers_layout.addLayout(peer_btn_row)

        layout.addWidget(peers_group)

        # -- Action buttons -----------------------------------------------
        btn_row = QHBoxLayout()

        self._sync_now_btn = QPushButton(self.tr("Sync Now"), self)
        self._sync_now_btn.setObjectName("sync_now_btn")
        self._sync_now_btn.clicked.connect(self._on_sync_now)
        btn_row.addWidget(self._sync_now_btn)

        btn_row.addStretch()

        self._save_btn = QPushButton(self.tr("Save"), self)
        self._save_btn.setObjectName("save_btn")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._cancel_btn = QPushButton(self.tr("Cancel"), self)
        self._cancel_btn.setObjectName("cancel_btn")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        layout.addLayout(btn_row)

    # ── Load/save ────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        """Populate fields from sync_config DB row."""
        config = self._db.get_sync_config()
        if config:
            self._username_edit.setText(config["local_username"] or "")
            self._folder_id_edit.setText(config["gdrive_folder_id"] or "")
            privacy = config["export_privacy"] or "filename"
            idx = self._privacy_combo.findData(privacy)
            if idx >= 0:
                self._privacy_combo.setCurrentIndex(idx)

        # Update auth status
        self._update_auth_status()

    def _load_peers(self) -> None:
        """Populate the peer list from remote_peers table."""
        self._peer_list.clear()
        peers = self._db.get_all_remote_peers()
        for peer in peers:
            self._peer_list.addItem(peer["username"])

    def _update_auth_status(self, error_message: str = "") -> None:
        """Show current authentication state."""
        if self._drive_sync and self._drive_sync.is_authenticated():
            self._auth_status_label.setText(self.tr("Signed in"))
            self._auth_status_label.setStyleSheet("color: green;")
        elif error_message:
            self._auth_status_label.setText(error_message)
            self._auth_status_label.setStyleSheet("color: red;")
        else:
            self._auth_status_label.setText(self.tr("Not signed in"))
            self._auth_status_label.setStyleSheet("color: gray;")

    # ── Validation (plan §Security — username + folder ID) ───────────────

    def _validate(self) -> bool:
        """Validate all fields. Returns True if valid."""
        from data.export import validate_username
        from data.sync import validate_folder_id

        username = self._username_edit.text().strip()
        if not validate_username(username):
            QMessageBox.warning(
                self,
                self.tr("Invalid Name"),
                self.tr(
                    "Display name must be 1\u201364 characters, "
                    "letters, digits, dash, or underscore only."
                ),
            )
            self._username_edit.setFocus()
            return False

        folder_id = self._folder_id_edit.text().strip()
        if folder_id and not validate_folder_id(folder_id):
            self._folder_id_error.setText(
                self.tr("Invalid folder ID format.")
            )
            self._folder_id_error.show()
            self._folder_id_edit.setFocus()
            return False

        self._folder_id_error.hide()
        return True

    # ── Slots ────────────────────────────────────────────────────────────

    def _on_sign_in(self) -> None:
        """Handle Sign in with Google button (plan §Workflow 5, step 3)."""
        self.sign_in_requested.emit()
        # Auth runs in a background thread; MainWindow calls set_signing_in()
        # and update_auth_status() when the flow completes.

    def _on_remove_peer(self) -> None:
        """Remove selected peer (plan §Workflow 5 — Manage peers)."""
        item = self._peer_list.currentItem()
        if item is None:
            return
        username = item.text()
        reply = QMessageBox.question(
            self,
            self.tr("Remove Peer"),
            self.tr(
                "Remove '{0}' and all their synced data?"
            ).format(username),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.peer_removed.emit(username)
            self._load_peers()

    def _on_sync_now(self) -> None:
        """Trigger an immediate sync cycle."""
        self.sync_requested.emit()

    def _on_save(self) -> None:
        """Validate and persist settings to sync_config (plan §Workflow 5, step 7)."""
        if not self._validate():
            return

        username = self._username_edit.text().strip()
        folder_id = self._folder_id_edit.text().strip() or None
        privacy = self._privacy_combo.currentData()
        sync_enabled = 1 if folder_id else 0

        self._db.upsert_sync_config(
            local_username=username,
            gdrive_folder_id=folder_id,
            export_privacy=privacy,
            sync_enabled=sync_enabled,
        )

        self.settings_saved.emit()
        self.accept()

    # ── Public API (for caller to update state after auth) ───────────────

    def set_signing_in(self, busy: bool) -> None:
        """Disable/re-enable the sign-in button during the background OAuth flow."""
        self._sign_in_btn.setEnabled(not busy)

    def update_auth_status(self, error_message: str = "") -> None:
        """Refresh the auth status label. Called by the parent after OAuth flow."""
        self._update_auth_status(error_message)
