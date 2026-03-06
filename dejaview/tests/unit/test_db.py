"""
tests/unit/test_db.py — Unit tests for data/db.py.

Plan reference: §Unit Tests: data/db.py.
"""

import datetime
import sqlite3

import pytest

from data.db import Database, validate_pixel_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_hash(prefix: str = "a") -> str:
    """Return a valid 32-char hex pixel_hash for testing (xxh128 length)."""
    return (prefix * 32)[:32]


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchema:
    """Plan §Unit Tests: data/db.py — Schema."""

    def test_all_tables_created_on_open(self, db: Database):
        """All expected tables must exist after open()."""
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {r["name"] for r in cur.fetchall()}
        expected = {
            "sessions", "session_folders", "files",
            "sync_config", "remote_peers", "remote_files",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_all_indexes_created(self, db: Database):
        """All plan-specified indexes must exist."""
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = {r["name"] for r in cur.fetchall()}
        expected = {
            "idx_files_session", "idx_files_hash", "idx_files_path",
            "idx_files_status", "idx_remote_files_hash",
        }
        assert expected.issubset(indexes), f"Missing indexes: {expected - indexes}"

    def test_duplicate_groups_view_exists(self, db: Database):
        """duplicate_groups view must be queryable without error."""
        db.conn.execute("SELECT * FROM duplicate_groups LIMIT 1").fetchall()

    def test_wal_mode_enabled(self, db: Database):
        """WAL journal mode must be active (plan §Database Schema)."""
        row = db.conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_foreign_keys_enabled(self, db: Database):
        row = db.conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

class TestSessionCRUD:
    """Plan §Session CRUD tests."""

    def test_create_session_returns_id(self, db: Database):
        sid = db.create_session("My Session", _now())
        assert isinstance(sid, int)
        assert sid > 0

    def test_session_status_defaults_to_in_progress(self, db: Database):
        sid = db.create_session("Test", _now())
        row = db.get_session(sid)
        assert row["status"] == "in_progress"

    def test_update_session_status_to_paused(self, db: Database):
        sid = db.create_session("Test", _now())
        db.update_session_status(sid, "paused")
        assert db.get_session(sid)["status"] == "paused"

    def test_update_session_status_to_complete(self, db: Database):
        sid = db.create_session("Test", _now())
        db.update_session_status(sid, "complete")
        assert db.get_session(sid)["status"] == "complete"

    def test_delete_session_cascades_to_files_and_folders(self, db: Database):
        """ON DELETE CASCADE must remove child rows (plan §test_delete_session...)."""
        sid = db.create_session("Cascade Test", _now())
        db.add_session_folder(sid, "/tmp/photos")
        db.insert_file(sid, "/tmp/photos/a.jpg", 1000, _now(), _now())
        db.delete_session(sid)
        # Session gone
        assert db.get_session(sid) is None
        # Child rows gone
        folders = db.get_session_folders(sid)
        assert folders == []
        files = db.get_files_for_session(sid)
        assert files == []

    def test_get_latest_session(self, db: Database):
        db.create_session("First", _now())
        sid2 = db.create_session("Second", _now())
        row = db.get_latest_session()
        assert row["id"] == sid2


# ---------------------------------------------------------------------------
# Session folders
# ---------------------------------------------------------------------------

class TestSessionFolders:
    def test_add_session_folder(self, db: Database, session_factory):
        sid = session_factory()
        db.add_session_folder(sid, "/tmp/photos")
        assert "/tmp/photos" in db.get_session_folders(sid)

    def test_add_duplicate_folder_is_idempotent(self, db: Database, session_factory):
        sid = session_factory()
        db.add_session_folder(sid, "/tmp/photos")
        db.add_session_folder(sid, "/tmp/photos")  # should not raise
        assert db.get_session_folders(sid).count("/tmp/photos") == 1

    def test_remove_session_folder(self, db: Database, session_factory):
        sid = session_factory()
        db.add_session_folder(sid, "/tmp/photos")
        db.remove_session_folder(sid, "/tmp/photos")
        assert "/tmp/photos" not in db.get_session_folders(sid)


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

class TestFileOperations:
    """Plan §File operations tests."""

    def test_insert_file_row(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/photos/a.jpg", 1024, _now(), _now())
        row = db.get_file(fid)
        assert row["path"] == "/photos/a.jpg"
        assert row["size"] == 1024
        assert row["pixel_hash"] is None
        assert row["status"] == "active"

    def test_upsert_on_duplicate_session_path_pair(self, db: Database, session_factory):
        """Inserting same (session_id, path) twice must not raise (plan §test_upsert...)."""
        sid = session_factory()
        fid1 = db.insert_file(sid, "/photos/a.jpg", 1024, _now(), _now())
        fid2 = db.insert_file(sid, "/photos/a.jpg", 1024, _now(), _now())
        assert fid1 == fid2  # same row returned

    def test_update_pixel_hash(self, db: Database, session_factory, thumb_dir):
        sid = session_factory()
        fid = db.insert_file(sid, "/photos/a.jpg", 1024, _now(), _now())
        h = _make_hash("a")
        thumb = str(thumb_dir / f"{h}.jpg")
        db.update_pixel_hash(fid, h, thumb)
        row = db.get_file(fid)
        assert row["pixel_hash"] == h
        assert row["thumbnail_path"] == thumb

    def test_files_with_null_hash_not_in_duplicate_groups(
        self, db: Database, session_factory
    ):
        """Files without pixel_hash must not appear in duplicate_groups view."""
        sid = session_factory()
        db.insert_file(sid, "/photos/a.jpg", 1000, _now(), _now())
        db.insert_file(sid, "/photos/b.jpg", 1000, _now(), _now())
        groups = db.get_duplicate_groups(sid)
        assert len(groups) == 0

    def test_duplicate_groups_view_counts_correctly(
        self, db: Database, session_factory, thumb_dir
    ):
        """Plan §test_duplicate_groups_view_counts_correctly."""
        sid = session_factory()
        h = _make_hash("f")
        thumb = str(thumb_dir / f"{h}.jpg")
        for path in ["/a.jpg", "/b.jpg", "/c.jpg"]:
            fid = db.insert_file(sid, path, 1000, _now(), _now())
            db.update_pixel_hash(fid, h, thumb)

        groups = db.get_duplicate_groups(sid)
        assert len(groups) == 1
        assert groups[0]["file_count"] == 3

        # Mark one deleted → count drops to 2
        rows = db.get_files_for_session(sid)
        db.update_file_status(rows[0]["id"], "deleted")
        groups = db.get_duplicate_groups(sid)
        assert groups[0]["file_count"] == 2

    def test_files_with_unique_size_not_hashed_by_view_contract(
        self, db: Database, session_factory, thumb_dir
    ):
        """
        The duplicate_groups view only reports pixel_hash groups with count > 1.
        A file that hash-collides but is the only one with that hash is not shown.
        """
        sid = session_factory()
        h = _make_hash("b")
        thumb = str(thumb_dir / f"{h}.jpg")
        fid = db.insert_file(sid, "/solo.jpg", 1000, _now(), _now())
        db.update_pixel_hash(fid, h, thumb)
        groups = db.get_duplicate_groups(sid)
        assert len(groups) == 0

    def test_get_unhashed_files_grouped_by_size(
        self, db: Database, session_factory
    ):
        """Only files sharing a size with another file should be returned."""
        sid = session_factory()
        # Two files with size 1000 — should be returned (candidates)
        db.insert_file(sid, "/a.jpg", 1000, _now(), _now())
        db.insert_file(sid, "/b.jpg", 1000, _now(), _now())
        # One file with unique size — should NOT be returned
        db.insert_file(sid, "/c.jpg", 9999, _now(), _now())

        candidates = db.get_unhashed_files_grouped_by_size(sid)
        paths = [r["path"] for r in candidates]
        assert "/a.jpg" in paths
        assert "/b.jpg" in paths
        assert "/c.jpg" not in paths

    def test_update_file_status(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/x.jpg", 500, _now(), _now())
        db.update_file_status(fid, "deleted")
        assert db.get_file(fid)["status"] == "deleted"

    def test_insert_files_batch(self, db: Database, session_factory):
        sid = session_factory()
        now = _now()
        rows = [(sid, f"/img_{i}.jpg", 100 * i, now, now) for i in range(5)]
        db.insert_files_batch(rows)
        files = db.get_files_for_session(sid)
        assert len(files) == 5

    def test_update_pixel_hashes_batch(self, db: Database, session_factory, thumb_dir):
        """Batch update writes pixel_hash and thumbnail_path for multiple files."""
        sid = session_factory()
        fids = []
        for i in range(4):
            fid = db.insert_file(sid, f"/batch_{i}.jpg", 1000, _now(), _now())
            fids.append(fid)

        updates = []
        for i, fid in enumerate(fids):
            h = _make_hash(str(i))
            thumb = str(thumb_dir / f"{h}.jpg")
            updates.append((fid, h, thumb))

        db.update_pixel_hashes_batch(updates)

        for fid, expected_hash, expected_thumb in updates:
            row = db.get_file(fid)
            assert row["pixel_hash"] == expected_hash
            assert row["thumbnail_path"] == expected_thumb

    def test_get_all_duplicate_file_ids(self, db: Database, session_factory, thumb_dir):
        """Bulk duplicate query returns grouped IDs; singletons excluded."""
        sid = session_factory()
        hash_a = _make_hash("a")
        hash_b = _make_hash("b")
        hash_c = _make_hash("c")

        # Two files with hash_a (duplicate pair)
        id1 = db.insert_file(sid, "/x/1.jpg", 100, _now(), _now())
        db.update_pixel_hash(id1, hash_a, str(thumb_dir / "a.jpg"))
        id2 = db.insert_file(sid, "/x/2.jpg", 100, _now(), _now())
        db.update_pixel_hash(id2, hash_a, str(thumb_dir / "a.jpg"))

        # Two files with hash_b (duplicate pair)
        id3 = db.insert_file(sid, "/x/3.jpg", 200, _now(), _now())
        db.update_pixel_hash(id3, hash_b, str(thumb_dir / "b.jpg"))
        id4 = db.insert_file(sid, "/x/4.jpg", 200, _now(), _now())
        db.update_pixel_hash(id4, hash_b, str(thumb_dir / "b.jpg"))

        # One file with hash_c (singleton — must be excluded)
        id5 = db.insert_file(sid, "/x/5.jpg", 300, _now(), _now())
        db.update_pixel_hash(id5, hash_c, str(thumb_dir / "c.jpg"))

        groups = db.get_all_duplicate_file_ids(sid)
        assert hash_a in groups
        assert hash_b in groups
        assert hash_c not in groups
        assert set(groups[hash_a]) == {id1, id2}
        assert set(groups[hash_b]) == {id3, id4}

    def test_get_all_duplicate_file_ids_excludes_deleted(
        self, db: Database, session_factory, thumb_dir
    ):
        """Deleted files must not appear in bulk duplicate results."""
        sid = session_factory()
        h = _make_hash("d")
        id1 = db.insert_file(sid, "/y/1.jpg", 100, _now(), _now())
        db.update_pixel_hash(id1, h, str(thumb_dir / "d.jpg"))
        id2 = db.insert_file(sid, "/y/2.jpg", 100, _now(), _now())
        db.update_pixel_hash(id2, h, str(thumb_dir / "d.jpg"))

        # Delete one → group drops below 2 → excluded
        db.update_file_status(id1, "deleted")
        groups = db.get_all_duplicate_file_ids(sid)
        assert h not in groups


# ---------------------------------------------------------------------------
# Sync config
# ---------------------------------------------------------------------------

class TestSyncConfig:
    """Plan §Sharing tables tests — sync_config."""

    def test_insert_sync_config_singleton(self, db: Database):
        db.upsert_sync_config(local_username="alice", sync_enabled=0)
        row = db.get_sync_config()
        assert row is not None
        assert row["local_username"] == "alice"

    def test_update_sync_config(self, db: Database):
        db.upsert_sync_config(local_username="alice")
        db.upsert_sync_config(local_username="bob")
        row = db.get_sync_config()
        assert row["local_username"] == "bob"

    def test_sync_config_singleton_constraint(self, db: Database):
        """Only one row (id=1) must ever exist."""
        db.upsert_sync_config(local_username="alice")
        db.upsert_sync_config(local_username="bob")
        count = db.conn.execute("SELECT COUNT(*) FROM sync_config").fetchone()[0]
        assert count == 1

    def test_get_scan_delay_ms_default(self, db: Database):
        """Returns 0 if no sync_config row exists."""
        assert db.get_scan_delay_ms() == 0


# ---------------------------------------------------------------------------
# Remote peers and remote files
# ---------------------------------------------------------------------------

class TestRemotePeers:
    """Plan §Sharing tables tests — remote_peers / remote_files."""

    def test_insert_remote_peer(self, db: Database):
        uid = db.upsert_remote_peer("alice", _now())
        assert isinstance(uid, int)
        peer = db.get_remote_peer("alice")
        assert peer["username"] == "alice"

    def test_upsert_remote_peer_is_idempotent(self, db: Database):
        db.upsert_remote_peer("alice", _now())
        db.upsert_remote_peer("alice", _now())
        count = db.conn.execute(
            "SELECT COUNT(*) FROM remote_peers WHERE username='alice'"
        ).fetchone()[0]
        assert count == 1

    def test_insert_remote_files_for_peer(self, db: Database):
        peer_id = db.upsert_remote_peer("alice", _now())
        h = _make_hash("c")
        db.insert_remote_files(
            peer_id, [{"pixel_hash": h, "filename": "beach.jpg", "size": 2000}]
        )
        rows = db.conn.execute(
            "SELECT * FROM remote_files WHERE peer_id = ?", (peer_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["pixel_hash"] == h

    def test_delete_peer_cascades_to_remote_files(self, db: Database):
        """Plan §test_delete_peer_cascades_to_remote_files."""
        peer_id = db.upsert_remote_peer("alice", _now())
        h = _make_hash("d")
        db.insert_remote_files(peer_id, [{"pixel_hash": h}] * 3)
        db.delete_remote_peer("alice")
        count = db.conn.execute(
            "SELECT COUNT(*) FROM remote_files WHERE peer_id = ?", (peer_id,)
        ).fetchone()[0]
        assert count == 0


# ---------------------------------------------------------------------------
# Cross-library JOIN
# ---------------------------------------------------------------------------

class TestCrossLibraryJoin:
    """Plan §test_cross_library_join_query_returns_matching_files."""

    def test_cross_library_join_returns_matching_file(
        self, db: Database, session_factory, thumb_dir
    ):
        sid = session_factory()
        h = _make_hash("e")
        thumb = str(thumb_dir / f"{h}.jpg")
        fid = db.insert_file(sid, "/local/photo.jpg", 1000, _now(), _now())
        db.update_pixel_hash(fid, h, thumb)

        peer_id = db.upsert_remote_peer("alice", _now())
        db.insert_remote_files(
            peer_id, [{"pixel_hash": h, "filename": "alice_photo.jpg"}]
        )

        matches = db.get_cross_library_matches(sid)
        assert len(matches) == 1
        assert matches[0]["local_path"] == "/local/photo.jpg"
        assert matches[0]["username"] == "alice"

    def test_no_cross_library_match_for_different_hash(
        self, db: Database, session_factory, thumb_dir
    ):
        sid = session_factory()
        h_local = _make_hash("1")
        h_remote = _make_hash("2")
        thumb = str(thumb_dir / f"{h_local}.jpg")
        fid = db.insert_file(sid, "/local/photo.jpg", 1000, _now(), _now())
        db.update_pixel_hash(fid, h_local, thumb)

        peer_id = db.upsert_remote_peer("bob", _now())
        db.insert_remote_files(peer_id, [{"pixel_hash": h_remote}])

        matches = db.get_cross_library_matches(sid)
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# Thumbnail cleanup (orphan detection)
# ---------------------------------------------------------------------------

class TestThumbnailCleanup:
    """Plan §Post-Action Cleanup — cleanup_orphaned_thumbnails."""

    def test_cleanup_returns_orphaned_thumbnail(
        self, db: Database, session_factory, thumb_dir
    ):
        sid = session_factory()
        h = _make_hash("9")
        thumb = str(thumb_dir / f"{h}.jpg")
        fid = db.insert_file(sid, "/x.jpg", 100, _now(), _now())
        db.update_pixel_hash(fid, h, thumb)
        db.update_file_status(fid, "deleted")

        orphans = db.cleanup_orphaned_thumbnails()
        assert thumb in orphans

    def test_cleanup_does_not_return_active_thumbnail(
        self, db: Database, session_factory, thumb_dir
    ):
        sid = session_factory()
        h = _make_hash("8")
        thumb = str(thumb_dir / f"{h}.jpg")
        fid = db.insert_file(sid, "/x.jpg", 100, _now(), _now())
        db.update_pixel_hash(fid, h, thumb)
        # Still active — no orphan
        orphans = db.cleanup_orphaned_thumbnails()
        assert thumb not in orphans


# ---------------------------------------------------------------------------
# validate_pixel_hash helper
# ---------------------------------------------------------------------------

class TestValidatePixelHash:
    """Plan §pixel_hash format enforcement."""

    def test_valid_sha256_hash_accepted(self):
        assert validate_pixel_hash("a" * 64) is True

    def test_valid_xxh128_hash_accepted(self):
        assert validate_pixel_hash("a" * 32) is True

    def test_hash_too_short_rejected(self):
        assert validate_pixel_hash("a" * 31) is False

    def test_hash_too_long_rejected(self):
        assert validate_pixel_hash("a" * 65) is False

    def test_hash_between_32_and_64_rejected(self):
        assert validate_pixel_hash("a" * 48) is False

    def test_uppercase_hex_rejected(self):
        assert validate_pixel_hash("A" * 32) is False

    def test_non_hex_chars_rejected(self):
        assert validate_pixel_hash("g" + "a" * 31) is False

    def test_sql_injection_attempt_rejected(self):
        assert validate_pixel_hash("'; DROP TABLE files; --" + "a" * 41) is False

    def test_empty_string_rejected(self):
        assert validate_pixel_hash("") is False

    def test_non_string_rejected(self):
        assert validate_pixel_hash(None) is False  # type: ignore[arg-type]
        assert validate_pixel_hash(123) is False   # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# hash_algorithm column (R3)
# ---------------------------------------------------------------------------

class TestHashAlgorithmColumn:
    """R3 — hash_algorithm column on files table."""

    def test_new_files_default_to_xxh128(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/photos/a.jpg", 1024, _now(), _now())
        row = db.get_file(fid)
        assert row["hash_algorithm"] == "xxh128"

    def test_update_pixel_hash_sets_xxh128_for_32_char(
        self, db: Database, session_factory, thumb_dir
    ):
        sid = session_factory()
        fid = db.insert_file(sid, "/x.jpg", 100, _now(), _now())
        h = "a" * 32
        db.update_pixel_hash(fid, h, str(thumb_dir / "a.jpg"))
        assert db.get_file(fid)["hash_algorithm"] == "xxh128"

    def test_update_pixel_hash_sets_sha256_for_64_char(
        self, db: Database, session_factory, thumb_dir
    ):
        sid = session_factory()
        fid = db.insert_file(sid, "/x.jpg", 100, _now(), _now())
        h = "a" * 64
        db.update_pixel_hash(fid, h, str(thumb_dir / "a.jpg"))
        assert db.get_file(fid)["hash_algorithm"] == "sha256"

    def test_batch_update_sets_algorithm_correctly(
        self, db: Database, session_factory, thumb_dir
    ):
        sid = session_factory()
        fid = db.insert_file(sid, "/x.jpg", 100, _now(), _now())
        h = "b" * 32
        db.update_pixel_hashes_batch([(fid, h, str(thumb_dir / "b.jpg"))])
        assert db.get_file(fid)["hash_algorithm"] == "xxh128"

    def test_duplicate_groups_scoped_by_algorithm(
        self, db: Database, session_factory, thumb_dir
    ):
        """Files with same hash value but different algorithms are NOT grouped."""
        sid = session_factory()
        # Two xxh128 files with hash "a"*32
        id1 = db.insert_file(sid, "/1.jpg", 100, _now(), _now())
        db.update_pixel_hash(id1, "a" * 32, str(thumb_dir / "a.jpg"))
        id2 = db.insert_file(sid, "/2.jpg", 100, _now(), _now())
        db.update_pixel_hash(id2, "a" * 32, str(thumb_dir / "a.jpg"))

        groups = db.get_duplicate_groups(sid)
        assert len(groups) == 1
        assert groups[0]["hash_algorithm"] == "xxh128"


# ---------------------------------------------------------------------------
# max_scan_workers (R3)
# ---------------------------------------------------------------------------

class TestMaxScanWorkers:
    """R3 — max_scan_workers in app_config."""

    def test_default_returns_zero(self, db: Database):
        assert db.get_max_scan_workers() == 0

    def test_upsert_and_read(self, db: Database):
        db.upsert_app_config(language="en", max_scan_workers=8)
        assert db.get_max_scan_workers() == 8

    def test_update_existing(self, db: Database):
        db.upsert_app_config(language="en")
        db.upsert_app_config(max_scan_workers=12)
        assert db.get_max_scan_workers() == 12


# ---------------------------------------------------------------------------
# File actions (Pluggable Views)
# ---------------------------------------------------------------------------

class TestFileActions:
    """Pluggable Views — file_actions CRUD."""

    @pytest.fixture(autouse=True)
    def _setup(self, db: Database):
        """Create a session with two files for action tests."""
        self.db = db
        self.sid = db.create_session("test", _now())
        self.fid1 = db.insert_file(self.sid, "/a/img1.jpg", 100, _now(), _now())
        self.fid2 = db.insert_file(self.sid, "/a/img2.jpg", 200, _now(), _now())

    def test_set_and_get_file_action(self):
        self.db.set_file_action(self.sid, self.fid1, "delete")
        rows = self.db.get_file_actions_for_session(self.sid)
        assert len(rows) == 1
        assert rows[0]["file_id"] == self.fid1
        assert rows[0]["action"] == "delete"
        assert rows[0]["scope"] == "file"

    def test_set_action_with_scope_and_timestamp(self):
        ts = _now()
        self.db.set_file_action(self.sid, self.fid1, "keep", scope="folder", decided_at=ts)
        rows = self.db.get_file_actions_for_session(self.sid)
        assert rows[0]["scope"] == "folder"
        assert rows[0]["decided_at"] == ts

    def test_upsert_overwrites_existing_action(self):
        self.db.set_file_action(self.sid, self.fid1, "delete")
        self.db.set_file_action(self.sid, self.fid1, "keep")
        rows = self.db.get_file_actions_for_session(self.sid)
        assert len(rows) == 1
        assert rows[0]["action"] == "keep"

    def test_set_file_actions_batch(self):
        ts = _now()
        batch = [
            (self.sid, self.fid1, "delete", "folder", ts),
            (self.sid, self.fid2, "keep", "folder", ts),
        ]
        self.db.set_file_actions_batch(batch)
        rows = self.db.get_file_actions_for_session(self.sid)
        assert len(rows) == 2
        actions = {r["file_id"]: r["action"] for r in rows}
        assert actions[self.fid1] == "delete"
        assert actions[self.fid2] == "keep"

    def test_get_decided_file_ids(self):
        self.db.set_file_action(self.sid, self.fid1, "delete")
        self.db.set_file_action(self.sid, self.fid2, "ignore")
        decided = self.db.get_decided_file_ids(self.sid)
        assert decided == {self.fid1, self.fid2}

    def test_get_decided_file_ids_empty_session(self):
        decided = self.db.get_decided_file_ids(self.sid)
        assert decided == set()

    def test_clear_file_action(self):
        self.db.set_file_action(self.sid, self.fid1, "delete")
        self.db.set_file_action(self.sid, self.fid2, "keep")
        self.db.clear_file_action(self.sid, self.fid1)
        decided = self.db.get_decided_file_ids(self.sid)
        assert decided == {self.fid2}

    def test_clear_all_actions(self):
        self.db.set_file_action(self.sid, self.fid1, "delete")
        self.db.set_file_action(self.sid, self.fid2, "keep")
        self.db.clear_all_actions(self.sid)
        assert self.db.get_decided_file_ids(self.sid) == set()
        assert self.db.get_file_actions_for_session(self.sid) == []

    def test_invalid_action_rejected(self):
        with pytest.raises(sqlite3.IntegrityError):
            self.db.set_file_action(self.sid, self.fid1, "move")

    def test_invalid_scope_rejected(self):
        with pytest.raises(sqlite3.IntegrityError):
            self.db.set_file_action(self.sid, self.fid1, "delete", scope="invalid")

    def test_cascade_deletes_on_session_delete(self):
        self.db.set_file_action(self.sid, self.fid1, "delete")
        self.db.delete_session(self.sid)
        # After session delete, file_actions should be gone too
        rows = self.db.conn.execute(
            "SELECT * FROM file_actions WHERE session_id = ?", (self.sid,)
        ).fetchall()
        assert len(rows) == 0

    def test_table_and_indexes_exist(self, db: Database):
        tables = {
            r["name"]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "file_actions" in tables
        indexes = {
            r["name"]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_file_actions_session" in indexes
        assert "idx_file_actions_file" in indexes


# ---------------------------------------------------------------------------
# Filtered duplicate groups (Phase 5)
# ---------------------------------------------------------------------------

class TestFilteredDuplicateGroups:
    """Phase 5 — get_filtered_duplicate_groups()."""

    @pytest.fixture(autouse=True)
    def _setup(self, db: Database, session_factory):
        self.db = db
        self.sid = session_factory()
        # Group A: 2 JPEG files, modified 2024-01-01
        h_a = _make_hash("a")
        for i, path in enumerate(["/photos/a1.jpg", "/photos/a2.jpg"]):
            fid = db.insert_file(self.sid, path, 1000 + i * 500, "2024-01-15", _now())
            db.update_pixel_hash(fid, h_a, f"/thumbs/{h_a}.jpg")
        # Group B: 3 HEIC files, modified 2024-06-01
        h_b = _make_hash("b")
        for i, path in enumerate(["/photos/b1.heic", "/photos/b2.heic", "/photos/b3.heic"]):
            fid = db.insert_file(self.sid, path, 2000 + i * 100, "2024-06-01", _now())
            db.update_pixel_hash(fid, h_b, f"/thumbs/{h_b}.jpg")
        self.h_a = h_a
        self.h_b = h_b

    def test_basic_query(self):
        groups = self.db.get_filtered_duplicate_groups(self.sid)
        assert len(groups) == 2

    def test_min_copies_filter(self):
        groups = self.db.get_filtered_duplicate_groups(self.sid, min_copies=3)
        assert len(groups) == 1
        assert groups[0]["pixel_hash"] == self.h_b

    def test_date_from_filter(self):
        groups = self.db.get_filtered_duplicate_groups(
            self.sid, date_from="2024-03-01"
        )
        assert len(groups) == 1
        assert groups[0]["pixel_hash"] == self.h_b

    def test_date_to_filter(self):
        groups = self.db.get_filtered_duplicate_groups(
            self.sid, date_to="2024-03-01"
        )
        assert len(groups) == 1
        assert groups[0]["pixel_hash"] == self.h_a

    def test_extension_filter_jpg(self):
        groups = self.db.get_filtered_duplicate_groups(
            self.sid, extensions=[".jpg"]
        )
        assert len(groups) == 1
        assert groups[0]["pixel_hash"] == self.h_a

    def test_extension_filter_heic(self):
        groups = self.db.get_filtered_duplicate_groups(
            self.sid, extensions=[".heic"]
        )
        assert len(groups) == 1
        assert groups[0]["pixel_hash"] == self.h_b

    def test_sort_by_copies(self):
        groups = self.db.get_filtered_duplicate_groups(
            self.sid, sort_by="copies", sort_desc=True
        )
        assert groups[0]["file_count"] >= groups[-1]["file_count"]

    def test_sort_by_waste_ascending(self):
        groups = self.db.get_filtered_duplicate_groups(
            self.sid, sort_by="waste", sort_desc=False
        )
        assert groups[0]["total_size"] <= groups[-1]["total_size"]

    def test_deleted_files_excluded(self):
        """Deleted files should not appear in filtered groups."""
        # Delete all files in group A by marking them deleted
        rows = self.db.get_cluster_files(self.sid, self.h_a)
        for r in rows:
            self.db.update_file_status(r["id"], "deleted")
        groups = self.db.get_filtered_duplicate_groups(self.sid)
        hashes = {g["pixel_hash"] for g in groups}
        assert self.h_a not in hashes

    def test_result_columns(self):
        groups = self.db.get_filtered_duplicate_groups(self.sid)
        g = groups[0]
        assert "pixel_hash" in g.keys()
        assert "file_count" in g.keys()
        assert "total_size" in g.keys()
        assert "oldest_date" in g.keys()
        assert "newest_date" in g.keys()

    def test_limit_returns_subset(self):
        groups = self.db.get_filtered_duplicate_groups(self.sid, limit=1)
        assert len(groups) == 1

    def test_limit_zero_returns_all(self):
        groups = self.db.get_filtered_duplicate_groups(self.sid, limit=0)
        assert len(groups) == 2

    def test_offset_skips_rows(self):
        all_groups = self.db.get_filtered_duplicate_groups(self.sid)
        page2 = self.db.get_filtered_duplicate_groups(self.sid, limit=1, offset=1)
        assert len(page2) == 1
        assert page2[0]["pixel_hash"] == all_groups[1]["pixel_hash"]

    def test_offset_beyond_end_returns_empty(self):
        groups = self.db.get_filtered_duplicate_groups(self.sid, limit=10, offset=100)
        assert len(groups) == 0

    def test_get_duplicate_group_count(self):
        count = self.db.get_duplicate_group_count(self.sid)
        assert count == 2

    def test_get_duplicate_group_count_with_min_copies(self):
        count = self.db.get_duplicate_group_count(self.sid, min_copies=3)
        assert count == 1

    def test_get_duplicate_group_count_with_date_filter(self):
        count = self.db.get_duplicate_group_count(self.sid, date_from="2024-03-01")
        assert count == 1


# ---------------------------------------------------------------------------
# Cluster files (Phase 5)
# ---------------------------------------------------------------------------

class TestClusterFiles:
    """Phase 5 — get_cluster_files()."""

    def test_returns_files_for_hash(self, db: Database, session_factory):
        sid = session_factory()
        h = _make_hash("c")
        f1 = db.insert_file(sid, "/a.jpg", 500, "2024-01-01", _now())
        db.update_pixel_hash(f1, h, "/thumbs/c.jpg")
        f2 = db.insert_file(sid, "/b.jpg", 1000, "2024-01-01", _now())
        db.update_pixel_hash(f2, h, "/thumbs/c.jpg")

        rows = db.get_cluster_files(sid, h)
        assert len(rows) == 2
        # Ordered by size DESC
        assert rows[0]["size"] >= rows[1]["size"]

    def test_excludes_deleted(self, db: Database, session_factory):
        sid = session_factory()
        h = _make_hash("d")
        f1 = db.insert_file(sid, "/a.jpg", 500, "2024-01-01", _now())
        db.update_pixel_hash(f1, h, "/thumbs/d.jpg")
        f2 = db.insert_file(sid, "/b.jpg", 1000, "2024-01-01", _now())
        db.update_pixel_hash(f2, h, "/thumbs/d.jpg")
        db.update_file_status(f1, "deleted")

        rows = db.get_cluster_files(sid, h)
        assert len(rows) == 1
        assert rows[0]["id"] == f2

    def test_empty_for_unknown_hash(self, db: Database, session_factory):
        sid = session_factory()
        rows = db.get_cluster_files(sid, _make_hash("z"))
        assert rows == []

    def test_result_columns(self, db: Database, session_factory):
        sid = session_factory()
        h = _make_hash("e")
        fid = db.insert_file(sid, "/x.jpg", 100, "2024-01-01", _now())
        db.update_pixel_hash(fid, h, "/thumbs/e.jpg")
        # Need at least 2 to form a group, but get_cluster_files doesn't require it
        rows = db.get_cluster_files(sid, h)
        assert len(rows) == 1
        r = rows[0]
        assert "id" in r.keys()
        assert "path" in r.keys()
        assert "size" in r.keys()
        assert "modified_at" in r.keys()
        assert "thumbnail_path" in r.keys()


# ---------------------------------------------------------------------------
# Full dupe folder paths (Phase 5)
# ---------------------------------------------------------------------------

class TestFullDupeFolderPaths:
    """Phase 5 — get_full_dupe_folder_paths()."""

    def test_fully_duplicated_folder(self, db: Database, session_factory):
        sid = session_factory()
        h1 = _make_hash("1")
        h2 = _make_hash("2")
        # Folder /photos has 2 files, both duplicates
        f1 = db.insert_file(sid, "/photos/a.jpg", 100, "2024-01-01", _now())
        db.update_pixel_hash(f1, h1, "/t/1.jpg")
        f2 = db.insert_file(sid, "/photos/b.jpg", 200, "2024-01-01", _now())
        db.update_pixel_hash(f2, h2, "/t/2.jpg")
        # Duplicates live elsewhere
        f3 = db.insert_file(sid, "/backup/a.jpg", 100, "2024-01-01", _now())
        db.update_pixel_hash(f3, h1, "/t/1.jpg")
        f4 = db.insert_file(sid, "/backup/b.jpg", 200, "2024-01-01", _now())
        db.update_pixel_hash(f4, h2, "/t/2.jpg")

        paths = db.get_full_dupe_folder_paths(sid)
        # Both /photos and /backup are fully duplicated
        assert len(paths) == 2

    def test_partially_duplicated_folder_excluded(self, db: Database, session_factory):
        sid = session_factory()
        h = _make_hash("1")
        # /photos has 2 files: one dupe, one unique
        f1 = db.insert_file(sid, "/photos/dupe.jpg", 100, "2024-01-01", _now())
        db.update_pixel_hash(f1, h, "/t/1.jpg")
        f2 = db.insert_file(sid, "/photos/unique.jpg", 200, "2024-01-01", _now())
        db.update_pixel_hash(f2, _make_hash("u"), "/t/u.jpg")  # unique hash
        # Dupe copy elsewhere
        f3 = db.insert_file(sid, "/backup/dupe.jpg", 100, "2024-01-01", _now())
        db.update_pixel_hash(f3, h, "/t/1.jpg")

        paths = db.get_full_dupe_folder_paths(sid)
        # /photos has a unique file, so it's NOT full dupe
        # /backup has only one file and it IS a dupe → full dupe
        assert "/photos" not in {p.replace("\\", "/") for p in paths}

    def test_empty_session(self, db: Database, session_factory):
        sid = session_factory()
        paths = db.get_full_dupe_folder_paths(sid)
        assert paths == set()

    def test_no_duplicates(self, db: Database, session_factory):
        sid = session_factory()
        # All files have unique hashes → no duplicates → no full dupe folders
        for i in range(3):
            h = _make_hash(str(i))
            fid = db.insert_file(sid, f"/photos/img{i}.jpg", 100, "2024-01-01", _now())
            db.update_pixel_hash(fid, h, f"/t/{i}.jpg")

        paths = db.get_full_dupe_folder_paths(sid)
        assert paths == set()


# ---------------------------------------------------------------------------
# Requests (Phase 4 — Family Discovery)
# ---------------------------------------------------------------------------

class TestRequests:
    """Phase 4 — requests table CRUD."""

    @pytest.fixture(autouse=True)
    def _setup(self, db: Database, session_factory):
        self.db = db
        self.sid = session_factory()

    def test_requests_table_exists(self):
        tables = {
            r["name"]
            for r in self.db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "requests" in tables

    def test_requests_indexes_exist(self):
        indexes = {
            r["name"]
            for r in self.db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_requests_session" in indexes
        assert "idx_requests_status" in indexes

    def test_create_request_returns_id(self):
        rid = self.db.create_request(
            self.sid, _make_hash("a"), "alice", _now()
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_create_request_is_idempotent(self):
        h = _make_hash("a")
        rid1 = self.db.create_request(self.sid, h, "alice", _now())
        rid2 = self.db.create_request(self.sid, h, "alice", _now())
        assert rid1 == rid2

    def test_create_request_different_peer(self):
        h = _make_hash("a")
        rid1 = self.db.create_request(self.sid, h, "alice", _now())
        rid2 = self.db.create_request(self.sid, h, "bob", _now())
        assert rid1 != rid2

    def test_get_requests_for_session(self):
        self.db.create_request(self.sid, _make_hash("a"), "alice", _now())
        self.db.create_request(self.sid, _make_hash("b"), "bob", _now())
        rows = self.db.get_requests_for_session(self.sid)
        assert len(rows) == 2

    def test_get_pending_requests_count(self):
        self.db.create_request(self.sid, _make_hash("a"), "alice", _now())
        self.db.create_request(self.sid, _make_hash("b"), "bob", _now())
        assert self.db.get_pending_requests_count(self.sid) == 2

    def test_update_request_status(self):
        rid = self.db.create_request(self.sid, _make_hash("a"), "alice", _now())
        self.db.update_request_status(rid, "approved", responded_at=_now())
        rows = self.db.get_requests_for_session(self.sid)
        assert rows[0]["status"] == "approved"
        assert rows[0]["responded_at"] is not None

    def test_cancel_request(self):
        rid = self.db.create_request(self.sid, _make_hash("a"), "alice", _now())
        self.db.cancel_request(rid)
        assert self.db.get_pending_requests_count(self.sid) == 0
        rows = self.db.get_requests_for_session(self.sid)
        assert rows[0]["status"] == "cancelled"

    def test_delete_request(self):
        h = _make_hash("a")
        self.db.create_request(self.sid, h, "alice", _now())
        self.db.delete_request(self.sid, h, "alice")
        assert self.db.get_requests_for_session(self.sid) == []

    def test_is_requested_true(self):
        h = _make_hash("a")
        self.db.create_request(self.sid, h, "alice", _now())
        assert self.db.is_requested(self.sid, h, "alice") is True

    def test_is_requested_false_when_not_exists(self):
        assert self.db.is_requested(self.sid, _make_hash("z"), "alice") is False

    def test_is_requested_false_when_cancelled(self):
        h = _make_hash("a")
        rid = self.db.create_request(self.sid, h, "alice", _now())
        self.db.cancel_request(rid)
        assert self.db.is_requested(self.sid, h, "alice") is False

    def test_create_requests_batch(self):
        now = _now()
        batch = [
            (self.sid, _make_hash("a"), "alice", now),
            (self.sid, _make_hash("b"), "bob", now),
            (self.sid, _make_hash("c"), "alice", now),
        ]
        self.db.create_requests_batch(batch)
        assert self.db.get_pending_requests_count(self.sid) == 3

    def test_get_pending_requests_for_review(self):
        self.db.create_request(self.sid, _make_hash("a"), "alice", _now())
        rid2 = self.db.create_request(self.sid, _make_hash("b"), "bob", _now())
        self.db.cancel_request(rid2)
        rows = self.db.get_pending_requests_for_review(self.sid)
        assert len(rows) == 1
        assert rows[0]["target_peer"] == "alice"

    def test_cascade_on_session_delete(self):
        self.db.create_request(self.sid, _make_hash("a"), "alice", _now())
        self.db.delete_session(self.sid)
        rows = self.db.conn.execute(
            "SELECT * FROM requests WHERE session_id = ?", (self.sid,)
        ).fetchall()
        assert len(rows) == 0

    def test_invalid_status_rejected(self):
        rid = self.db.create_request(self.sid, _make_hash("a"), "alice", _now())
        with pytest.raises(sqlite3.IntegrityError):
            self.db.update_request_status(rid, "invalid_status")


class TestFamilyTreasures:
    """Phase 4 — get_family_treasures()."""

    def test_returns_remote_only_files(self, db: Database, session_factory):
        sid = session_factory()
        # Local file with hash_a
        h_local = _make_hash("a")
        fid = db.insert_file(sid, "/local/photo.jpg", 1000, _now(), _now())
        db.update_pixel_hash(fid, h_local, "/t/a.jpg")

        # Remote peer has hash_a (shared) + hash_b (treasure)
        h_treasure = _make_hash("b")
        peer_id = db.upsert_remote_peer("alice", _now())
        db.insert_remote_files(peer_id, [
            {"pixel_hash": h_local, "filename": "shared.jpg", "size": 1000},
            {"pixel_hash": h_treasure, "filename": "treasure.jpg", "size": 2000},
        ])

        treasures = db.get_family_treasures(sid)
        assert len(treasures) == 1
        assert treasures[0]["pixel_hash"] == h_treasure
        assert treasures[0]["peer_username"] == "alice"

    def test_empty_when_all_shared(self, db: Database, session_factory):
        sid = session_factory()
        h = _make_hash("a")
        fid = db.insert_file(sid, "/local/photo.jpg", 1000, _now(), _now())
        db.update_pixel_hash(fid, h, "/t/a.jpg")

        peer_id = db.upsert_remote_peer("alice", _now())
        db.insert_remote_files(peer_id, [
            {"pixel_hash": h, "filename": "same.jpg", "size": 1000},
        ])

        treasures = db.get_family_treasures(sid)
        assert len(treasures) == 0

    def test_multiple_peers_treasures(self, db: Database, session_factory):
        sid = session_factory()
        h1 = _make_hash("x")
        h2 = _make_hash("y")

        peer1 = db.upsert_remote_peer("alice", _now())
        db.insert_remote_files(peer1, [
            {"pixel_hash": h1, "filename": "a.jpg", "size": 1000},
        ])
        peer2 = db.upsert_remote_peer("bob", _now())
        db.insert_remote_files(peer2, [
            {"pixel_hash": h2, "filename": "b.jpg", "size": 2000},
        ])

        treasures = db.get_family_treasures(sid)
        assert len(treasures) == 2
        peers = {t["peer_username"] for t in treasures}
        assert peers == {"alice", "bob"}


# ---------------------------------------------------------------------------
# Similarity schema + migration tests
# ---------------------------------------------------------------------------

class TestSimilaritySchema:
    """Plan §S1.5–S1.7 — similarity schema migration."""

    def test_files_has_perceptual_hash_columns(self, db: Database):
        """Migration must add perceptual_hash, width, height to files."""
        cols = {
            r[1]
            for r in db.conn.execute("PRAGMA table_info(files)").fetchall()
        }
        assert "perceptual_hash" in cols
        assert "width" in cols
        assert "height" in cols

    def test_sessions_has_similarity_enabled(self, db: Database):
        """Migration must add similarity_enabled column to sessions."""
        cols = {
            r[1]
            for r in db.conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        assert "similarity_enabled" in cols

    def test_similarity_enabled_defaults_to_zero(self, db: Database):
        sid = db.create_session("Test", _now())
        row = db.get_session(sid)
        assert row["similarity_enabled"] == 0

    def test_similarity_groups_table_exists(self, db: Database):
        tables = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "similarity_groups" in tables
        assert "similarity_group_members" in tables

    def test_similarity_indexes_exist(self, db: Database):
        indexes = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_files_phash" in indexes
        assert "idx_simgroups_session" in indexes
        assert "idx_simgroupmembers_group" in indexes
        assert "idx_simgroupmembers_file" in indexes

    def test_similarity_group_status_check_constraint(self, db: Database):
        """Status must be one of pending / reviewed / actioned."""
        sid = db.create_session("Test", _now())
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        gid = db.create_similarity_group(sid, _now(), fid, member_count=0)
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "UPDATE similarity_groups SET status = 'invalid' WHERE id = ?",
                (gid,),
            )

    def test_similarity_group_members_unique_constraint(self, db: Database):
        """(group_id, file_id) must be unique."""
        sid = db.create_session("Test", _now())
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        gid = db.create_similarity_group(sid, _now(), fid, member_count=1)
        db.add_similarity_group_members_batch([(gid, fid, 0)])
        # INSERT OR IGNORE — duplicate silently ignored
        db.add_similarity_group_members_batch([(gid, fid, 0)])
        members = db.get_similarity_group_members(gid)
        assert len(members) == 1

    def test_cascade_delete_session_removes_groups(self, db: Database):
        """Deleting a session must cascade-delete its similarity groups."""
        sid = db.create_session("Test", _now())
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        gid = db.create_similarity_group(sid, _now(), fid, member_count=1)
        db.add_similarity_group_members_batch([(gid, fid, 0)])
        db.delete_session(sid)
        assert db.get_similarity_group_count(sid) == 0


# ---------------------------------------------------------------------------
# Similarity CRUD tests
# ---------------------------------------------------------------------------

class TestSimilarityCRUD:
    """Plan §S1.8 — similarity group CRUD methods."""

    # -- Perceptual hash storage -------------------------------------------

    def test_update_perceptual_hashes_batch(self, db: Database, session_factory):
        sid = session_factory()
        f1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        f2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        db.update_perceptual_hashes_batch([
            (f1, "abcd1234abcd1234", 1920, 1080),
            (f2, "1234abcd1234abcd", 800, 600),
        ])
        row1 = db.conn.execute(
            "SELECT perceptual_hash, width, height FROM files WHERE id = ?",
            (f1,),
        ).fetchone()
        assert row1["perceptual_hash"] == "abcd1234abcd1234"
        assert row1["width"] == 1920
        assert row1["height"] == 1080

        row2 = db.conn.execute(
            "SELECT perceptual_hash, width, height FROM files WHERE id = ?",
            (f2,),
        ).fetchone()
        assert row2["perceptual_hash"] == "1234abcd1234abcd"
        assert row2["width"] == 800
        assert row2["height"] == 600

    def test_update_dual_hashes_batch(self, db: Database, session_factory):
        """Dual-hash batch sets pixel_hash + thumbnail + pHash + dimensions."""
        sid = session_factory()
        fid = db.insert_file(sid, "/c.jpg", 300, _now(), _now())
        pixel_h = _make_hash("d")
        db.update_dual_hashes_batch([
            (fid, pixel_h, "/t/c.jpg", "ffff0000ffff0000", 4032, 3024),
        ])
        row = db.conn.execute(
            "SELECT pixel_hash, thumbnail_path, perceptual_hash, width, height "
            "FROM files WHERE id = ?",
            (fid,),
        ).fetchone()
        assert row["pixel_hash"] == pixel_h
        assert row["thumbnail_path"] == "/t/c.jpg"
        assert row["perceptual_hash"] == "ffff0000ffff0000"
        assert row["width"] == 4032
        assert row["height"] == 3024

    # -- Files needing hashes ----------------------------------------------

    def test_get_files_needing_hashes_returns_unhashed(self, db: Database, session_factory):
        sid = session_factory()
        f1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        f2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        # f1 gets a pHash, f2 does not
        db.update_perceptual_hashes_batch([(f1, "aaaa", 100, 100)])
        needing = db.get_files_needing_hashes(sid)
        ids = [r["id"] for r in needing]
        assert f2 in ids
        assert f1 not in ids

    def test_get_files_needing_hashes_excludes_deleted(self, db: Database, session_factory):
        """Deleted files should not be returned for hashing."""
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        db.conn.execute(
            "UPDATE files SET status = 'deleted' WHERE id = ?", (fid,)
        )
        db.conn.commit()
        needing = db.get_files_needing_hashes(sid)
        assert len(needing) == 0

    def test_get_files_with_phash(self, db: Database, session_factory):
        sid = session_factory()
        f1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        f2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        f3 = db.insert_file(sid, "/c.jpg", 300, _now(), _now())
        db.update_perceptual_hashes_batch([
            (f1, "aaaa", 100, 100),
            (f3, "bbbb", 200, 200),
        ])
        with_phash = db.get_files_with_phash(sid)
        ids = [r["id"] for r in with_phash]
        assert f1 in ids
        assert f3 in ids
        assert f2 not in ids

    # -- Similarity group lifecycle ----------------------------------------

    def test_create_similarity_group(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        gid = db.create_similarity_group(sid, _now(), fid, member_count=3)
        assert isinstance(gid, int)
        assert gid > 0

    def test_get_similarity_groups(self, db: Database, session_factory):
        sid = session_factory()
        f1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        f2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        g1 = db.create_similarity_group(sid, _now(), f1, member_count=2)
        g2 = db.create_similarity_group(sid, _now(), f2, member_count=3)
        groups = db.get_similarity_groups(sid)
        assert len(groups) == 2
        # Ordered by member_count DESC
        assert groups[0]["id"] == g2
        assert groups[1]["id"] == g1

    def test_get_similarity_groups_includes_representative_path(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/photos/best.jpg", 100, _now(), _now())
        db.create_similarity_group(sid, _now(), fid, member_count=1)
        groups = db.get_similarity_groups(sid)
        assert groups[0]["representative_path"] == "/photos/best.jpg"

    def test_get_similarity_group_count(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        assert db.get_similarity_group_count(sid) == 0
        db.create_similarity_group(sid, _now(), fid, member_count=1)
        db.create_similarity_group(sid, _now(), fid, member_count=1)
        assert db.get_similarity_group_count(sid) == 2

    def test_add_and_get_similarity_group_members(self, db: Database, session_factory):
        sid = session_factory()
        f1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        f2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        f3 = db.insert_file(sid, "/c.jpg", 300, _now(), _now())
        gid = db.create_similarity_group(sid, _now(), f1, member_count=3)
        db.add_similarity_group_members_batch([
            (gid, f1, 0),
            (gid, f2, 3),
            (gid, f3, 7),
        ])
        members = db.get_similarity_group_members(gid)
        assert len(members) == 3
        # Ordered by distance, then id
        assert members[0]["distance"] == 0
        assert members[1]["distance"] == 3
        assert members[2]["distance"] == 7
        # File metadata is joined
        assert members[0]["path"] == "/a.jpg"
        assert members[1]["path"] == "/b.jpg"

    def test_get_similarity_group_file_count(self, db: Database, session_factory):
        sid = session_factory()
        f1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        f2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        f3 = db.insert_file(sid, "/c.jpg", 300, _now(), _now())
        g1 = db.create_similarity_group(sid, _now(), f1, member_count=2)
        g2 = db.create_similarity_group(sid, _now(), f3, member_count=1)
        db.add_similarity_group_members_batch([
            (g1, f1, 0),
            (g1, f2, 4),
            (g2, f3, 0),
        ])
        assert db.get_similarity_group_file_count(sid) == 3

    def test_update_similarity_group_status(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        gid = db.create_similarity_group(sid, _now(), fid)
        # Default is pending
        groups = db.get_similarity_groups(sid)
        assert groups[0]["status"] == "pending"
        # Update to reviewed
        db.update_similarity_group_status(gid, "reviewed")
        groups = db.get_similarity_groups(sid)
        assert groups[0]["status"] == "reviewed"
        # Update to actioned
        db.update_similarity_group_status(gid, "actioned")
        groups = db.get_similarity_groups(sid)
        assert groups[0]["status"] == "actioned"

    def test_clear_similarity_groups(self, db: Database, session_factory):
        sid = session_factory()
        f1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        f2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        gid = db.create_similarity_group(sid, _now(), f1, member_count=2)
        db.add_similarity_group_members_batch([(gid, f1, 0), (gid, f2, 5)])
        db.clear_similarity_groups(sid)
        assert db.get_similarity_group_count(sid) == 0
        assert db.get_similarity_group_file_count(sid) == 0

    def test_clear_only_affects_target_session(self, db: Database, session_factory):
        """Clearing groups for session A must not affect session B."""
        sid_a = session_factory("Session A")
        sid_b = session_factory("Session B")
        fa = db.insert_file(sid_a, "/a.jpg", 100, _now(), _now())
        fb = db.insert_file(sid_b, "/b.jpg", 200, _now(), _now())
        db.create_similarity_group(sid_a, _now(), fa, member_count=1)
        db.create_similarity_group(sid_b, _now(), fb, member_count=1)
        db.clear_similarity_groups(sid_a)
        assert db.get_similarity_group_count(sid_a) == 0
        assert db.get_similarity_group_count(sid_b) == 1

    def test_group_count_scoped_to_session(self, db: Database, session_factory):
        """Counts must be scoped to the queried session."""
        sid_a = session_factory("A")
        sid_b = session_factory("B")
        fa = db.insert_file(sid_a, "/a.jpg", 100, _now(), _now())
        fb = db.insert_file(sid_b, "/b.jpg", 200, _now(), _now())
        db.create_similarity_group(sid_a, _now(), fa, member_count=1)
        db.create_similarity_group(sid_b, _now(), fb, member_count=1)
        db.create_similarity_group(sid_b, _now(), fb, member_count=1)
        assert db.get_similarity_group_count(sid_a) == 1
        assert db.get_similarity_group_count(sid_b) == 2


# ---------------------------------------------------------------------------
# Scoped clearing + bulk fetch (Composable Sort Chain feature)
# ---------------------------------------------------------------------------

class TestScopedClearing:
    """Tests for clear_duplicate_actions, clear_similarity_actions, get_all_duplicate_files_bulk."""

    @pytest.fixture(autouse=True)
    def _setup(self, db: Database, session_factory):
        self.db = db
        self.sid = session_factory("Scoped")
        # Create duplicate group: hash_a with 2 files
        self.hash_a = _make_hash("a")
        self.f1 = db.insert_file(self.sid, "/dup/img1.jpg", 1000, "2024-01-01", _now())
        self.f2 = db.insert_file(self.sid, "/dup/img2.jpg", 500, "2024-01-02", _now())
        db.update_pixel_hash(self.f1, self.hash_a, "/thumbs/a.jpg")
        db.update_pixel_hash(self.f2, self.hash_a, "/thumbs/a.jpg")
        # Create a unique file (not in any duplicate group)
        self.hash_u = _make_hash("u")
        self.f_unique = db.insert_file(self.sid, "/unique/solo.jpg", 200, "2024-01-01", _now())
        db.update_pixel_hash(self.f_unique, self.hash_u, "/thumbs/u.jpg")
        # Create similarity group with f1 and f_unique
        self.gid = db.create_similarity_group(self.sid, _now(), self.f1, member_count=2)
        db.add_similarity_group_members_batch([
            (self.gid, self.f1, 0),
            (self.gid, self.f_unique, 5),
        ])

    def test_clear_duplicate_actions_only_clears_dupes(self):
        """clear_duplicate_actions removes only duplicate-group file actions."""
        ts = _now()
        # Set actions on all three files
        self.db.set_file_actions_batch([
            (self.sid, self.f1, "keep", "file", ts),
            (self.sid, self.f2, "delete", "file", ts),
            (self.sid, self.f_unique, "keep", "file", ts),
        ])
        self.db.clear_duplicate_actions(self.sid)
        decided = self.db.get_decided_file_ids(self.sid)
        # f_unique action should survive (not in duplicate group)
        assert self.f_unique in decided
        # Duplicate group members should be cleared
        assert self.f1 not in decided
        assert self.f2 not in decided

    def test_clear_similarity_actions_only_clears_similarity(self):
        """clear_similarity_actions removes only similarity-group member actions."""
        ts = _now()
        self.db.set_file_actions_batch([
            (self.sid, self.f1, "keep", "file", ts),
            (self.sid, self.f2, "delete", "file", ts),
            (self.sid, self.f_unique, "keep", "file", ts),
        ])
        self.db.clear_similarity_actions(self.sid)
        decided = self.db.get_decided_file_ids(self.sid)
        # f2 is only in duplicate group, not similarity → should survive
        assert self.f2 in decided
        # f1 and f_unique are similarity members → should be cleared
        assert self.f1 not in decided
        assert self.f_unique not in decided

    def test_clear_duplicate_actions_empty_session(self):
        """No crash when session has no actions."""
        self.db.clear_duplicate_actions(self.sid)
        assert self.db.get_decided_file_ids(self.sid) == set()

    def test_clear_similarity_actions_empty_session(self):
        """No crash when session has no actions."""
        self.db.clear_similarity_actions(self.sid)
        assert self.db.get_decided_file_ids(self.sid) == set()

    def test_get_all_duplicate_files_bulk(self):
        """Bulk fetch returns all duplicate files grouped by pixel_hash."""
        groups = self.db.get_all_duplicate_files_bulk(self.sid)
        assert self.hash_a in groups
        assert self.hash_u not in groups  # unique, not a duplicate
        files = groups[self.hash_a]
        assert len(files) == 2
        file_ids = {f["id"] for f in files}
        assert file_ids == {self.f1, self.f2}

    def test_get_all_duplicate_files_bulk_returns_metadata(self):
        """Each file dict has expected keys."""
        groups = self.db.get_all_duplicate_files_bulk(self.sid)
        f = groups[self.hash_a][0]
        for key in ("id", "path", "size", "modified_at", "width", "height", "pixel_hash"):
            assert key in f, f"Missing key: {key}"

    def test_get_all_duplicate_files_bulk_empty_session(self, db: Database, session_factory):
        """Empty session returns empty dict."""
        sid = session_factory("Empty")
        assert db.get_all_duplicate_files_bulk(sid) == {}

    def test_scoped_clears_are_independent(self):
        """Clearing one view's actions does not affect the other view."""
        ts = _now()
        self.db.set_file_actions_batch([
            (self.sid, self.f1, "keep", "file", ts),
            (self.sid, self.f2, "delete", "file", ts),
            (self.sid, self.f_unique, "keep", "file", ts),
        ])
        # Clear duplicates, then check similarity members still have actions
        self.db.clear_duplicate_actions(self.sid)
        decided = self.db.get_decided_file_ids(self.sid)
        # f_unique is only a similarity member → its action from initial batch should remain
        assert self.f_unique in decided

        # Re-set all actions
        self.db.set_file_actions_batch([
            (self.sid, self.f1, "keep", "file", ts),
            (self.sid, self.f2, "delete", "file", ts),
            (self.sid, self.f_unique, "keep", "file", ts),
        ])
        # Clear similarity, then check duplicate members still have actions
        self.db.clear_similarity_actions(self.sid)
        decided = self.db.get_decided_file_ids(self.sid)
        assert self.f2 in decided  # f2 only in duplicate group
