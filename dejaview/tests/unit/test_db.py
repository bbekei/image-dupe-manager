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
    """Return a valid 64-char hex pixel_hash for testing."""
    return (prefix * 64)[:64]


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
            "sessions", "session_folders", "files", "actions",
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
            "idx_files_status", "idx_actions_file", "idx_remote_files_hash",
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


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class TestActions:
    """Plan §Actions tests."""

    def test_stage_action_for_file(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        aid = db.stage_action(fid, "delete")
        assert isinstance(aid, int) and aid > 0

    def test_action_status_defaults_to_staged(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        aid = db.stage_action(fid, "keep")
        row = db.get_action(aid)
        assert row["status"] == "staged"
        assert row["performed_at"] is None

    def test_confirm_action_sets_performed_at(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        aid = db.stage_action(fid, "delete")
        ts = _now()
        db.confirm_action(aid, ts)
        row = db.get_action(aid)
        assert row["status"] == "confirmed"
        assert row["performed_at"] == ts

    def test_list_staged_actions_for_session(self, db: Database, session_factory):
        sid = session_factory()
        fid1 = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        fid2 = db.insert_file(sid, "/b.jpg", 200, _now(), _now())
        aid1 = db.stage_action(fid1, "delete")
        aid2 = db.stage_action(fid2, "keep")
        # Confirm one
        db.confirm_action(aid1, _now())
        staged = db.get_staged_actions(sid)
        # Only the unconfirmed one remains staged
        assert len(staged) == 1
        assert staged[0]["id"] == aid2

    def test_stage_rename_with_detail(self, db: Database, session_factory):
        sid = session_factory()
        fid = db.insert_file(sid, "/a.jpg", 100, _now(), _now())
        aid = db.stage_action(fid, "rename", detail="beach_2023.jpg")
        row = db.get_action(aid)
        assert row["action_type"] == "rename"
        assert row["detail"] == "beach_2023.jpg"


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

    def test_valid_hash_accepted(self):
        assert validate_pixel_hash("a" * 64) is True

    def test_hash_too_short_rejected(self):
        assert validate_pixel_hash("a" * 63) is False

    def test_hash_too_long_rejected(self):
        assert validate_pixel_hash("a" * 65) is False

    def test_uppercase_hex_rejected(self):
        assert validate_pixel_hash("A" * 64) is False

    def test_non_hex_chars_rejected(self):
        assert validate_pixel_hash("g" + "a" * 63) is False

    def test_sql_injection_attempt_rejected(self):
        assert validate_pixel_hash("'; DROP TABLE files; --" + "a" * 41) is False

    def test_empty_string_rejected(self):
        assert validate_pixel_hash("") is False

    def test_non_string_rejected(self):
        assert validate_pixel_hash(None) is False  # type: ignore[arg-type]
        assert validate_pixel_hash(123) is False   # type: ignore[arg-type]
