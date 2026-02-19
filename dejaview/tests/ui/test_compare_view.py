"""
tests/ui/test_compare_view.py — UI tests for ui/compare_view.py.
Plan §UI Tests: compare_view — Req 4.4 + 4.5.

Tests cover:
- All tiles rendered for group
- Local tile has KEEP and DEL buttons
- Remote tile has no action buttons
- Clicking KEEP stages keep action
- Clicking DEL stages delete action
- Clicking KEEP on one marks others as DEL candidates
- Batch rule: keep oldest stages correct actions
- Batch rule: keep largest stages correct actions
- Rename action staged with new name
- Confirmation dialog lists all staged deletes
- Confirm sets action status to confirmed
- Rename validation (path traversal guard)
- Path scope check
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from data.db import Database
from ui.compare_view import CompareView, _FileTile, _ConfirmDialog, _validate_rename


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
    # Req 4.4 — plan §UI Tests: test_all_tiles_rendered_for_group
    assert len(compare_view.tiles) == 3
    assert len(compare_view.local_tiles) == 3
    assert len(compare_view.remote_tiles) == 0


def test_local_tile_has_keep_and_del_buttons(compare_view):
    # Req 4.4 — plan §UI Tests: test_local_tile_has_keep_and_del_buttons
    tile = compare_view.local_tiles[0]
    keep_btn = tile.findChild(type(tile), "")  # type: ignore
    # Check by objectName
    assert tile.findChild(tile._keep_btn.__class__, "keep_btn") is not None
    assert tile.findChild(tile._del_btn.__class__, "del_btn") is not None
    assert tile.findChild(tile._rename_btn.__class__, "rename_btn") is not None


def test_remote_tile_has_no_action_buttons(qtbot, db, session_id, dup_group):
    # Req 4.4 — plan §UI Tests: test_remote_tile_has_no_action_buttons
    # Buttons are not rendered, not merely disabled (plan §Workflow 4).
    _add_remote_match(db)
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    # NOTE: get_cross_library_matches JOIN returns one row per (local, remote) pair,
    # so with 3 local files we get 3 remote tiles for the same remote file.
    assert len(cv.remote_tiles) >= 1
    remote = cv.remote_tiles[0]
    # Remote tile must NOT have keep/del/rename buttons at all.
    from PyQt6.QtWidgets import QPushButton
    buttons = remote.findChildren(QPushButton)
    button_names = {b.objectName() for b in buttons}
    assert "keep_btn" not in button_names
    assert "del_btn" not in button_names
    assert "rename_btn" not in button_names


def test_remote_tile_shows_peer_label(qtbot, db, session_id, dup_group):
    # Plan §Workflow 4 — remote tiles show peer name badge.
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
    # Plan §UI Layout — "DUPLICATE GROUP (N files · SHA: ...)"
    from PyQt6.QtWidgets import QLabel
    header = compare_view.findChild(QLabel, "compare_header")
    assert header is not None
    assert "3 files" in header.text()
    assert HASH_DUP[:8] in header.text()


# ── KEEP/DEL staging tests ──────────────────────────────────────────────────

def test_clicking_keep_stages_keep_action(compare_view, dup_group, db, session_id):
    # Req 4.5 — plan §UI Tests: test_clicking_keep_stages_keep_action
    fid = dup_group[0]["id"]
    compare_view._on_keep(fid)

    staged = db.get_staged_actions(session_id)
    keep_actions = [a for a in staged if a["action_type"] == "keep" and a["file_id"] == fid]
    assert len(keep_actions) == 1
    assert keep_actions[0]["status"] == "staged"


def test_clicking_del_stages_delete_action(compare_view, dup_group, db, session_id):
    # Req 4.5 — plan §UI Tests: test_clicking_del_stages_delete_action
    fid = dup_group[1]["id"]
    compare_view._on_delete(fid)

    staged = db.get_staged_actions(session_id)
    del_actions = [a for a in staged if a["action_type"] == "delete" and a["file_id"] == fid]
    assert len(del_actions) == 1
    assert del_actions[0]["status"] == "staged"


def test_clicking_keep_on_one_marks_others_as_del_candidates(compare_view, dup_group, db, session_id):
    # Req 4.5 — plan §UI Tests: test_clicking_keep_on_one_marks_others_as_del_candidates
    kept_id = dup_group[0]["id"]
    other_ids = {dup_group[1]["id"], dup_group[2]["id"]}

    compare_view._on_keep(kept_id)

    staged = db.get_staged_actions(session_id)
    keeps = {a["file_id"] for a in staged if a["action_type"] == "keep"}
    deletes = {a["file_id"] for a in staged if a["action_type"] == "delete"}

    assert keeps == {kept_id}
    assert deletes == other_ids


# ── Batch rule tests ────────────────────────────────────────────────────────

def test_batch_rule_keep_oldest_stages_correct_actions(qtbot, db, session_id, dup_group):
    # Req 4.5 — plan §UI Tests: test_batch_rule_keep_oldest_stages_correct_actions
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    # Patch the dialog to auto-accept with keep_oldest.
    with patch("ui.compare_view._BatchRulesDialog") as MockDlg:
        from PyQt6.QtWidgets import QDialog
        instance = MockDlg.return_value
        instance.exec.return_value = QDialog.DialogCode.Accepted
        instance.selected_rule = "keep_oldest"
        cv._on_batch_rules()

    staged = db.get_staged_actions(session_id)
    # The oldest file (smallest modified_at) should be KEEP.
    oldest = min(dup_group, key=lambda f: f["modified_at"])
    keep_ids = {a["file_id"] for a in staged if a["action_type"] == "keep"}
    del_ids = {a["file_id"] for a in staged if a["action_type"] == "delete"}

    assert keep_ids == {oldest["id"]}
    assert del_ids == {f["id"] for f in dup_group if f["id"] != oldest["id"]}


def test_batch_rule_keep_largest_stages_correct_actions(qtbot, db, session_id, dup_group):
    # Req 4.5 — plan §UI Tests: test_batch_rule_keep_largest_stages_correct_actions
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    with patch("ui.compare_view._BatchRulesDialog") as MockDlg:
        from PyQt6.QtWidgets import QDialog
        instance = MockDlg.return_value
        instance.exec.return_value = QDialog.DialogCode.Accepted
        instance.selected_rule = "keep_largest"
        cv._on_batch_rules()

    staged = db.get_staged_actions(session_id)
    # The largest file should be KEEP.
    largest = max(dup_group, key=lambda f: f["size"])
    keep_ids = {a["file_id"] for a in staged if a["action_type"] == "keep"}

    assert keep_ids == {largest["id"]}


# ── Rename tests ─────────────────────────────────────────────────────────────

def test_rename_action_staged_with_new_name(compare_view, dup_group, db, session_id):
    # Req 4.5 — plan §UI Tests: test_rename_action_staged_with_new_name
    fid = dup_group[0]["id"]
    compare_view._on_rename(fid, "vacation_beach_2023.jpg")

    staged = db.get_staged_actions(session_id)
    rename_actions = [a for a in staged if a["action_type"] == "rename"]
    assert len(rename_actions) == 1
    assert rename_actions[0]["detail"] == "vacation_beach_2023.jpg"
    assert rename_actions[0]["file_id"] == fid


def test_rename_with_invalid_name_is_not_staged(compare_view, dup_group, db, session_id):
    # Invalid name (path separator) should not be staged.
    fid = dup_group[0]["id"]
    compare_view._on_rename(fid, "../../evil.jpg")

    staged = db.get_staged_actions(session_id)
    assert len(staged) == 0


# ── Rename validation (plan §Security — rename path traversal) ──────────────

def test_rename_rejects_path_separator():
    assert _validate_rename("../../evil.jpg") is False


def test_rename_rejects_empty_string():
    assert _validate_rename("") is False


def test_rename_rejects_leading_dot():
    assert _validate_rename(".hidden") is False


def test_rename_rejects_over_255_chars():
    assert _validate_rename("a" * 256) is False


def test_rename_accepts_valid_filename():
    assert _validate_rename("vacation_beach_2023.jpg") is True


def test_rename_rejects_backslash():
    assert _validate_rename("sub\\file.jpg") is False


def test_rename_rejects_forward_slash():
    assert _validate_rename("sub/file.jpg") is False


# ── Confirmation dialog tests ───────────────────────────────────────────────

def test_confirmation_dialog_lists_all_staged_deletes(qtbot, dup_group):
    # Req 4.5 — plan §UI Tests: test_confirmation_dialog_lists_all_staged_deletes
    action_list = [
        {"action_type": "delete", "path": dup_group[0]["path"], "detail": ""},
        {"action_type": "delete", "path": dup_group[1]["path"], "detail": ""},
    ]
    dlg = _ConfirmDialog(action_list)
    qtbot.addWidget(dlg)

    assert dlg._list.count() == 2
    for i in range(2):
        text = dlg._list.item(i).text()
        assert "DELETE" in text


def test_confirmation_dialog_lists_rename_action(qtbot, dup_group):
    action_list = [
        {"action_type": "rename", "path": dup_group[0]["path"],
         "detail": "new_name.jpg"},
    ]
    dlg = _ConfirmDialog(action_list)
    qtbot.addWidget(dlg)

    assert dlg._list.count() == 1
    text = dlg._list.item(0).text()
    assert "RENAME" in text
    assert "new_name.jpg" in text


def test_confirm_sets_action_status_to_confirmed(qtbot, db, session_id, dup_group):
    # Req 4.5 — plan §UI Tests: test_confirm_sets_action_status_to_confirmed
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    # Stage a KEEP on file 0, which auto-stages DELETE on files 1 and 2.
    cv._on_keep(dup_group[0]["id"])

    staged = db.get_staged_actions(session_id)
    action_list = [
        {"action_type": a["action_type"], "path": a["path"],
         "detail": a["detail"], "action_id": a["id"], "file_id": a["file_id"]}
        for a in staged
    ]

    # Execute actions directly (bypasses dialog).
    cv._execute_actions(action_list)

    # Verify all actions are confirmed.
    for a in staged:
        row = db.get_action(a["id"])
        assert row["status"] == "confirmed"
        assert row["performed_at"] is not None


def test_confirm_deletes_file_from_disk(qtbot, db, session_id, dup_group, tmp_path):
    # After confirmation, deleted files should be removed from disk.
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    target_file = dup_group[1]["path"]
    assert os.path.isfile(target_file)

    # Stage delete for file 1 only.
    aid = db.stage_action(dup_group[1]["id"], "delete")
    staged = db.get_staged_actions(session_id)
    action_list = [
        {"action_type": a["action_type"], "path": a["path"],
         "detail": a["detail"], "action_id": a["id"], "file_id": a["file_id"]}
        for a in staged
    ]
    cv._execute_actions(action_list)

    assert not os.path.isfile(target_file)
    file_row = db.get_file(dup_group[1]["id"])
    assert file_row["status"] == "deleted"


def test_confirm_renames_file_on_disk(qtbot, db, session_id, dup_group, tmp_path):
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    old_path = dup_group[0]["path"]
    new_name = "renamed_photo.jpg"
    expected_dest = str(Path(old_path).parent / new_name)

    assert os.path.isfile(old_path)

    aid = db.stage_action(dup_group[0]["id"], "rename", detail=new_name)
    staged = db.get_staged_actions(session_id)
    action_list = [
        {"action_type": a["action_type"], "path": a["path"],
         "detail": a["detail"], "action_id": a["id"], "file_id": a["file_id"]}
        for a in staged
    ]
    cv._execute_actions(action_list)

    assert not os.path.isfile(old_path)
    assert os.path.isfile(expected_dest)
    file_row = db.get_file(dup_group[0]["id"])
    assert file_row["status"] == "renamed"
    assert file_row["path"] == expected_dest


# ── Path scope check (plan §Security — confirmed-delete path validation) ────

def test_delete_outside_scope_is_rejected(qtbot, db, session_id, dup_group, tmp_path):
    # File outside session_folders should NOT be deleted.
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    # Create a file outside the scan scope.
    outside = tmp_path / "outside" / "evil.jpg"
    outside.parent.mkdir(exist_ok=True)
    outside.write_bytes(b"\xff\xd8" + b"\x00" * 10)
    fid = db.insert_file(session_id, str(outside), 100, "2026-01-01T00:00:00Z",
                         "2026-01-01T00:00:00Z")
    db.update_pixel_hash(fid, HASH_DUP, f"/thumbs/{HASH_DUP}.jpg")

    aid = db.stage_action(fid, "delete")
    action_list = [{
        "action_type": "delete", "path": str(outside), "detail": "",
        "action_id": aid, "file_id": fid,
    }]

    # Suppress the warning dialog.
    with patch.object(cv, "tr", side_effect=lambda s, *a: s.format(*a) if a else s):
        with patch("ui.compare_view.QMessageBox"):
            cv._execute_actions(action_list)

    # File should still exist — delete was rejected.
    assert os.path.isfile(str(outside))
    # Action should NOT be confirmed.
    row = db.get_action(aid)
    assert row["status"] == "staged"


# ── Signal tests ─────────────────────────────────────────────────────────────

def test_actions_confirmed_signal_emitted(qtbot, db, session_id, dup_group):
    # Plan §Phase 4.1 — actions_confirmed signal.
    folders = db.get_session_folders(session_id)
    cv = CompareView(db=db, session_id=session_id, pixel_hash=HASH_DUP,
                     session_folders=folders)
    qtbot.addWidget(cv)

    cv._on_keep(dup_group[0]["id"])
    staged = db.get_staged_actions(session_id)
    action_list = [
        {"action_type": a["action_type"], "path": a["path"],
         "detail": a["detail"], "action_id": a["id"], "file_id": a["file_id"]}
        for a in staged
    ]

    with qtbot.waitSignal(cv.actions_confirmed, timeout=1000):
        cv._execute_actions(action_list)


def test_closed_signal_emitted_on_close(qtbot, db, session_id, dup_group):
    # Plan §Phase 4.1 — closed signal.
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
