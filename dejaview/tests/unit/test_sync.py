"""
tests/unit/test_sync.py — Unit tests for data/sync.py (DriveSync).

Plan §Test Framework — Unit Tests: data/sync.py.
All Google Drive API calls are mocked via unittest.mock.

Tests cover (plan §Test Framework):
- test_upload_called_with_correct_file_id_on_update
- test_upload_called_with_create_on_first_export
- test_download_skips_unchanged_peer_file
- test_download_imports_changed_peer_file
- test_offline_fallback_does_not_raise
- test_pending_export_flag_set_when_offline
- test_pending_export_sent_on_next_successful_sync
- test_remove_peer_clears_remote_files
+ folder ID validation, credential storage, authenticate flow
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from data.db import Database
from data.sync import (
    DriveSync,
    save_credentials,
    load_credentials,
    validate_folder_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_FOLDER_ID = "A" * 33  # 33-char alphanumeric string (valid range 25–50)
VALID_HASH = "a" * 64


def _setup_sync_config(db, username="testuser", folder_id=VALID_FOLDER_ID,
                        file_id=None, sync_enabled=1, privacy="filename",
                        pending_export=0):
    """Insert a sync_config row for testing."""
    db.upsert_sync_config(
        local_username=username,
        gdrive_folder_id=folder_id,
        gdrive_file_id=file_id,
        sync_enabled=sync_enabled,
        export_privacy=privacy,
        pending_export=pending_export,
    )


def _insert_test_file(db, session_id, path="C:/Photos/img.jpg",
                       pixel_hash=VALID_HASH, size=1000):
    """Insert a file row with a pixel_hash for export payload building."""
    now = datetime.now(timezone.utc).isoformat()
    file_id = db.insert_file(session_id, path, size, now, now)
    if pixel_hash:
        db.update_pixel_hash(file_id, pixel_hash,
                             f"thumbs/{pixel_hash}.jpg")


def _make_mock_service():
    """Build a nested MagicMock that mimics the Drive v3 files() resource."""
    service = MagicMock()
    # files().list().execute(), files().create().execute(), etc.
    return service


def _make_peer_payload(username="alice", pixel_hash=VALID_HASH):
    """Build a minimal valid peer export payload as JSON bytes."""
    payload = {
        "username": username,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "privacy_level": "filename",
        "files": [
            {
                "remote_id": f"{username}:1",
                "pixel_hash": pixel_hash,
                "filename": "photo.jpg",
                "size": 2000,
                "modified_at": "2024-01-01T00:00:00+00:00",
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


# ---------------------------------------------------------------------------
# Folder ID validation
# ---------------------------------------------------------------------------

class TestValidateFolderId:
    """Plan §Security — Drive folder ID validation."""

    def test_valid_folder_id_accepted(self):
        assert validate_folder_id("A" * 25) is True
        assert validate_folder_id("A" * 50) is True
        assert validate_folder_id("abcABC012_-" + "x" * 14) is True

    def test_too_short_rejected(self):
        assert validate_folder_id("A" * 24) is False

    def test_too_long_rejected(self):
        assert validate_folder_id("A" * 51) is False

    def test_invalid_chars_rejected(self):
        assert validate_folder_id("A" * 24 + "!") is False
        assert validate_folder_id("A" * 24 + " ") is False

    def test_empty_string_rejected(self):
        assert validate_folder_id("") is False

    def test_non_string_rejected(self):
        assert validate_folder_id(12345) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Credential storage
# ---------------------------------------------------------------------------

class TestCredentialStorage:
    """Plan §Security — OAuth2 token file creation + load."""

    def test_save_credentials_writes_json(self, tmp_path):
        token_path = tmp_path / "creds.json"
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "abc"}'
        save_credentials(mock_creds, token_path)
        assert token_path.exists()
        assert json.loads(token_path.read_text()) == {"token": "abc"}

    def test_save_credentials_creates_parent_dirs(self, tmp_path):
        token_path = tmp_path / "subdir" / "deep" / "creds.json"
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = "{}"
        save_credentials(mock_creds, token_path)
        assert token_path.exists()

    def test_load_credentials_returns_none_for_missing_file(self, tmp_path):
        result = load_credentials(tmp_path / "nonexistent.json")
        assert result is None

    @patch("data.sync.Path.exists", return_value=True)
    def test_load_credentials_returns_none_on_parse_error(self, mock_exists,
                                                           tmp_path):
        token_path = tmp_path / "bad_creds.json"
        token_path.write_text("not valid json")
        # The import inside load_credentials will fail since google libs
        # aren't installed in test env — this exercises the except branch.
        result = load_credentials(token_path)
        assert result is None


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------

class TestUpload:
    """Plan §Test Framework — sync upload tests."""

    @patch("data.sync.DriveSync._make_media_upload_bytes", return_value=MagicMock())
    def test_upload_called_with_correct_file_id_on_update(self, mock_media,
                                                           db, session_factory):
        """Plan test: when gdrive_file_id is set, files().update() is called."""
        # Req: test_upload_called_with_correct_file_id_on_update
        session_id = session_factory()
        _insert_test_file(db, session_id)
        existing_file_id = "drive_file_id_123"
        _setup_sync_config(db, file_id=existing_file_id)

        service = _make_mock_service()
        sync = DriveSync(db, "/fake/creds.json", service=service)

        result = sync.upload(session_id)

        assert result is True
        service.files().update.assert_called_once()
        call_kwargs = service.files().update.call_args
        assert call_kwargs.kwargs.get("fileId") == existing_file_id or \
               call_kwargs[1].get("fileId") == existing_file_id
        # files().create() must NOT have been called
        service.files().create.assert_not_called()

    @patch("data.sync.DriveSync._make_media_upload_bytes", return_value=MagicMock())
    def test_upload_called_with_create_on_first_export(self, mock_media,
                                                        db, session_factory):
        """Plan test: when gdrive_file_id is NULL, files().create() is called
        and the returned file id is saved to sync_config."""
        # Req: test_upload_called_with_create_on_first_export
        session_id = session_factory()
        _insert_test_file(db, session_id)
        _setup_sync_config(db, file_id=None)  # No existing Drive file

        service = _make_mock_service()
        new_id = "new_drive_file_456"
        service.files().create().execute.return_value = {"id": new_id}

        sync = DriveSync(db, "/fake/creds.json", service=service)
        result = sync.upload(session_id)

        assert result is True
        service.files().create.assert_called()
        # Verify the new file id was saved
        config = db.get_sync_config()
        assert config["gdrive_file_id"] == new_id

    @patch("data.sync.DriveSync._make_media_upload_bytes", return_value=MagicMock())
    def test_upload_sets_last_exported_at(self, mock_media, db,
                                          session_factory):
        session_id = session_factory()
        _insert_test_file(db, session_id)
        _setup_sync_config(db, file_id="existing_id")

        service = _make_mock_service()
        sync = DriveSync(db, "/fake/creds.json", service=service)
        sync.upload(session_id)

        config = db.get_sync_config()
        assert config["last_exported_at"] is not None

    @patch("data.sync.DriveSync._make_media_upload_bytes", return_value=MagicMock())
    def test_upload_clears_pending_export_on_success(self, mock_media, db,
                                                      session_factory):
        session_id = session_factory()
        _insert_test_file(db, session_id)
        _setup_sync_config(db, file_id="existing_id", pending_export=1)

        service = _make_mock_service()
        sync = DriveSync(db, "/fake/creds.json", service=service)
        sync.upload(session_id)

        config = db.get_sync_config()
        assert config["pending_export"] == 0

    def test_upload_without_service_returns_false(self, db, session_factory):
        session_id = session_factory()
        sync = DriveSync(db, "/fake/creds.json", service=None)
        assert sync.upload(session_id) is False

    def test_upload_without_sync_config_returns_false(self, db,
                                                       session_factory):
        session_id = session_factory()
        service = _make_mock_service()
        sync = DriveSync(db, "/fake/creds.json", service=service)
        assert sync.upload(session_id) is False

    def test_upload_with_invalid_folder_id_returns_false(self, db,
                                                          session_factory):
        session_id = session_factory()
        _insert_test_file(db, session_id)
        _setup_sync_config(db, folder_id="bad!")

        service = _make_mock_service()
        sync = DriveSync(db, "/fake/creds.json", service=service)
        assert sync.upload(session_id) is False


# ---------------------------------------------------------------------------
# Download tests
# ---------------------------------------------------------------------------

class TestDownload:
    """Plan §Test Framework — sync download tests."""

    def test_download_skips_unchanged_peer_file(self, db, session_factory):
        """Plan test: when remote_peer.file_mtime matches Drive modifiedTime,
        get_media() is NOT called."""
        # Req: test_download_skips_unchanged_peer_file
        session_factory()
        _setup_sync_config(db)

        # Pre-populate peer with matching mtime
        mtime = "2024-06-01T12:00:00Z"
        db.upsert_remote_peer("alice", last_seen_at=mtime, file_mtime=mtime)

        service = _make_mock_service()
        service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "alice.json", "modifiedTime": mtime}
            ]
        }

        sync = DriveSync(db, "/fake/creds.json", service=service)
        result, errors = sync.download_peers()

        # get_media should NOT be called — file is unchanged
        service.files().get_media.assert_not_called()
        assert result is False  # Nothing imported

    def test_download_imports_changed_peer_file(self, db, session_factory):
        """Plan test: when file_mtime does not match, get_media() IS called
        and import_payload() is invoked."""
        # Req: test_download_imports_changed_peer_file
        session_factory()
        _setup_sync_config(db)

        old_mtime = "2024-06-01T12:00:00Z"
        new_mtime = "2024-07-01T12:00:00Z"
        db.upsert_remote_peer("alice", last_seen_at=old_mtime,
                               file_mtime=old_mtime)

        service = _make_mock_service()
        service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "alice.json",
                 "modifiedTime": new_mtime}
            ]
        }
        peer_payload = _make_peer_payload("alice")
        service.files().get_media().execute.return_value = peer_payload

        sync = DriveSync(db, "/fake/creds.json", service=service)
        result, errors = sync.download_peers()

        assert result is True
        service.files().get_media.assert_called()
        # Verify peer's file_mtime was updated
        peer = db.get_remote_peer("alice")
        assert peer["file_mtime"] == new_mtime

    def test_download_skips_own_export(self, db, session_factory):
        """Own export (matching local_username) must be skipped."""
        session_factory()
        _setup_sync_config(db, username="testuser")

        service = _make_mock_service()
        service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "testuser.json",
                 "modifiedTime": "2024-07-01"}
            ]
        }

        sync = DriveSync(db, "/fake/creds.json", service=service)
        result, errors = sync.download_peers()

        service.files().get_media.assert_not_called()
        assert result is False

    def test_download_skips_invalid_username_files(self, db, session_factory):
        """Files with invalid usernames in their name are skipped."""
        session_factory()
        _setup_sync_config(db)

        service = _make_mock_service()
        service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "bad user!.json",
                 "modifiedTime": "2024-07-01"}
            ]
        }

        sync = DriveSync(db, "/fake/creds.json", service=service)
        result, errors = sync.download_peers()
        assert result is False

    def test_download_new_peer_imported(self, db, session_factory):
        """A peer not yet in the DB is downloaded and imported."""
        session_factory()
        _setup_sync_config(db)

        service = _make_mock_service()
        service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "bob.json",
                 "modifiedTime": "2024-07-01T00:00:00Z"}
            ]
        }
        peer_payload = _make_peer_payload("bob")
        service.files().get_media().execute.return_value = peer_payload

        sync = DriveSync(db, "/fake/creds.json", service=service)
        result, errors = sync.download_peers()

        assert result is True
        peer = db.get_remote_peer("bob")
        assert peer is not None

    def test_download_updates_last_imported_at(self, db, session_factory):
        session_factory()
        _setup_sync_config(db)

        service = _make_mock_service()
        service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "bob.json",
                 "modifiedTime": "2024-07-01T00:00:00Z"}
            ]
        }
        service.files().get_media().execute.return_value = \
            _make_peer_payload("bob")

        sync = DriveSync(db, "/fake/creds.json", service=service)
        sync.download_peers()

        config = db.get_sync_config()
        assert config["last_imported_at"] is not None


# ---------------------------------------------------------------------------
# Offline fallback / sync cycle tests
# ---------------------------------------------------------------------------

class TestSyncCycle:
    """Plan §Test Framework — offline fallback and pending export tests."""

    def test_offline_fallback_does_not_raise(self, db, session_factory):
        """Plan test: when Drive API raises, sync() catches it and sets
        status to 'unavailable'; no exception propagates."""
        # Req: test_offline_fallback_does_not_raise
        session_id = session_factory()
        _insert_test_file(db, session_id)
        _setup_sync_config(db)

        service = _make_mock_service()
        service.files().list().execute.side_effect = Exception("Network error")

        sync = DriveSync(db, "/fake/creds.json", service=service)
        # Must NOT raise
        result, peer_errors = sync.sync(session_id)

        assert result == "unavailable" or sync.status == "unavailable"

    @patch("data.sync.DriveSync._make_media_upload_bytes", return_value=MagicMock())
    def test_pending_export_flag_set_when_offline(self, mock_media, db,
                                                   session_factory):
        """Plan test: when upload fails, pending_export = 1."""
        # Req: test_pending_export_flag_set_when_offline
        session_id = session_factory()
        _insert_test_file(db, session_id)
        _setup_sync_config(db, pending_export=0)

        service = _make_mock_service()
        # List succeeds (download phase), but update fails (upload phase)
        service.files().list().execute.return_value = {"files": []}
        service.files().update().execute.side_effect = Exception("Offline")
        # Need gdrive_file_id so update path is taken
        db.upsert_sync_config(gdrive_file_id="existing_id")

        sync = DriveSync(db, "/fake/creds.json", service=service)
        sync.sync(session_id)

        config = db.get_sync_config()
        assert config["pending_export"] == 1

    @patch("data.sync.DriveSync._make_media_upload_bytes", return_value=MagicMock())
    def test_pending_export_sent_on_next_successful_sync(self, mock_media,
                                                          db, session_factory):
        """Plan test: when pending_export=1 and next sync succeeds,
        upload is called and pending_export reset to 0."""
        # Req: test_pending_export_sent_on_next_successful_sync
        session_id = session_factory()
        _insert_test_file(db, session_id)
        _setup_sync_config(db, pending_export=1)

        service = _make_mock_service()
        service.files().list().execute.return_value = {"files": []}
        service.files().create().execute.return_value = {"id": "new_id"}

        sync = DriveSync(db, "/fake/creds.json", service=service)
        # Call sync WITHOUT session_id — it should still upload because
        # pending_export=1; it uses get_latest_session() to find one.
        sync.sync(session_id=None)

        config = db.get_sync_config()
        assert config["pending_export"] == 0

    def test_sync_without_service_returns_unavailable(self, db):
        _setup_sync_config(db)
        sync = DriveSync(db, "/fake/creds.json", service=None)
        result, _ = sync.sync()
        assert result == "unavailable"

    def test_sync_without_sync_enabled_returns_idle(self, db):
        _setup_sync_config(db, sync_enabled=0)
        service = _make_mock_service()
        sync = DriveSync(db, "/fake/creds.json", service=service)
        result, _ = sync.sync()
        assert result == "idle"


# ---------------------------------------------------------------------------
# Peer management
# ---------------------------------------------------------------------------

class TestRemovePeer:
    """Plan test: test_remove_peer_clears_remote_files."""

    def test_remove_peer_clears_remote_files(self, db):
        """Plan test: given a peer with 3 remote_files rows, after
        remove_peer() the peer and all files are gone."""
        # Req: test_remove_peer_clears_remote_files
        peer_id = db.upsert_remote_peer("alice", last_seen_at="2024-01-01")
        entries = [
            {"pixel_hash": f"{'a' * 63}{i}", "filename": f"img{i}.jpg"}
            for i in range(3)
        ]
        db.insert_remote_files(peer_id, entries)

        sync = DriveSync(db, "/fake/creds.json", service=MagicMock())
        sync.remove_peer("alice")

        assert db.get_remote_peer("alice") is None
        # Verify remote_files also gone (CASCADE)
        rows = db.conn.execute(
            "SELECT COUNT(*) AS cnt FROM remote_files WHERE peer_id = ?",
            (peer_id,),
        ).fetchone()
        assert rows["cnt"] == 0
