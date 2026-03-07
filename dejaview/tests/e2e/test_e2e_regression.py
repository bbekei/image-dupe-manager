"""
tests/e2e/test_e2e_regression.py — Headless regression tests (ported from old UI tests).

Exercises scan and sync workflows through DejaViewAPI, the same interface the
React frontend uses.  No GUI, no pywebview, no MainWindow.

Run with:
    cd dejaview
    python -m pytest tests/e2e/test_e2e_regression.py -m headless_e2e --no-cov -v
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from backend.api import DejaViewAPI
from data.db import Database
from data.sync import DriveSync

pytestmark = [pytest.mark.headless_e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    """Create a minimal JPEG. Use achromatic (R=G=B) colors for round-trip."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


def _wait_for_scan(api: DejaViewAPI, timeout: float = 15.0) -> None:
    """Block until the scanner thread finishes."""
    scanner = api._scanner
    assert scanner is not None, "No scanner running"
    scanner.wait(int(timeout * 1000))
    assert not scanner.isRunning(), "Scanner did not finish in time"


def _wait_for_executor(api: DejaViewAPI, timeout: float = 15.0) -> None:
    """Block until the executor thread finishes."""
    executor = api._executor
    assert executor is not None, "No executor running"
    executor.wait(int(timeout * 1000))
    assert not executor.isRunning(), "Executor did not finish in time"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_env(db: Database, tmp_path: Path):
    """Full API environment: DejaViewAPI + temp dirs."""
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    trash_root = tmp_path / "trash"
    trash_root.mkdir()
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    api = DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=trash_root,
        app_dir=app_dir,
    )
    mock_window = MagicMock()
    api.set_window(mock_window)

    return api, db, tmp_path, trash_root


# ---------------------------------------------------------------------------
# Workflow 1 — Scanning a Photo Library (via API)
# ---------------------------------------------------------------------------

class TestWF1ScanThroughAPI:
    """Exercises start_scan → wait → verify DB groups via DejaViewAPI."""

    @pytest.fixture
    def scanned(self, api_env):
        api, db, tmp_path, trash_root = api_env
        scan_dir = tmp_path / "photos"
        scan_dir.mkdir()

        img_a = _make_jpg(scan_dir / "img_a.jpg", color=(128, 128, 128), size=(64, 64))
        img_b = _make_jpg(scan_dir / "img_b.jpg", color=(128, 128, 128), size=(64, 64))
        img_c = _make_jpg(scan_dir / "img_c.jpg", color=(64, 64, 64), size=(48, 48))

        session_id = api.start_scan(
            [str(scan_dir)], "Regression WF1", enable_similarity=False,
        )
        _wait_for_scan(api)

        return {
            "api": api, "db": db, "session_id": session_id,
            "scan_dir": scan_dir,
            "img_a": img_a, "img_b": img_b, "img_c": img_c,
        }

    def test_scan_produces_duplicate_groups(self, scanned):
        """Req 4.2 — full scan produces correct duplicate groups."""
        db = scanned["db"]
        sid = scanned["session_id"]
        img_a, img_b, img_c = scanned["img_a"], scanned["img_b"], scanned["img_c"]

        groups = db.get_duplicate_groups(sid)
        assert len(groups) == 1
        assert groups[0]["file_count"] == 2

        dup_hash = groups[0]["pixel_hash"]
        files_in_group = db.get_files_by_pixel_hash(sid, dup_hash)
        paths_in_group = {f["path"] for f in files_in_group}
        assert str(img_a) in paths_in_group
        assert str(img_b) in paths_in_group
        assert str(img_c) not in paths_in_group

        session = db.get_session(sid)
        assert session["status"] == "complete"

    def test_scan_summary_via_api(self, scanned):
        """Verify get_scan_summary returns correct counts after scan."""
        api = scanned["api"]
        sid = scanned["session_id"]

        summary = api.get_scan_summary(sid)
        assert summary["total_files"] == 3
        assert summary["total_groups"] == 1
        assert summary["total_duplicates"] == 2

    def test_scan_progress_reaches_complete(self, scanned):
        """After scan, progress state should indicate completion."""
        api = scanned["api"]
        progress = api.get_scan_progress()
        assert progress["phase"] == "complete"

    def test_duplicate_groups_via_api(self, scanned):
        """Verify get_duplicate_groups returns groups with files."""
        api = scanned["api"]
        sid = scanned["session_id"]

        result = api.get_duplicate_groups(sid)
        assert result["total_count"] == 1
        assert len(result["groups"]) == 1
        group = result["groups"][0]
        assert group["file_count"] == 2
        assert len(group["files"]) == 2


# ---------------------------------------------------------------------------
# Workflow 5 — Google Drive Sync (fully mocked)
# ---------------------------------------------------------------------------

class TestWF5SyncThroughAPI:
    """Exercises sync workflows through DejaViewAPI with mocked Drive."""

    def test_sync_drive_calls_sync(self, api_env):
        """sync_drive() delegates to DriveSync.sync() and returns status."""
        api, db, tmp_path, trash_root = api_env

        # Create a session so sync has something to work with
        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session("Sync Test", now)
        db.update_session_status(sid, "complete")

        # Configure sync
        db.upsert_sync_config(
            local_username="testuser",
            gdrive_folder_id="A" * 33,
            sync_enabled=1,
            export_privacy="filename",
        )

        # Inject mock DriveSync
        mock_sync = MagicMock(spec=DriveSync)
        mock_sync.is_authenticated.return_value = True
        mock_sync.sync.return_value = ("synced", {})
        api._drive_sync = mock_sync

        result = api.sync_drive()

        mock_sync.sync.assert_called_once_with(sid)
        assert result["status"] == "synced"
        assert result["errors"] == {}

    def test_sync_drive_returns_unavailable_without_drive(self, api_env):
        """sync_drive() returns 'unavailable' when no DriveSync configured."""
        api, db, tmp_path, trash_root = api_env
        api._drive_sync = None

        result = api.sync_drive()
        assert result["status"] == "unavailable"

    def test_auto_download_peers_on_sync(self, api_env):
        """Sync with mocked Drive downloads peer data into DB."""
        api, db, tmp_path, trash_root = api_env
        PEER_HASH = "b" * 64
        now = datetime.now(timezone.utc).isoformat()

        # Configure sync
        db.upsert_sync_config(
            local_username="testuser",
            gdrive_folder_id="A" * 33,
            sync_enabled=1,
            export_privacy="filename",
        )

        # Build a mock Drive service that serves one peer file
        peer_payload = json.dumps({
            "username": "alice",
            "exported_at": now,
            "privacy_level": "filename",
            "files": [{
                "pixel_hash": PEER_HASH, "filename": "photo.jpg",
                "size": 1000, "modified_at": now,
            }],
        }).encode()

        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "f1", "name": "alice.json", "modifiedTime": now}],
        }
        mock_service.files.return_value.get_media.return_value.execute.return_value = (
            peer_payload
        )

        # Real DriveSync with mock service
        real_sync = DriveSync(
            db=db, credentials_path=tmp_path / "creds.json", service=mock_service,
        )
        api._drive_sync = real_sync

        # Create a session so sync has something to upload
        sid = db.create_session("Peer Download Test", now)
        db.update_session_status(sid, "complete")

        result = api.sync_drive()

        # Assert remote_files populated for peer 'alice'
        peer = db.get_remote_peer("alice")
        assert peer is not None
        rows = db.conn.execute(
            "SELECT * FROM remote_files WHERE peer_id = ?", (peer["id"],)
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0]["pixel_hash"] == PEER_HASH

    def test_sync_config_roundtrip(self, api_env):
        """save_sync_config + get_sync_config round-trips correctly."""
        api, db, tmp_path, trash_root = api_env

        result = api.save_sync_config("testuser", "A" * 33, "filename")
        assert result["ok"] is True

        config = api.get_sync_config()
        assert config["local_username"] == "testuser"
        assert config["gdrive_folder_id"] == "A" * 33
        assert config["export_privacy"] == "filename"
        assert config["sync_enabled"] is True

    def test_save_sync_config_rejects_invalid_username(self, api_env):
        """save_sync_config validates username."""
        api, db, tmp_path, trash_root = api_env

        result = api.save_sync_config("", "A" * 33, "filename")
        assert result["ok"] is False
        assert result["error"] == "invalid_username"
