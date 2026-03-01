"""
tests/ui/test_results_panel.py — UI tests for ui/results_panel.py.
Plan §UI Tests: results_panel — Req 4.3.

Tests cover:
- All filter shows every file
- Duplicates Only filter hides unique files
- Duplicate badge visible on duplicate file
- No badge on unique file
- Double-clicking duplicate file emits compare_view_requested
- 200ms debounce queues and flushes correctly
"""

import pytest

from PyQt6.QtCore import Qt

from data.db import Database
from ui.results_panel import (
    FILTER_ALL,
    FILTER_CROSS_LIBRARY,
    FILTER_DUPLICATES_ONLY,
    ROLE_FILE_ID,
    ROLE_IS_DUPLICATE,
    ROLE_NODE_TYPE,
    ROLE_PIXEL_HASH,
    ResultsPanel,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

HASH_A = "a" * 64  # duplicate hash
HASH_B = "b" * 64  # unique hash
HASH_C = "c" * 64  # unique hash


def _populate_db(db: Database, session_id: int) -> dict:
    """
    Insert 5 files: 2 duplicates (HASH_A), 3 unique (HASH_B, HASH_C, None).
    Returns a dict mapping label → file_id.
    """
    now = "2026-01-01T00:00:00Z"
    ids = {}

    # Duplicate pair
    ids["dup1"] = db.insert_file(session_id, "/photos/img001.jpg", 1000, now, now)
    db.update_pixel_hash(ids["dup1"], HASH_A, f"/thumbs/{HASH_A}.jpg")
    ids["dup2"] = db.insert_file(session_id, "/photos/sub/img002.jpg", 1000, now, now)
    db.update_pixel_hash(ids["dup2"], HASH_A, f"/thumbs/{HASH_A}.jpg")

    # Unique files
    ids["uniq1"] = db.insert_file(session_id, "/photos/img003.jpg", 2000, now, now)
    db.update_pixel_hash(ids["uniq1"], HASH_B, f"/thumbs/{HASH_B}.jpg")
    ids["uniq2"] = db.insert_file(session_id, "/photos/img004.jpg", 3000, now, now)
    db.update_pixel_hash(ids["uniq2"], HASH_C, f"/thumbs/{HASH_C}.jpg")

    # Unhashed file (discovered but not yet hashed)
    ids["unhashed"] = db.insert_file(session_id, "/photos/img005.jpg", 4000, now, now)

    return ids


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def session_id(db):
    return db.create_session("Test", "2026-01-01T00:00:00Z")


@pytest.fixture
def populated_db(db, session_id):
    """DB with 5 files (2 duplicates, 3 unique/unhashed)."""
    ids = _populate_db(db, session_id)
    return db, session_id, ids


@pytest.fixture
def panel(qtbot, populated_db):
    """ResultsPanel loaded with the populated session."""
    db, session_id, ids = populated_db
    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)
    p.reload()
    return p, ids


# ── Filter tests ─────────────────────────────────────────────────────────────

def test_all_filter_shows_every_file(panel):
    # Req 4.3 — plan §UI Tests: test_all_filter_shows_every_file
    p, ids = panel
    p.set_filter(FILTER_ALL)
    assert p.visible_file_count() == 5


def test_duplicates_only_filter_hides_unique_files(panel):
    # Req 4.3 — plan §UI Tests: test_duplicates_only_filter_hides_unique_files
    p, ids = panel
    p.set_filter(FILTER_DUPLICATES_ONLY)
    assert p.visible_file_count() == 2


def test_duplicates_only_shows_correct_files(panel):
    # Verify the correct files are shown (the duplicate pair).
    p, ids = panel
    p.set_filter(FILTER_DUPLICATES_ONLY)
    visible = p.visible_items_data()
    visible_ids = {item["file_id"] for item in visible}
    assert ids["dup1"] in visible_ids
    assert ids["dup2"] in visible_ids
    assert ids["uniq1"] not in visible_ids


def test_switching_back_to_all_restores_full_list(panel):
    p, ids = panel
    p.set_filter(FILTER_DUPLICATES_ONLY)
    assert p.visible_file_count() == 2
    p.set_filter(FILTER_ALL)
    assert p.visible_file_count() == 5


# ── Badge tests ──────────────────────────────────────────────────────────────

def test_duplicate_badge_visible_on_duplicate_file(panel):
    # Req 4.3 — plan §UI Tests: test_duplicate_badge_visible_on_duplicate_file
    p, ids = panel
    visible = p.visible_items_data()
    dup_items = [v for v in visible if v["file_id"] == ids["dup1"]]
    assert len(dup_items) == 1
    assert "DUPLICATE" in dup_items[0]["badge_text"]


def test_no_badge_on_unique_file(panel):
    # Req 4.3 — plan §UI Tests: test_no_badge_on_unique_file
    p, ids = panel
    visible = p.visible_items_data()
    uniq_items = [v for v in visible if v["file_id"] == ids["uniq1"]]
    assert len(uniq_items) == 1
    assert uniq_items[0]["badge_text"] == ""


def test_no_badge_on_unhashed_file(panel):
    p, ids = panel
    visible = p.visible_items_data()
    unhashed = [v for v in visible if v["file_id"] == ids["unhashed"]]
    assert len(unhashed) == 1
    assert unhashed[0]["badge_text"] == ""
    assert unhashed[0]["is_duplicate"] is False


# ── Compare view signal ──────────────────────────────────────────────────────

def test_double_clicking_duplicate_emits_compare_view_requested(qtbot, populated_db):
    # Req 4.3 — plan §UI Tests: test_clicking_duplicate_file_opens_compare_view
    db, session_id, ids = populated_db
    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)
    p.reload()

    # Find the proxy index for dup1.
    dup1_source_item = p._find_file_item(ids["dup1"])
    assert dup1_source_item is not None
    source_index = p._model.indexFromItem(dup1_source_item)
    proxy_index = p._proxy.mapFromSource(source_index)
    assert proxy_index.isValid()

    with qtbot.waitSignal(p.compare_view_requested, timeout=1000) as blocker:
        p._on_item_double_clicked(proxy_index)

    assert blocker.args == [HASH_A]


def test_double_clicking_unique_file_does_not_emit_signal(qtbot, populated_db):
    db, session_id, ids = populated_db
    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)
    p.reload()

    uniq_item = p._find_file_item(ids["uniq1"])
    assert uniq_item is not None
    source_index = p._model.indexFromItem(uniq_item)
    proxy_index = p._proxy.mapFromSource(source_index)

    # Should NOT emit — unique file is not a duplicate.
    signal_emitted = False

    def _on_signal(ph):
        nonlocal signal_emitted
        signal_emitted = True

    p.compare_view_requested.connect(_on_signal)
    p._on_item_double_clicked(proxy_index)
    assert not signal_emitted


def test_double_clicking_folder_does_not_emit_signal(qtbot, populated_db):
    db, session_id, ids = populated_db
    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)
    p.reload()

    # Get the first folder node from proxy model.
    first_idx = p._proxy.index(0, 0)
    assert first_idx.isValid()

    signal_emitted = False

    def _on_signal(ph):
        nonlocal signal_emitted
        signal_emitted = True

    p.compare_view_requested.connect(_on_signal)
    p._on_item_double_clicked(first_idx)
    assert not signal_emitted


# ── Debounce tests ───────────────────────────────────────────────────────────

def test_debounce_queues_file_discoveries(qtbot, db, session_id):
    # Req 4.3 — plan §Resource Usage: UI update rate-limiting (200ms debounce).
    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)

    now = "2026-01-01T00:00:00Z"
    fid = db.insert_file(session_id, "/new/photo.jpg", 500, now, now)

    # Enqueue discovery — tree should NOT update immediately.
    p.on_file_discovered(fid, "/new/photo.jpg")
    assert p.visible_file_count() == 0  # not yet flushed

    # Manually flush the debounce queue.
    p._flush_pending()
    assert p.visible_file_count() == 1


def test_debounce_updates_badge_on_hash_complete(qtbot, db, session_id):
    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)

    now = "2026-01-01T00:00:00Z"
    fid1 = db.insert_file(session_id, "/a/img1.jpg", 1000, now, now)
    fid2 = db.insert_file(session_id, "/a/img2.jpg", 1000, now, now)

    # Discover files first (flush immediately).
    p.on_file_discovered(fid1, "/a/img1.jpg")
    p.on_file_discovered(fid2, "/a/img2.jpg")
    p._flush_pending()
    assert p.visible_file_count() == 2

    # Now hash both — they become duplicates.
    hash_val = "d" * 64
    db.update_pixel_hash(fid1, hash_val, f"/thumbs/{hash_val}.jpg")
    db.update_pixel_hash(fid2, hash_val, f"/thumbs/{hash_val}.jpg")

    # Signal duplicate found.
    p.on_duplicate_found(hash_val, [fid1, fid2])
    p._flush_pending()

    visible = p.visible_items_data()
    dup_badges = [v for v in visible if "DUPLICATE" in v["badge_text"]]
    assert len(dup_badges) == 2


# ── Tree structure tests ────────────────────────────────────────────────────

def test_folder_hierarchy_created_correctly(panel):
    """Files are shown in their original folder context (plan §Workflow 2)."""
    p, ids = panel
    # Root item should have folder children, not file children directly.
    root = p._model.invisibleRootItem()
    assert root.rowCount() > 0
    # First child should be a folder ("photos" or a drive root).
    first_child = root.child(0, 0)
    assert first_child.data(ROLE_NODE_TYPE) == "folder"


def test_reload_clears_and_rebuilds(panel):
    p, ids = panel
    assert p.visible_file_count() == 5
    p.reload()
    assert p.visible_file_count() == 5  # same count after reload


def test_set_session_id_triggers_reload(qtbot, db):
    p = ResultsPanel(db=db)
    qtbot.addWidget(p)
    assert p.visible_file_count() == 0

    sid = db.create_session("Test", "2026-01-01T00:00:00Z")
    now = "2026-01-01T00:00:00Z"
    db.insert_file(sid, "/x/a.jpg", 100, now, now)

    p.set_session_id(sid)
    assert p.visible_file_count() == 1


# ── Filter radio button tests ───────────────────────────────────────────────

def test_radio_all_checked_by_default(qtbot, db):
    p = ResultsPanel(db=db)
    qtbot.addWidget(p)
    assert p._radio_all.isChecked()
    assert p.current_filter == FILTER_ALL


def test_cross_library_radio_disabled_without_data(qtbot, db):
    # Cross-Library radio disabled when no cross-library data exists.
    p = ResultsPanel(db=db)
    qtbot.addWidget(p)
    assert not p._radio_cross.isEnabled()


# ── Cross-Library filter tests (Phase 5) ─────────────────────────────────────

HASH_CROSS = "e" * 64


@pytest.fixture
def cross_library_panel(qtbot, db, session_id):
    """ResultsPanel with cross-library data: one file matches a remote peer."""
    now = "2026-01-01T00:00:00Z"
    ids = {}

    # Local files: 2 duplicates + 1 unique + 1 cross-library match
    ids["dup1"] = db.insert_file(session_id, "/photos/img001.jpg", 1000, now, now)
    db.update_pixel_hash(ids["dup1"], HASH_A, f"/thumbs/{HASH_A}.jpg")
    ids["dup2"] = db.insert_file(session_id, "/photos/img002.jpg", 1000, now, now)
    db.update_pixel_hash(ids["dup2"], HASH_A, f"/thumbs/{HASH_A}.jpg")
    ids["uniq"] = db.insert_file(session_id, "/photos/img003.jpg", 2000, now, now)
    db.update_pixel_hash(ids["uniq"], HASH_B, f"/thumbs/{HASH_B}.jpg")
    ids["cross"] = db.insert_file(session_id, "/photos/img004.jpg", 3000, now, now)
    db.update_pixel_hash(ids["cross"], HASH_CROSS, f"/thumbs/{HASH_CROSS}.jpg")

    # Remote peer with matching hash
    peer_id = db.upsert_remote_peer("alice", now)
    db.insert_remote_files(peer_id, [
        {"remote_id": "alice:1", "pixel_hash": HASH_CROSS,
         "filename": "alice_photo.jpg", "size": 3000},
    ])

    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)
    p.reload()
    return p, ids


def test_cross_library_radio_enabled_with_data(cross_library_panel):
    """Cross-Library radio becomes enabled when matches exist (plan §Phase 5)."""
    p, ids = cross_library_panel
    assert p._radio_cross.isEnabled()


def test_cross_library_filter_shows_only_matching_files(cross_library_panel):
    """Plan §UI Tests: test_cross_library_filter_shows_cross_matches."""
    p, ids = cross_library_panel
    p.set_filter(FILTER_CROSS_LIBRARY)
    assert p.visible_file_count() == 1
    visible = p.visible_items_data()
    assert visible[0]["file_id"] == ids["cross"]


def test_cross_library_filter_hides_duplicates_and_unique(cross_library_panel):
    """Only cross-library matched files visible, not local duplicates or uniques."""
    p, ids = cross_library_panel
    p.set_filter(FILTER_CROSS_LIBRARY)
    visible_ids = {v["file_id"] for v in p.visible_items_data()}
    assert ids["dup1"] not in visible_ids
    assert ids["dup2"] not in visible_ids
    assert ids["uniq"] not in visible_ids


def test_update_cross_library_data_refreshes(qtbot, db, session_id):
    """update_cross_library_data() re-enables the filter after import."""
    now = "2026-01-01T00:00:00Z"
    fid = db.insert_file(session_id, "/photos/x.jpg", 1000, now, now)
    db.update_pixel_hash(fid, HASH_CROSS, f"/thumbs/{HASH_CROSS}.jpg")

    p = ResultsPanel(db=db, session_id=session_id)
    qtbot.addWidget(p)
    p.reload()
    assert not p._radio_cross.isEnabled()

    # Simulate import
    peer_id = db.upsert_remote_peer("bob", now)
    db.insert_remote_files(peer_id, [
        {"remote_id": "bob:1", "pixel_hash": HASH_CROSS, "size": 1000},
    ])
    p.update_cross_library_data()

    assert p._radio_cross.isEnabled()
    p.set_filter(FILTER_CROSS_LIBRARY)
    assert p.visible_file_count() == 1
