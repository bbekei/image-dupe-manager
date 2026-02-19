"""
tests/ui/test_share_dialog.py — UI tests for ShareDialog (plan §Phase 6.3).

Tests cover:
- Widget construction and initial state
- Loading config from DB
- Username validation (plan §Security — username sanitization)
- Folder ID validation (plan §Security — Drive folder ID validation)
- Privacy level selection
- Peer list display and removal
- Save persists to sync_config
- Signal emission (sign_in_requested, sync_requested, peer_removed, settings_saved)
"""

import pytest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from ui.share_dialog import ShareDialog


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def dialog(qtbot, db):
    """ShareDialog with a fresh DB, no DriveSync."""
    dlg = ShareDialog(db=db, drive_sync=None)
    qtbot.addWidget(dlg)
    return dlg


@pytest.fixture
def dialog_with_config(qtbot, db):
    """ShareDialog with pre-existing sync_config."""
    db.upsert_sync_config(
        local_username="alice",
        gdrive_folder_id="a" * 33,
        export_privacy="hash_only",
        sync_enabled=1,
    )
    dlg = ShareDialog(db=db, drive_sync=None)
    qtbot.addWidget(dlg)
    return dlg


@pytest.fixture
def dialog_with_peers(qtbot, db):
    """ShareDialog with pre-existing peers."""
    db.upsert_sync_config(local_username="alice")
    db.upsert_remote_peer("bob", "2026-01-01T00:00:00Z")
    db.upsert_remote_peer("carol", "2026-01-02T00:00:00Z")
    dlg = ShareDialog(db=db, drive_sync=None)
    qtbot.addWidget(dlg)
    return dlg


# ── Construction and initial state ───────────────────────────────────────

class TestShareDialogConstruction:

    def test_dialog_has_correct_title(self, dialog):
        assert "Configure Sync" in dialog.windowTitle()

    def test_all_key_widgets_exist(self, dialog):
        assert dialog.findChild(type(dialog._username_edit), "username_edit") is not None
        assert dialog.findChild(type(dialog._sign_in_btn), "sign_in_btn") is not None
        assert dialog.findChild(type(dialog._folder_id_edit), "folder_id_edit") is not None
        assert dialog.findChild(type(dialog._privacy_combo), "privacy_combo") is not None
        assert dialog.findChild(type(dialog._peer_list), "peer_list") is not None
        assert dialog.findChild(type(dialog._save_btn), "save_btn") is not None
        assert dialog.findChild(type(dialog._cancel_btn), "cancel_btn") is not None
        assert dialog.findChild(type(dialog._sync_now_btn), "sync_now_btn") is not None

    def test_empty_db_shows_blank_fields(self, dialog):
        assert dialog._username_edit.text() == ""
        assert dialog._folder_id_edit.text() == ""
        assert dialog._privacy_combo.currentData() == "filename"  # default

    def test_auth_status_shows_not_signed_in(self, dialog):
        assert "Not signed in" in dialog._auth_status_label.text()


# ── Loading config from DB ───────────────────────────────────────────────

class TestShareDialogLoadConfig:

    def test_loads_username(self, dialog_with_config):
        assert dialog_with_config._username_edit.text() == "alice"

    def test_loads_folder_id(self, dialog_with_config):
        assert dialog_with_config._folder_id_edit.text() == "a" * 33

    def test_loads_privacy_level(self, dialog_with_config):
        assert dialog_with_config._privacy_combo.currentData() == "hash_only"


# ── Peer list ────────────────────────────────────────────────────────────

class TestShareDialogPeerList:

    def test_peers_loaded(self, dialog_with_peers):
        peer_list = dialog_with_peers._peer_list
        usernames = [peer_list.item(i).text() for i in range(peer_list.count())]
        assert "bob" in usernames
        assert "carol" in usernames

    def test_remove_peer_emits_signal(self, qtbot, dialog_with_peers, db):
        """Selecting a peer and clicking Remove emits peer_removed(username)."""
        peer_list = dialog_with_peers._peer_list
        peer_list.setCurrentRow(0)
        username = peer_list.currentItem().text()

        with qtbot.waitSignal(dialog_with_peers.peer_removed, timeout=1000) as sig:
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                dialog_with_peers._on_remove_peer()

        assert sig.args == [username]

    def test_remove_peer_no_selection_does_nothing(self, qtbot, dialog_with_peers):
        """Clicking Remove with no selection does nothing (no crash)."""
        dialog_with_peers._peer_list.clearSelection()
        dialog_with_peers._peer_list.setCurrentItem(None)
        # Should not raise
        dialog_with_peers._on_remove_peer()

    def test_remove_peer_declined_does_not_emit(self, qtbot, dialog_with_peers):
        """Clicking No in confirmation does not emit peer_removed."""
        dialog_with_peers._peer_list.setCurrentRow(0)

        signals = []
        dialog_with_peers.peer_removed.connect(lambda u: signals.append(u))

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            dialog_with_peers._on_remove_peer()

        assert len(signals) == 0


# ── Validation ───────────────────────────────────────────────────────────

class TestShareDialogValidation:

    def test_empty_username_rejected(self, qtbot, dialog):
        """Plan §Security — username sanitization: empty is invalid."""
        dialog._username_edit.setText("")
        with patch.object(QMessageBox, "warning"):
            assert dialog._validate() is False

    def test_username_with_spaces_rejected(self, qtbot, dialog):
        dialog._username_edit.setText("alice bob")
        with patch.object(QMessageBox, "warning"):
            assert dialog._validate() is False

    def test_username_with_dots_rejected(self, qtbot, dialog):
        dialog._username_edit.setText("alice.bob")
        with patch.object(QMessageBox, "warning"):
            assert dialog._validate() is False

    def test_valid_username_accepted(self, qtbot, dialog):
        dialog._username_edit.setText("alice_123")
        assert dialog._validate() is True

    def test_invalid_folder_id_rejected(self, qtbot, dialog):
        """Plan §Security — Drive folder ID validation: too short."""
        dialog._username_edit.setText("alice")
        dialog._folder_id_edit.setText("short")
        assert dialog._validate() is False
        assert not dialog._folder_id_error.isHidden()

    def test_valid_folder_id_accepted(self, qtbot, dialog):
        dialog._username_edit.setText("alice")
        dialog._folder_id_edit.setText("a" * 33)
        assert dialog._validate() is True
        assert dialog._folder_id_error.isHidden()

    def test_empty_folder_id_accepted(self, qtbot, dialog):
        """Empty folder ID is OK (sync just won't be enabled)."""
        dialog._username_edit.setText("alice")
        dialog._folder_id_edit.setText("")
        assert dialog._validate() is True


# ── Save ─────────────────────────────────────────────────────────────────

class TestShareDialogSave:

    def test_save_persists_to_db(self, qtbot, dialog, db):
        """Save writes all fields to sync_config."""
        dialog._username_edit.setText("alice")
        dialog._folder_id_edit.setText("b" * 33)
        dialog._privacy_combo.setCurrentIndex(
            dialog._privacy_combo.findData("full_path")
        )

        with qtbot.waitSignal(dialog.settings_saved, timeout=1000):
            dialog._on_save()

        config = db.get_sync_config()
        assert config["local_username"] == "alice"
        assert config["gdrive_folder_id"] == "b" * 33
        assert config["export_privacy"] == "full_path"
        assert config["sync_enabled"] == 1

    def test_save_without_folder_id_disables_sync(self, qtbot, dialog, db):
        dialog._username_edit.setText("alice")
        dialog._folder_id_edit.setText("")

        with qtbot.waitSignal(dialog.settings_saved, timeout=1000):
            dialog._on_save()

        config = db.get_sync_config()
        assert config["sync_enabled"] == 0

    def test_save_emits_settings_saved(self, qtbot, dialog):
        dialog._username_edit.setText("alice")
        with qtbot.waitSignal(dialog.settings_saved, timeout=1000):
            dialog._on_save()

    def test_invalid_save_does_not_emit(self, qtbot, dialog):
        dialog._username_edit.setText("")  # Invalid
        signals = []
        dialog.settings_saved.connect(lambda: signals.append(True))
        with patch.object(QMessageBox, "warning"):
            dialog._on_save()
        assert len(signals) == 0


# ── Signals ──────────────────────────────────────────────────────────────

class TestShareDialogSignals:

    def test_sign_in_emits_signal(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.sign_in_requested, timeout=1000):
            dialog._on_sign_in()

    def test_sync_now_emits_signal(self, qtbot, dialog):
        with qtbot.waitSignal(dialog.sync_requested, timeout=1000):
            dialog._on_sync_now()


# ── Auth status ──────────────────────────────────────────────────────────

class TestShareDialogAuthStatus:

    def test_authenticated_shows_signed_in(self, qtbot, db):
        mock_sync = MagicMock()
        mock_sync.is_authenticated.return_value = True
        dlg = ShareDialog(db=db, drive_sync=mock_sync)
        qtbot.addWidget(dlg)
        assert "Signed in" in dlg._auth_status_label.text()
        assert "Not" not in dlg._auth_status_label.text()

    def test_unauthenticated_shows_not_signed_in(self, qtbot, db):
        mock_sync = MagicMock()
        mock_sync.is_authenticated.return_value = False
        dlg = ShareDialog(db=db, drive_sync=mock_sync)
        qtbot.addWidget(dlg)
        assert "Not signed in" in dlg._auth_status_label.text()
