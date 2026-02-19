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
from PyQt6.QtWidgets import QLabel, QPushButton

from core.scanner import Scanner
from data.db import Database
from data.export import build_export_payload, import_payload
from data.sync import DriveSync
from ui.compare_view import CompareView
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
# Workflow 3 — Acting on Duplicates (staging + confirm)
# ---------------------------------------------------------------------------

def test_regression_wf3_stage_and_confirm_delete(scanned_session, db):
    """Req 4.5 — stage delete, confirm, verify DB + optional disk check."""
    win = scanned_session["win"]
    session_id = scanned_session["session_id"]
    img_b = scanned_session["img_b"]

    # 1. Find img_b's file_id.
    files = db.get_files_for_session(session_id)
    img_b_row = next(f for f in files if f["path"] == str(img_b))
    file_id = img_b_row["id"]

    # 2. Stage a delete action.
    action_id = db.stage_action(file_id, "delete")
    action = db.get_action(action_id)
    assert action["status"] == "staged"
    assert os.path.isfile(str(img_b))  # file still on disk

    # 3. Open CompareView and execute the staged action.
    groups = db.get_duplicate_groups(session_id)
    pixel_hash = groups[0]["pixel_hash"]
    win._on_compare_requested(pixel_hash)
    cv = win._compare_view

    staged = db.get_staged_actions(session_id)
    action_list = [
        {
            "action_type": a["action_type"],
            "path": a["path"],
            "detail": a["detail"],
            "action_id": a["id"],
            "file_id": a["file_id"],
        }
        for a in staged
    ]
    cv._execute_actions(action_list)

    # 4. Assert confirmed.
    action = db.get_action(action_id)
    assert action["status"] == "confirmed"
    assert action["performed_at"] is not None

    # 5. Destructive assertion gated by env var.
    if os.environ.get("RUN_DESTRUCTIVE_TESTS") == "1":
        assert not os.path.isfile(str(img_b))


# ---------------------------------------------------------------------------
# Workflow 4 — Cross-Library (read-only remote tiles)
# ---------------------------------------------------------------------------

def test_regression_wf4_remote_tile_has_no_actions(qtbot, db, tmp_path, thumb_dir):
    """Req 4.4 — remote tiles are informational only, no action buttons."""
    HASH = "a" * 64
    now = datetime.now(timezone.utc).isoformat()

    # 1. Create a local file with a known pixel_hash.
    scan_dir = tmp_path / "photos"
    scan_dir.mkdir()
    local_file = _make_jpg(scan_dir / "beach.jpg")

    session_id = db.create_session("wf4", now)
    db.add_session_folder(session_id, str(scan_dir))
    file_id = db.insert_file(session_id, str(local_file), 102, now, now)
    db.update_pixel_hash(file_id, HASH, str(thumb_dir / f"{HASH}.jpg"))

    # Create a dummy thumbnail so the tile can load it.
    _make_jpg(thumb_dir / f"{HASH}.jpg", size=(40, 40))

    # 2. Create matching remote_file for peer 'alice'.
    peer_id = db.upsert_remote_peer("alice", now)
    db.insert_remote_files(peer_id, [
        {"pixel_hash": HASH, "filename": "vacation.jpg", "size": 1000,
         "modified_at": now},
    ])

    # 3. Open CompareView for this group.
    session_folders = db.get_session_folders(session_id)
    cv = CompareView(
        db=db, session_id=session_id, pixel_hash=HASH,
        session_folders=session_folders,
    )
    qtbot.addWidget(cv)

    # 4. Local tile has KEEP and DEL buttons.
    assert len(cv.local_tiles) >= 1
    local_tile = cv.local_tiles[0]
    assert local_tile.findChild(QPushButton, "keep_btn") is not None
    assert local_tile.findChild(QPushButton, "del_btn") is not None

    # 5. Remote tile has no action buttons.
    assert len(cv.remote_tiles) >= 1
    remote_tile = cv.remote_tiles[0]
    btn_names = {b.objectName() for b in remote_tile.findChildren(QPushButton)}
    assert "keep_btn" not in btn_names
    assert "del_btn" not in btn_names
    assert "rename_btn" not in btn_names

    # 6. Remote tile shows 'alice' peer label.
    peer_label = remote_tile.findChild(QLabel, "peer_label")
    assert peer_label is not None
    assert "alice" in peer_label.text()


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


# ---------------------------------------------------------------------------
# Workflow 6 — Manual Export / Import
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("privacy", ["hash_only", "filename", "full_path"])
def test_regression_wf6_manual_export_import_round_trip(
    qtbot, db, tmp_path, thumb_dir, privacy
):
    """Plan §Workflow 6 — export→import→cross-library match."""
    now = datetime.now(timezone.utc).isoformat()

    # 1. Scan folder with 2 duplicate images (Alice's library).
    scan_dir = tmp_path / "alice_photos"
    scan_dir.mkdir()
    _make_jpg(scan_dir / "img_a.jpg", color=(128, 128, 128))
    _make_jpg(scan_dir / "img_b.jpg", color=(128, 128, 128))

    session_id = db.create_session("alice_scan", now)
    db.add_session_folder(session_id, str(scan_dir))

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    with qtbot.waitSignal(scanner.scan_complete, timeout=15_000):
        scanner.start()

    # 2. Export to JSON at the given privacy level.
    payload = build_export_payload(db, session_id, "alice", privacy)
    raw_json = json.dumps(payload)

    assert payload["username"] == "alice"
    assert payload["privacy_level"] == privacy
    assert len(payload["files"]) == 2

    # 3. Create a second DB (Bob). Scan Bob's copy of the same image.
    db2 = Database(tmp_path / "db2.db")
    db2.open()
    try:
        bob_dir = tmp_path / "bob_photos"
        bob_dir.mkdir()
        _make_jpg(bob_dir / "bob_img.jpg", color=(128, 128, 128))

        bob_session = db2.create_session("bob_scan", now)
        db2.add_session_folder(bob_session, str(bob_dir))

        bob_thumb = tmp_path / "bob_thumbs"
        bob_thumb.mkdir()
        scanner2 = Scanner(db=db2, session_id=bob_session, thumb_dir=bob_thumb)
        with qtbot.waitSignal(scanner2.scan_complete, timeout=15_000):
            scanner2.start()

        # 4. Import Alice's JSON into Bob's DB.
        import_payload(db2, raw_json.encode())

        # 5. Cross-library JOIN returns expected matches.
        matches = db2.get_cross_library_matches(bob_session)
        assert len(matches) >= 1
        assert all(m["username"] == "alice" for m in matches)

        # Bob's local hash must appear in the match set.
        bob_files = db2.get_files_for_session(bob_session)
        bob_hashes = {f["pixel_hash"] for f in bob_files if f["pixel_hash"]}
        matched_hashes = {m["pixel_hash"] for m in matches}
        assert len(matched_hashes & bob_hashes) >= 1
    finally:
        db2.close()
