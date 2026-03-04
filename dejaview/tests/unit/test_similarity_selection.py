"""
tests/unit/test_similarity_selection.py — Unit tests for core/similarity_selection.py.

Plan reference: §S3.2 — Recommendation logic tests.
"""

import datetime

import pytest

from core.similarity_selection import (
    SimilarityPreset,
    _pick_similarity_keeper,
    apply_similarity_preset,
    recommend_keeper,
)
from data.db import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_hash(prefix: str = "a") -> str:
    return (prefix * 32)[:32]


def _file(
    fid: int,
    width: int = 100,
    height: int = 100,
    size: int = 1000,
    modified_at: str = "2024-01-01T00:00:00",
    path: str = "",
) -> dict:
    return {
        "id": fid,
        "width": width,
        "height": height,
        "size": size,
        "modified_at": modified_at,
        "path": path or f"/photos/img_{fid}.jpg",
    }


# ---------------------------------------------------------------------------
# recommend_keeper tests
# ---------------------------------------------------------------------------

class TestRecommendKeeper:

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            recommend_keeper([])

    def test_single_file(self):
        fid, reason = recommend_keeper([_file(1)])
        assert fid == 1

    def test_highest_resolution_wins(self):
        files = [
            _file(1, width=100, height=100, size=5000),   # 10k px
            _file(2, width=4032, height=3024, size=3000),  # 12.2M px
        ]
        fid, reason = recommend_keeper(files)
        assert fid == 2
        assert "resolution" in reason

    def test_same_resolution_largest_file_wins(self):
        files = [
            _file(1, width=100, height=100, size=1000),
            _file(2, width=100, height=100, size=5000),
        ]
        fid, reason = recommend_keeper(files)
        assert fid == 2
        assert "file" in reason

    def test_tiebreak_by_modified_at(self):
        files = [
            _file(1, width=100, height=100, size=1000,
                  modified_at="2024-01-01T00:00:00"),
            _file(2, width=100, height=100, size=1000,
                  modified_at="2024-06-15T12:00:00"),
        ]
        fid, _ = recommend_keeper(files)
        assert fid == 2  # newer

    def test_tiebreak_by_shortest_path(self):
        files = [
            _file(1, width=100, height=100, size=1000,
                  modified_at="2024-01-01",
                  path="/very/long/deeply/nested/path/img.jpg"),
            _file(2, width=100, height=100, size=1000,
                  modified_at="2024-01-01",
                  path="/short/img.jpg"),
        ]
        fid, _ = recommend_keeper(files)
        assert fid == 2  # shorter path

    def test_none_dimensions_treated_as_zero(self):
        files = [
            {"id": 1, "width": None, "height": None, "size": 5000,
             "modified_at": "", "path": "/a.jpg"},
            {"id": 2, "width": 100, "height": 100, "size": 1000,
             "modified_at": "", "path": "/b.jpg"},
        ]
        fid, _ = recommend_keeper(files)
        assert fid == 2  # has resolution; file 1 has 0x0


# ---------------------------------------------------------------------------
# _pick_similarity_keeper tests
# ---------------------------------------------------------------------------

class TestPickSimilarityKeeper:

    def test_keep_highest_resolution(self):
        files = [
            _file(1, width=800, height=600),    # 480k
            _file(2, width=4032, height=3024),   # 12.2M
        ]
        assert _pick_similarity_keeper(
            files, SimilarityPreset.KEEP_HIGHEST_RESOLUTION
        ) == 2

    def test_keep_largest_file(self):
        files = [
            _file(1, size=1000),
            _file(2, size=50000),
        ]
        assert _pick_similarity_keeper(
            files, SimilarityPreset.KEEP_LARGEST_FILE
        ) == 2

    def test_keep_newest(self):
        files = [
            _file(1, modified_at="2024-01-01"),
            _file(2, modified_at="2024-12-25"),
        ]
        assert _pick_similarity_keeper(
            files, SimilarityPreset.KEEP_NEWEST
        ) == 2

    def test_keep_oldest(self):
        files = [
            _file(1, modified_at="2020-01-01"),
            _file(2, modified_at="2024-12-25"),
        ]
        assert _pick_similarity_keeper(
            files, SimilarityPreset.KEEP_OLDEST
        ) == 1

    def test_keep_shortest_path(self):
        files = [
            _file(1, path="/a/b/c/d/e/f/img.jpg"),
            _file(2, path="/a/img.jpg"),
        ]
        assert _pick_similarity_keeper(
            files, SimilarityPreset.KEEP_SHORTEST_PATH
        ) == 2


# ---------------------------------------------------------------------------
# apply_similarity_preset integration tests (with real DB)
# ---------------------------------------------------------------------------

class TestApplySimilarityPreset:

    def _setup_group(self, db: Database, session_id: int):
        """Create a similarity group with 3 files of different resolutions."""
        now = _now()
        f1 = db.insert_file(session_id, "/photos/hires.jpg", 12000, now, now)
        f2 = db.insert_file(session_id, "/photos/midres.jpg", 5000, now, now)
        f3 = db.insert_file(session_id, "/photos/lowres.jpg", 300, now, now)

        # Set pixel hashes (all different — these are similar, not exact dupes).
        db.update_pixel_hash(f1, _make_hash("a"), "/t/1.jpg")
        db.update_pixel_hash(f2, _make_hash("b"), "/t/2.jpg")
        db.update_pixel_hash(f3, _make_hash("c"), "/t/3.jpg")

        # Set dimensions.
        db.update_perceptual_hashes_batch([
            (f1, "aaaa", 4032, 3024),
            (f2, "aabb", 1920, 1080),
            (f3, "aacc", 800, 600),
        ])

        gid = db.create_similarity_group(
            session_id, now, f1, member_count=3,
        )
        db.add_similarity_group_members_batch([
            (gid, f1, 0),
            (gid, f2, 3),
            (gid, f3, 7),
        ])

        return gid, f1, f2, f3

    def test_keep_highest_resolution_marks_correctly(
        self, db: Database, session_factory
    ):
        sid = session_factory()
        gid, f_hi, f_mid, f_lo = self._setup_group(db, sid)

        keep, delete = apply_similarity_preset(
            db, sid, SimilarityPreset.KEEP_HIGHEST_RESOLUTION,
        )
        assert keep == 1
        assert delete == 2

        # Check that hires is kept.
        actions = db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}
        assert action_map[f_hi] == "keep"
        assert action_map[f_mid] == "delete"
        assert action_map[f_lo] == "delete"

    def test_keep_largest_file_marks_correctly(
        self, db: Database, session_factory
    ):
        sid = session_factory()
        gid, f_hi, f_mid, f_lo = self._setup_group(db, sid)

        keep, delete = apply_similarity_preset(
            db, sid, SimilarityPreset.KEEP_LARGEST_FILE,
        )
        assert keep == 1
        assert delete == 2

        actions = db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}
        assert action_map[f_hi] == "keep"  # 12000 bytes

    def test_subset_of_groups(self, db: Database, session_factory):
        """Only specified group_ids are processed."""
        sid = session_factory()
        gid1, f1, _, _ = self._setup_group(db, sid)

        # Create a second group.
        now = _now()
        f4 = db.insert_file(sid, "/other/x.jpg", 8000, now, now)
        f5 = db.insert_file(sid, "/other/y.jpg", 2000, now, now)
        db.update_pixel_hash(f4, _make_hash("d"), "/t/4.jpg")
        db.update_pixel_hash(f5, _make_hash("e"), "/t/5.jpg")
        db.update_perceptual_hashes_batch([
            (f4, "dddd", 1000, 1000),
            (f5, "ddee", 500, 500),
        ])
        gid2 = db.create_similarity_group(sid, now, f4, member_count=2)
        db.add_similarity_group_members_batch([(gid2, f4, 0), (gid2, f5, 4)])

        # Apply only to group 2.
        keep, delete = apply_similarity_preset(
            db, sid, SimilarityPreset.KEEP_HIGHEST_RESOLUTION,
            group_ids=[gid2],
        )
        assert keep == 1
        assert delete == 1

        # Group 1 should have no actions.
        actions = db.get_file_actions_for_session(sid)
        action_ids = {a["file_id"] for a in actions}
        assert f1 not in action_ids

    def test_master_copy_protection(self, db: Database, session_factory):
        """Last copy of a pixel_hash with exact dupes must NOT be deleted.

        Scenario: pixel_hash 'a' has 2 files (f1, f1b — exact duplicates).
        f1 is in a similarity group with f2 (pixel_hash 'b').
        f1b is also in the group.
        If f2 is the keeper, both f1 and f1b would be marked for deletion —
        but deleting both would remove all copies of pixel_hash 'a'.
        Master Copy protection forces one to be kept.
        """
        sid = session_factory()
        now = _now()

        # f1 and f1b share pixel_hash 'a' (exact duplicates).
        f1 = db.insert_file(sid, "/copy1.jpg", 100, now, now)
        f1b = db.insert_file(sid, "/copy1b.jpg", 100, now, now)
        db.update_pixel_hash(f1, _make_hash("a"), "/t/1.jpg")
        db.update_pixel_hash(f1b, _make_hash("a"), "/t/1b.jpg")
        db.update_perceptual_hashes_batch([
            (f1, "aaaa", 50, 50),
            (f1b, "aaaa", 50, 50),
        ])

        # f2 has pixel_hash 'b' — the "keeper" by resolution.
        f2 = db.insert_file(sid, "/better.jpg", 5000, now, now)
        db.update_pixel_hash(f2, _make_hash("b"), "/t/2.jpg")
        db.update_perceptual_hashes_batch([(f2, "aabb", 4000, 3000)])

        gid = db.create_similarity_group(sid, now, f2, member_count=3)
        db.add_similarity_group_members_batch([
            (gid, f1, 5), (gid, f1b, 5), (gid, f2, 0),
        ])

        keep, delete = apply_similarity_preset(
            db, sid, SimilarityPreset.KEEP_HIGHEST_RESOLUTION,
        )

        actions = db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}

        # f2 is the keeper (highest res).
        assert action_map[f2] == "keep"
        # Of f1 and f1b, one must be deleted and one force-kept
        # (Master Copy: can't delete ALL copies of pixel_hash 'a').
        a_actions = [action_map[f1], action_map[f1b]]
        assert "keep" in a_actions, "At least one copy of pixel_hash 'a' must survive"
        assert "delete" in a_actions, "One copy of pixel_hash 'a' should be deleted"

    def test_unique_pixel_hashes_can_be_deleted(self, db: Database, session_factory):
        """Files with unique pixel_hashes CAN be deleted in similarity groups.

        In a similarity group, each file typically has a distinct pixel_hash.
        These are near-duplicates, and the user chooses which to keep.
        Deletion of the 'worse' copies is allowed because a similar version
        (different pixel_hash) is preserved.
        """
        sid = session_factory()
        now = _now()

        f1 = db.insert_file(sid, "/lowres.jpg", 100, now, now)
        db.update_pixel_hash(f1, _make_hash("a"), "/t/1.jpg")
        db.update_perceptual_hashes_batch([(f1, "aaaa", 50, 50)])

        f2 = db.insert_file(sid, "/hires.jpg", 5000, now, now)
        db.update_pixel_hash(f2, _make_hash("b"), "/t/2.jpg")
        db.update_perceptual_hashes_batch([(f2, "aabb", 4000, 3000)])

        gid = db.create_similarity_group(sid, now, f2, member_count=2)
        db.add_similarity_group_members_batch([(gid, f1, 5), (gid, f2, 0)])

        keep, delete = apply_similarity_preset(
            db, sid, SimilarityPreset.KEEP_HIGHEST_RESOLUTION,
        )
        assert keep == 1
        assert delete == 1

        actions = db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}
        assert action_map[f2] == "keep"
        assert action_map[f1] == "delete"

    def test_returns_zero_for_empty_session(self, db: Database, session_factory):
        sid = session_factory()
        keep, delete = apply_similarity_preset(
            db, sid, SimilarityPreset.KEEP_HIGHEST_RESOLUTION,
        )
        assert keep == 0
        assert delete == 0
