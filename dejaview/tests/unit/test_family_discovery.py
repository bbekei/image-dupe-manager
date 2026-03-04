"""
tests/unit/test_family_discovery.py — Unit tests for Phase 4 Family Discovery.

Tests the FamilyTreasureModel (no Qt UI needed — QAbstractListModel is
testable without a visible window).
"""

import datetime
import sqlite3

import pytest

from data.db import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_hash(prefix: str = "a") -> str:
    """Return a valid 32-char hex pixel_hash for testing (xxh128 length)."""
    return (prefix * 32)[:32]


# ---------------------------------------------------------------------------
# Family Discovery DB integration tests
# ---------------------------------------------------------------------------

class TestFamilyDiscoveryDB:
    """Phase 4 — end-to-end DB workflows for family discovery."""

    @pytest.fixture(autouse=True)
    def _setup(self, db: Database, session_factory):
        self.db = db
        self.sid = session_factory()

        # Set up a peer with some photos
        self.peer_id = db.upsert_remote_peer("alice", _now())
        self.h_shared = _make_hash("s")
        self.h_treasure1 = _make_hash("t")
        self.h_treasure2 = _make_hash("u")

        # Local file shares hash with peer
        fid = db.insert_file(self.sid, "/local/shared.jpg", 1000, _now(), _now())
        db.update_pixel_hash(fid, self.h_shared, "/thumbs/s.jpg")

        # Peer has the shared file plus two treasures
        db.insert_remote_files(self.peer_id, [
            {"pixel_hash": self.h_shared, "filename": "shared.jpg", "size": 1000},
            {"pixel_hash": self.h_treasure1, "filename": "treasure1.jpg", "size": 2000},
            {"pixel_hash": self.h_treasure2, "filename": "treasure2.jpg", "size": 3000},
        ])

    def test_family_treasures_returns_only_unshared(self):
        treasures = self.db.get_family_treasures(self.sid)
        hashes = {t["pixel_hash"] for t in treasures}
        assert self.h_shared not in hashes
        assert self.h_treasure1 in hashes
        assert self.h_treasure2 in hashes

    def test_request_workflow(self):
        """Create request → check count → cancel → count drops."""
        rid = self.db.create_request(
            self.sid, self.h_treasure1, "alice", _now()
        )
        assert self.db.get_pending_requests_count(self.sid) == 1
        assert self.db.is_requested(self.sid, self.h_treasure1, "alice")

        self.db.cancel_request(rid)
        assert self.db.get_pending_requests_count(self.sid) == 0
        assert not self.db.is_requested(self.sid, self.h_treasure1, "alice")

    def test_request_toggle_via_delete(self):
        """Create → delete → recreate (heart toggle workflow)."""
        self.db.create_request(self.sid, self.h_treasure1, "alice", _now())
        assert self.db.is_requested(self.sid, self.h_treasure1, "alice")

        self.db.delete_request(self.sid, self.h_treasure1, "alice")
        assert not self.db.is_requested(self.sid, self.h_treasure1, "alice")

        # Recreate should work (no unique constraint violation)
        self.db.create_request(self.sid, self.h_treasure1, "alice", _now())
        assert self.db.is_requested(self.sid, self.h_treasure1, "alice")

    def test_batch_request(self):
        """Batch request multiple treasures at once."""
        now = _now()
        batch = [
            (self.sid, self.h_treasure1, "alice", now),
            (self.sid, self.h_treasure2, "alice", now),
        ]
        self.db.create_requests_batch(batch)
        assert self.db.get_pending_requests_count(self.sid) == 2

    def test_pending_review_excludes_cancelled(self):
        """get_pending_requests_for_review only shows pending."""
        self.db.create_request(self.sid, self.h_treasure1, "alice", _now())
        rid2 = self.db.create_request(
            self.sid, self.h_treasure2, "alice", _now()
        )
        self.db.cancel_request(rid2)

        rows = self.db.get_pending_requests_for_review(self.sid)
        assert len(rows) == 1
        assert rows[0]["pixel_hash"] == self.h_treasure1

    def test_multiple_peers(self):
        """Requests can target different peers."""
        peer2 = self.db.upsert_remote_peer("bob", _now())
        h_bob = _make_hash("b")
        self.db.insert_remote_files(peer2, [
            {"pixel_hash": h_bob, "filename": "bob.jpg", "size": 500},
        ])

        self.db.create_request(self.sid, self.h_treasure1, "alice", _now())
        self.db.create_request(self.sid, h_bob, "bob", _now())

        assert self.db.get_pending_requests_count(self.sid) == 2
        assert self.db.is_requested(self.sid, self.h_treasure1, "alice")
        assert self.db.is_requested(self.sid, h_bob, "bob")

    def test_family_treasure_count_matches_treasures(self):
        """get_family_treasure_count should match len(get_family_treasures)."""
        count = self.db.get_family_treasure_count(self.sid)
        treasures = self.db.get_family_treasures(self.sid)
        assert count == len(treasures)
