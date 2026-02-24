"""
tests/ui/test_compare_view.py — UI tests for ui/compare_view.py (read-only viewer).

Tests cover:
- All tiles rendered for group
- Local and remote tiles have no action buttons (read-only)
- Remote tile shows peer label and read-only badge
- Header shows file count and hash prefix
- Close button emits closed signal
- Tile properties and format_size
"""

import os
from pathlib import Path

import pytest

from data.db import Database
from ui.compare_view import CompareView, _FileTile


# ── Constants ────────────────────────────────────────────────────────────────

HASH_DUP = "d" * 64


# ── Helpers ──────────────────────────────────────────────────────────────────

def _populate_duplicate_group(db, session_id, tmp_path, count=3):
    """
    Insert *count* local files with the same pixel_hash into db.
    Creates real files on disk under tmp_path so path scope checks pass.
    Returns list of dicts: [{id, path, size, modified_at}, ...].
    """
    now_base = "2023-06-{day:02d}T12:00:00Z"
    sizes = [2_100_000, 1_800_000, 2_100_000, 1_500_000, 3_000_000]
    folder = tmp_path / "photos"
    folder.mkdir(exist_ok=True)

    files = []
    for i in range(count):
        fname = f"img{i:04d}.jpg"
        fpath = folder / fname
        fpath.write_bytes(b"\xff\xd8" + b"\x00" * 100)  # minimal JPEG-ish

        day = 15 + i  # 15, 16, 17...
        mod = now_base.format(day=day)
        size = sizes[i % len(sizes)]
        scan_ts = "2026-01-01T00:00:00Z"

        fid = db.insert_file(session_id, str(fpath), size, mod, scan_ts)
        db.update_pixel_hash(fid, HASH_DUP, f"/thumbs/{HASH_DUP}.jpg")
        files.append({"id": fid, "path": str(fpath), "size": size, "modified_at": mod})

    return files


def _add_remote_match(db, pixel_hash=HASH_DUP, peer_name="alice"):
    """Insert a remote peer with one file matching *pixel_hash*."""
    now = "2026-01-01T00:00:00Z"
    peer_id = db.upsert_remote_peer(peer_name, now)
    db.insert_remote_files(peer_id, [
        {"pixel_hash": pixel_hash, "filename": "vacation_beach.jpg",
         "size": 2_000_000, "modified_at": "2023-07-30T00:00:00Z"},
    ])
    return peer_id


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def session_id(db):
    return db.create_session("Test", "2026-01-01T00:00:00Z")


@pytest.fixture
def dup_group(db, session_id, tmp_path):
    """3 local duplicate files + session folder registered."""
    folder = str(tmp_path / "photos")
    db.add_session_folder(session_id, folder)
    files = _populate_duplicate_group(db, session_id, tmp_path, count=3)
    return files


@pytest.fixture
def compare_view(qtbot, db, session_id, dup_group, tmp_path):
    """CompareView opened for the duplicate group."""
    folders = db.get_session_folders(session_id)
    cv = CompareView(
        db=db,
        session_id=session_id,
        pixel_hash=HASH_DUP,
        session_folders=folders,
    )
    qtbot.addWidget(cv)
    return cv


# ── Tile rendering tests ────────────────────────────────────────────────────

def test_all_tiles_rendered_for_group(compare_view, dup_group):
    assert len(compare_view.tiles) == 3
    assert len(compare_view.local_tiles) == 3
    assert len(compare_view.remote_tiles) == 0


def test_local_tile_has_no_action_buttons(compare_view):
    """After simplification, local tiles have no KEEP/DEL/Rename buttons."""
    tile = compare_view.local_tiles[0]
    from PyQt6.QtWidgets import QPushButton
    buttons = tile.findChildren(QPushButton)
    button_names = {b.objectName() for b in buttons}
    assert "keep_btn" not in button_names
    assert "del_btn" not in button_names
    assert "rename_btn" not in button_names


def test_remote_tile_has_no_action_buttons(qtbot, db, session_id, dup_group):
    _add_remote_match(db)
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    assert len(cv.remote_tiles) >= 1
    remote = cv.remote_tiles[0]
    from PyQt6.QtWidgets import QPushButton
    buttons = remote.findChildren(QPushButton)
    button_names = {b.objectName() for b in buttons}
    assert "keep_btn" not in button_names
    assert "del_btn" not in button_names
    assert "rename_btn" not in button_names


def test_remote_tile_shows_peer_label(qtbot, db, session_id, dup_group):
    _add_remote_match(db, peer_name="alice")
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    assert len(cv.remote_tiles) >= 1
    remote = cv.remote_tiles[0]
    from PyQt6.QtWidgets import QLabel
    peer_label = remote.findChild(QLabel, "peer_label")
    assert peer_label is not None
    assert "alice" in peer_label.text()


def test_remote_tile_shows_read_only_label(qtbot, db, session_id, dup_group):
    _add_remote_match(db)
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    assert len(cv.remote_tiles) >= 1
    remote = cv.remote_tiles[0]
    from PyQt6.QtWidgets import QLabel
    ro_label = remote.findChild(QLabel, "read_only_label")
    assert ro_label is not None
    assert "read only" in ro_label.text().lower()


def test_header_shows_file_count_and_hash(compare_view):
    from PyQt6.QtWidgets import QLabel
    header = compare_view.findChild(QLabel, "compare_header")
    assert header is not None
    assert "3 files" in header.text()
    assert HASH_DUP[:8] in header.text()


# ── Signal tests ─────────────────────────────────────────────────────────────

def test_closed_signal_emitted_on_close(qtbot, db, session_id, dup_group):
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    with qtbot.waitSignal(cv.closed, timeout=1000):
        cv._on_close()


# ── Tile widget unit tests ──────────────────────────────────────────────────

def test_file_tile_format_size():
    assert _FileTile._format_size(500) == "500 B"
    assert _FileTile._format_size(2048) == "2.0 KB"
    assert _FileTile._format_size(2_100_000) == "2.0 MB"


def test_file_tile_properties(qtbot):
    tile = _FileTile(
        file_id=42, file_path="/photos/img.jpg", size=1000,
        modified_at="2023-06-15T12:00:00Z", thumbnail_path=None,
        is_local=True,
    )
    qtbot.addWidget(tile)
    assert tile.file_id == 42
    assert tile.file_path == "/photos/img.jpg"
    assert tile.is_local is True


def test_remote_tile_properties(qtbot):
    tile = _FileTile(
        file_id=-1, file_path="vacation.jpg", size=2000,
        modified_at="2023-07-30T00:00:00Z", thumbnail_path=None,
        is_local=False, peer_name="alice",
    )
    qtbot.addWidget(tile)
    assert tile.is_local is False
