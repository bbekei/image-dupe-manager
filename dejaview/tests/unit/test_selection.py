"""
Tests for core/selection.py — Smart selection presets and Master Copy logic.

UX Redesign Phase 5 — Advanced Cleanup.
"""

import datetime

import pytest

from core.selection import (
    SelectionPreset,
    apply_preset,
    get_master_copies,
    identify_master_copy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _insert_file(db, session_id, path, size, modified_at, pixel_hash):
    """Insert a file and update its pixel_hash, returning file_id."""
    fid = db.insert_file(session_id, path, size, modified_at, _now())
    if pixel_hash:
        db.update_pixel_hash(fid, pixel_hash, f"/thumbs/{pixel_hash}.jpg")
    return fid


# ---------------------------------------------------------------------------
# identify_master_copy
# ---------------------------------------------------------------------------

class TestIdentifyMasterCopy:
    """Tests for identify_master_copy()."""

    def test_empty_list(self):
        assert identify_master_copy([]) is None

    def test_single_file(self):
        files = [{"id": 1, "size": 1000, "modified_at": "2024-01-01", "path": "/a.jpg"}]
        assert identify_master_copy(files) == 1

    def test_largest_wins(self):
        files = [
            {"id": 1, "size": 500, "modified_at": "2024-01-01", "path": "/a.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-01-01", "path": "/b.jpg"},
        ]
        assert identify_master_copy(files) == 2

    def test_newest_tiebreak(self):
        files = [
            {"id": 1, "size": 1000, "modified_at": "2024-01-01", "path": "/a.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-06-01", "path": "/b.jpg"},
        ]
        assert identify_master_copy(files) == 2

    def test_path_tiebreak_when_equal(self):
        files = [
            {"id": 1, "size": 1000, "modified_at": "2024-01-01", "path": "/b.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-01-01", "path": "/a.jpg"},
        ]
        # Shortest path alphabetically = /a.jpg → id 2
        assert identify_master_copy(files) == 2

    def test_missing_fields(self):
        files = [
            {"id": 1, "size": None, "modified_at": None, "path": ""},
            {"id": 2, "size": 100, "modified_at": "", "path": "/x.jpg"},
        ]
        assert identify_master_copy(files) == 2


# ---------------------------------------------------------------------------
# apply_preset
# ---------------------------------------------------------------------------

class TestApplyPreset:
    """Tests for apply_preset() with database integration."""

    def test_keep_largest(self, db, session_factory):
        sid = session_factory()
        h = "a" * 32
        f1 = _insert_file(db, sid, "/small.jpg", 500, "2024-01-01", h)
        f2 = _insert_file(db, sid, "/large.jpg", 2000, "2024-01-01", h)

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_LARGEST_FILE)

        assert keep == 1
        assert delete == 1
        actions = {r["file_id"]: r["action"] for r in db.get_file_actions_for_session(sid)}
        assert actions[f2] == "keep"
        assert actions[f1] == "delete"

    def test_keep_newest(self, db, session_factory):
        sid = session_factory()
        h = "b" * 32
        f1 = _insert_file(db, sid, "/old.jpg", 1000, "2020-01-01", h)
        f2 = _insert_file(db, sid, "/new.jpg", 1000, "2024-06-15", h)

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_NEWEST)

        actions = {r["file_id"]: r["action"] for r in db.get_file_actions_for_session(sid)}
        assert actions[f2] == "keep"
        assert actions[f1] == "delete"

    def test_keep_deepest_path(self, db, session_factory):
        sid = session_factory()
        h = "c" * 32
        f1 = _insert_file(db, sid, "/x.jpg", 1000, "2024-01-01", h)
        f2 = _insert_file(db, sid, "/a/b/c/deep.jpg", 1000, "2024-01-01", h)

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_DEEPEST_PATH)

        actions = {r["file_id"]: r["action"] for r in db.get_file_actions_for_session(sid)}
        assert actions[f2] == "keep"
        assert actions[f1] == "delete"

    def test_keep_shortest_path(self, db, session_factory):
        sid = session_factory()
        h = "d" * 32
        f1 = _insert_file(db, sid, "/short.jpg", 1000, "2024-01-01", h)
        f2 = _insert_file(db, sid, "/a/b/c/deep.jpg", 1000, "2024-01-01", h)

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_SHORTEST_PATH)

        actions = {r["file_id"]: r["action"] for r in db.get_file_actions_for_session(sid)}
        assert actions[f1] == "keep"
        assert actions[f2] == "delete"

    def test_singleton_group_skipped(self, db, session_factory):
        """Groups with only 1 file are not touched."""
        sid = session_factory()
        h = "e" * 32
        _insert_file(db, sid, "/only.jpg", 1000, "2024-01-01", h)

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_LARGEST_FILE)

        assert keep == 0
        assert delete == 0
        assert len(db.get_file_actions_for_session(sid)) == 0

    def test_multiple_groups(self, db, session_factory):
        """Multiple duplicate groups are all processed."""
        sid = session_factory()
        h1 = "f" * 32
        h2 = "0" * 32
        _insert_file(db, sid, "/a1.jpg", 100, "2024-01-01", h1)
        _insert_file(db, sid, "/a2.jpg", 200, "2024-01-01", h1)
        _insert_file(db, sid, "/b1.jpg", 300, "2024-01-01", h2)
        _insert_file(db, sid, "/b2.jpg", 400, "2024-01-01", h2)

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_LARGEST_FILE)

        assert keep == 2
        assert delete == 2

    def test_keep_oldest(self, db, session_factory):
        sid = session_factory()
        h = "g" * 32
        f1 = _insert_file(db, sid, "/old.jpg", 1000, "2018-03-01", h)
        f2 = _insert_file(db, sid, "/new.jpg", 1000, "2024-06-15", h)

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_OLDEST)

        actions = {r["file_id"]: r["action"] for r in db.get_file_actions_for_session(sid)}
        assert actions[f1] == "keep"
        assert actions[f2] == "delete"

    def test_keep_highest_resolution(self, db, session_factory):
        sid = session_factory()
        h = "h" * 32
        f1 = _insert_file(db, sid, "/low.jpg", 1000, "2024-01-01", h)
        f2 = _insert_file(db, sid, "/high.jpg", 1000, "2024-01-01", h)
        # Set resolution: f1=640x480, f2=1920x1080
        db.update_perceptual_hashes_batch([
            (f1, "p" * 16, 640, 480),
            (f2, "q" * 16, 1920, 1080),
        ])

        keep, delete = apply_preset(db, sid, SelectionPreset.KEEP_HIGHEST_RESOLUTION)

        actions = {r["file_id"]: r["action"] for r in db.get_file_actions_for_session(sid)}
        assert actions[f2] == "keep"
        assert actions[f1] == "delete"

    def test_filtered_hashes(self, db, session_factory):
        """Only groups in the pixel_hashes list are processed."""
        sid = session_factory()
        h1 = "f" * 32
        h2 = "0" * 32
        _insert_file(db, sid, "/a1.jpg", 100, "2024-01-01", h1)
        _insert_file(db, sid, "/a2.jpg", 200, "2024-01-01", h1)
        _insert_file(db, sid, "/b1.jpg", 300, "2024-01-01", h2)
        _insert_file(db, sid, "/b2.jpg", 400, "2024-01-01", h2)

        keep, delete = apply_preset(
            db, sid, SelectionPreset.KEEP_LARGEST_FILE, pixel_hashes=[h1]
        )

        assert keep == 1
        assert delete == 1
        # h2 group should have no actions
        actions = db.get_file_actions_for_session(sid)
        action_hashes = set()
        for a in actions:
            f = db.get_file(a["file_id"])
            action_hashes.add(f["pixel_hash"])
        assert h2 not in action_hashes


# ---------------------------------------------------------------------------
# get_master_copies
# ---------------------------------------------------------------------------

class TestGetMasterCopies:
    """Tests for get_master_copies()."""

    def test_returns_master_per_group(self, db, session_factory):
        sid = session_factory()
        h = "a" * 32
        _insert_file(db, sid, "/small.jpg", 500, "2024-01-01", h)
        f2 = _insert_file(db, sid, "/large.jpg", 2000, "2024-01-01", h)

        masters = get_master_copies(db, sid)

        assert masters[h] == f2

    def test_empty_session(self, db, session_factory):
        sid = session_factory()
        masters = get_master_copies(db, sid)
        assert masters == {}
