"""
tests/ui/test_folder_panel.py — UI tests for ui/folder_panel.py.
Plan §UI Tests: folder_panel.

Req 4.1 — Browse, select, and add folders to the scan scope.
"""

from datetime import datetime, timezone

import pytest

from ui.folder_panel import FolderPanel


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def session_id(db):
    """Create a fresh session and return its id."""
    now = datetime.now(timezone.utc).isoformat()
    return db.create_session(name="UI test session", created_at=now)


@pytest.fixture
def panel(qtbot, db, session_id):
    """FolderPanel wired to the test DB with an active session."""
    p = FolderPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_add_folder_appears_in_list(panel, tmp_path):
    # Req 4.1 — plan §UI Tests: test_add_folder_appears_in_list
    folder = str(tmp_path / "Photos")
    panel.add_folder(folder, persist=False)
    assert panel.folders() == [folder]


def test_remove_folder_removes_from_list(panel, tmp_path):
    # Req 4.1 — plan §UI Tests: test_remove_folder_removes_from_list
    folder = str(tmp_path / "Photos")
    panel.add_folder(folder, persist=False)
    panel.remove_folder(folder, persist=False)
    assert panel.folders() == []


def test_duplicate_folder_not_added_twice(panel, tmp_path):
    # plan §UI Tests: test_duplicate_folder_not_added_twice
    folder = str(tmp_path / "Photos")
    panel.add_folder(folder, persist=False)
    panel.add_folder(folder, persist=False)
    assert len(panel.folders()) == 1


def test_folder_list_persists_to_db(panel, db, session_id, tmp_path):
    # Req 4.1 — plan §UI Tests: test_folder_list_persists_to_db
    folder = str(tmp_path / "Photos")
    panel.add_folder(folder, persist=True)
    stored = db.get_session_folders(session_id)
    assert folder in stored


def test_remove_folder_removes_from_db(panel, db, session_id, tmp_path):
    # Complementary: ensure removal is persisted to the DB.
    folder = str(tmp_path / "Photos")
    panel.add_folder(folder, persist=True)
    panel.remove_folder(folder, persist=True)
    stored = db.get_session_folders(session_id)
    assert folder not in stored


def test_folders_changed_signal_emitted_on_add(qtbot, panel, tmp_path):
    folder = str(tmp_path / "A")
    with qtbot.waitSignal(panel.folders_changed, timeout=1000) as blocker:
        panel.add_folder(folder, persist=False)
    assert folder in blocker.args[0]


def test_folders_changed_signal_emitted_on_remove(qtbot, panel, tmp_path):
    folder = str(tmp_path / "A")
    panel.add_folder(folder, persist=False)
    with qtbot.waitSignal(panel.folders_changed, timeout=1000):
        panel.remove_folder(folder, persist=False)
    assert folder not in panel.folders()


def test_remove_btn_disabled_when_nothing_selected(panel):
    # Remove button starts disabled when list is empty.
    assert not panel._remove_btn.isEnabled()


def test_remove_btn_enabled_after_selection(panel, tmp_path):
    folder = str(tmp_path / "Photos")
    panel.add_folder(folder, persist=False)
    panel._list.setCurrentRow(0)
    assert panel._remove_btn.isEnabled()


def test_add_without_session_id_does_not_persist(qtbot, db, tmp_path):
    # When no session_id is set, add_folder must not attempt a DB write.
    panel = FolderPanel(db=db)  # session_id=None
    qtbot.addWidget(panel)
    folder = str(tmp_path / "Unsaved")
    panel.add_folder(folder, persist=True)   # persist=True but no session_id
    assert panel.folders() == [folder]       # in-memory list is populated
    # No session exists, so no rows can be in session_folders.
    # (The DB has no sessions at all — any query returns empty.)
    rows = db.conn.execute("SELECT * FROM session_folders").fetchall()
    assert rows == []
