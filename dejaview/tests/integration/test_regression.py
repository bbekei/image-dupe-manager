"""
tests/integration/test_regression.py — E2E regression tests (plan §Regression Suites).

Exercises Workflows 1–6 through the real MainWindow (or direct Scanner/CompareView).
Each test is independent (fresh DB via function-scoped fixtures).
No real %APPDATA%, no real Drive API.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from core.scanner import Scanner
from data.db import Database
from data.export import build_export_payload, import_payload
from data.sync import DriveSync
from ui.main_window import MainWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    """Create a minimal JPEG. Use achromatic (R=G=B) colors for round-trip."""
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


# ---------------------------------------------------------------------------
# Shared scan fixture for WF1 / WF2 / WF3
# ---------------------------------------------------------------------------

@pytest.fixture
def scanned_session(qtbot, db, tmp_path, thumb_dir):
    """
    Run a full scan of 3 images (2 duplicates + 1 unique) via MainWindow.

    img_a + img_b: 64×64 gray (128,128,128) → identical pixel_hash.
    img_c: 48×48 gray (64,64,64) → different size AND hash (unique).
    """
    scan_dir = tmp_path / "photos"
    scan_dir.mkdir()

    img_a = _make_jpg(scan_dir / "img_a.jpg", color=(128, 128, 128), size=(64, 64))
    img_b = _make_jpg(scan_dir / "img_b.jpg", color=(128, 128, 128), size=(64, 64))
    img_c = _make_jpg(scan_dir / "img_c.jpg", color=(64, 64, 64), size=(48, 48))

    win = MainWindow(db=db, thumb_dir=thumb_dir)
    qtbot.addWidget(win)

    win._folder_panel.add_folder(str(scan_dir), persist=False)
    # _on_start() runs synchronously during click(); creates _scanner.
    win._scan_control._start_btn.click()
    with qtbot.waitSignal(win._scanner.scan_complete, timeout=15_000):
        pass

    # Drain 200ms debounce in ResultsPanel.
    win._results_panel._flush_pending()

    return {
        "win": win,
        "scan_dir": scan_dir,
        "img_a": img_a,
        "img_b": img_b,
        "img_c": img_c,
        "session_id": win._session_id,
    }


# ---------------------------------------------------------------------------
# Workflow 1 — Scanning a Photo Library
# ---------------------------------------------------------------------------

def test_regression_wf1_scan_produces_duplicate_badges(scanned_session, db):
    """Req 4.2 — full scan produces correct duplicate groups."""
    session_id = scanned_session["session_id"]
    img_a = scanned_session["img_a"]
    img_b = scanned_session["img_b"]
    img_c = scanned_session["img_c"]

    # 1. Exactly one duplicate group with file_count=2.
    groups = db.get_duplicate_groups(session_id)
    assert len(groups) == 1
    assert groups[0]["file_count"] == 2

    # 2. img_a and img_b share that pixel_hash; img_c does not.
    dup_hash = groups[0]["pixel_hash"]
    files_in_group = db.get_files_by_pixel_hash(session_id, dup_hash)
    paths_in_group = {f["path"] for f in files_in_group}
    assert str(img_a) in paths_in_group
    assert str(img_b) in paths_in_group
    assert str(img_c) not in paths_in_group

    # 3. Session status is 'complete'.
    session = db.get_session(session_id)
    assert session["status"] == "complete"


# ---------------------------------------------------------------------------
# Workflow 2 — Reviewing Duplicates
# ---------------------------------------------------------------------------

def test_regression_wf2_filter_duplicates_only(scanned_session):
    """Req 4.3 — Duplicates Only filter shows exactly the duplicate pair."""
    win = scanned_session["win"]
    img_c = scanned_session["img_c"]
    panel = win._results_panel

    panel.set_filter("duplicates_only")

    items = panel.visible_items_data()
    visible_paths = {item["path"] for item in items}

    assert len(visible_paths) == 2
    assert str(img_c) not in visible_paths
    assert all(item["is_duplicate"] for item in items)


# ---------------------------------------------------------------------------
# Workflow 5 — Google Drive Sync (fully mocked)
# ---------------------------------------------------------------------------

def test_regression_wf5_auto_upload_after_scan_complete(
    qtbot, db, tmp_path, thumb_dir
):
    """Plan §Workflow 5 — auto-upload after scan completes."""
    # 1. Configure sync.
    db.upsert_sync_config(
        local_username="testuser",
        gdrive_folder_id="A" * 33,
        gdrive_file_id="existing_id",
        sync_enabled=1,
        export_privacy="filename",
    )

    # 2. Mock DriveSync.
    mock_sync = MagicMock(spec=DriveSync)
    mock_sync.is_authenticated.return_value = True
    mock_sync.sync.return_value = "synced"

    # 3. Build MainWindow with mock, add folder, scan.
    scan_dir = tmp_path / "photos"
    scan_dir.mkdir()
    _make_jpg(scan_dir / "img.jpg")

    win = MainWindow(db=db, thumb_dir=thumb_dir, drive_sync=mock_sync)
    qtbot.addWidget(win)
    win._folder_panel.add_folder(str(scan_dir), persist=False)

    win._scan_control._start_btn.click()
    with qtbot.waitSignal(win._scanner.scan_complete, timeout=15_000):
        pass

    # 4. Wait for sync worker to finish.
    qtbot.wait(100)
    if win._sync_worker is not None:
        qtbot.waitUntil(
            lambda: not win._sync_worker.isRunning(), timeout=5_000
        )

    # 5. sync() was called exactly once.
    mock_sync.sync.assert_called_once()


def test_regression_wf5_auto_download_on_start(qtbot, db, tmp_path, thumb_dir):
    """Plan §Workflow 5 — auto-download on app startup."""
    PEER_HASH = "b" * 64
    now = datetime.now(timezone.utc).isoformat()

    # 1. Configure sync.
    db.upsert_sync_config(
        local_username="testuser",
        gdrive_folder_id="A" * 33,
        sync_enabled=1,
        export_privacy="filename",
    )

    # 2. Build a mock Drive service that serves one peer file.
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

    # 3. Real DriveSync with mock service (passes is_authenticated).
    real_sync = DriveSync(
        db=db, credentials_path=tmp_path / "creds.json", service=mock_service,
    )
    win = MainWindow(db=db, thumb_dir=thumb_dir, drive_sync=real_sync)
    qtbot.addWidget(win)

    # 4. Simulate app startup.
    win.sync_on_start()
    qtbot.wait(100)
    if win._sync_worker is not None:
        qtbot.waitUntil(
            lambda: not win._sync_worker.isRunning(), timeout=5_000
        )

    # 5. Assert remote_files populated for peer 'alice'.
    peer = db.get_remote_peer("alice")
    assert peer is not None
    rows = db.conn.execute(
        "SELECT * FROM remote_files WHERE peer_id = ?", (peer["id"],)
    ).fetchall()
    assert len(rows) >= 1
    assert rows[0]["pixel_hash"] == PEER_HASH


