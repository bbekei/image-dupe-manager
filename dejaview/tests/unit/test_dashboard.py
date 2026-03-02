"""
tests/unit/test_dashboard.py — Tests for Dashboard widget and DB integration.
"""

import datetime

import pytest

from data.db import Database


class TestFamilyTreasureCount:
    """Tests for db.get_family_treasure_count()."""

    def test_no_remote_files(self, db, session_factory):
        sid = session_factory()
        assert db.get_family_treasure_count(sid) == 0

    def test_all_remote_hashes_also_local(self, db, session_factory):
        sid = session_factory()
        # Add a local file with a hash
        db.conn.execute(
            "INSERT INTO files (session_id, path, pixel_hash, status) "
            "VALUES (?, ?, ?, ?)",
            (sid, "/photos/a.jpg", "aabb" * 8, "active"),
        )
        # Add a remote peer with the same hash
        db.conn.execute(
            "INSERT INTO remote_peers (username) VALUES (?)", ("bob",)
        )
        peer_id = db.conn.execute(
            "SELECT id FROM remote_peers WHERE username='bob'"
        ).fetchone()["id"]
        db.conn.execute(
            "INSERT INTO remote_files (peer_id, pixel_hash) VALUES (?, ?)",
            (peer_id, "aabb" * 8),
        )
        db.conn.commit()
        # All remote hashes exist locally — 0 treasures
        assert db.get_family_treasure_count(sid) == 0

    def test_remote_hashes_not_local(self, db, session_factory):
        sid = session_factory()
        # Add a local file with hash A
        db.conn.execute(
            "INSERT INTO files (session_id, path, pixel_hash, status) "
            "VALUES (?, ?, ?, ?)",
            (sid, "/photos/a.jpg", "aaaa" * 8, "active"),
        )
        # Add remote peer with hashes A and B
        db.conn.execute(
            "INSERT INTO remote_peers (username) VALUES (?)", ("bob",)
        )
        peer_id = db.conn.execute(
            "SELECT id FROM remote_peers WHERE username='bob'"
        ).fetchone()["id"]
        db.conn.execute(
            "INSERT INTO remote_files (peer_id, pixel_hash) VALUES (?, ?)",
            (peer_id, "aaaa" * 8),  # exists locally
        )
        db.conn.execute(
            "INSERT INTO remote_files (peer_id, pixel_hash) VALUES (?, ?)",
            (peer_id, "bbbb" * 8),  # NOT local — this is a treasure
        )
        db.conn.commit()
        assert db.get_family_treasure_count(sid) == 1

    def test_multiple_remote_peers(self, db, session_factory):
        sid = session_factory()
        # No local files at all
        for name in ("bob", "alice"):
            db.conn.execute(
                "INSERT INTO remote_peers (username) VALUES (?)", (name,)
            )
        bob_id = db.conn.execute(
            "SELECT id FROM remote_peers WHERE username='bob'"
        ).fetchone()["id"]
        alice_id = db.conn.execute(
            "SELECT id FROM remote_peers WHERE username='alice'"
        ).fetchone()["id"]
        # Bob has hash A, Alice has hash A and B
        db.conn.execute(
            "INSERT INTO remote_files (peer_id, pixel_hash) VALUES (?, ?)",
            (bob_id, "aaaa" * 8),
        )
        db.conn.execute(
            "INSERT INTO remote_files (peer_id, pixel_hash) VALUES (?, ?)",
            (alice_id, "aaaa" * 8),
        )
        db.conn.execute(
            "INSERT INTO remote_files (peer_id, pixel_hash) VALUES (?, ?)",
            (alice_id, "bbbb" * 8),
        )
        db.conn.commit()
        # Distinct hashes: A and B, both not local → 2 treasures
        assert db.get_family_treasure_count(sid) == 2

    def test_deleted_local_files_not_counted(self, db, session_factory):
        sid = session_factory()
        # A local file exists but is 'deleted' status
        db.conn.execute(
            "INSERT INTO files (session_id, path, pixel_hash, status) "
            "VALUES (?, ?, ?, ?)",
            (sid, "/photos/a.jpg", "aaaa" * 8, "deleted"),
        )
        # Remote peer has the same hash
        db.conn.execute(
            "INSERT INTO remote_peers (username) VALUES (?)", ("bob",)
        )
        peer_id = db.conn.execute(
            "SELECT id FROM remote_peers WHERE username='bob'"
        ).fetchone()["id"]
        db.conn.execute(
            "INSERT INTO remote_files (peer_id, pixel_hash) VALUES (?, ?)",
            (peer_id, "aaaa" * 8),
        )
        db.conn.commit()
        # Local file is deleted, so remote hash is a treasure
        assert db.get_family_treasure_count(sid) == 1
