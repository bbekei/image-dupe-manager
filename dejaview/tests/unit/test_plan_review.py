"""
tests/unit/test_plan_review.py — Tests for DB methods used by Plan Review.

Tests cover: soft_deletes CRUD, get_plan_summary(), get_delete_actions_with_paths().
"""

import datetime

import pytest

from data.db import Database


class TestSoftDeletesCRUD:
    """Tests for soft_deletes table operations."""

    def _insert_file(self, db, session_id, path, size=1000):
        """Helper: insert a file row and return its id."""
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return db.insert_file(session_id, path, size, ts, ts)

    def test_record_soft_delete(self, db, session_factory):
        sid = session_factory()
        fid = self._insert_file(db, sid, "/photos/a.jpg")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        expires = "2026-04-01T00:00:00+00:00"

        sd_id = db.record_soft_delete(
            sid, fid, "/photos/a.jpg", "/trash/1/a.jpg", now, expires
        )
        assert sd_id is not None

        active = db.get_active_soft_deletes(sid)
        assert len(active) == 1
        assert active[0]["original_path"] == "/photos/a.jpg"
        assert active[0]["trash_path"] == "/trash/1/a.jpg"

    def test_record_recovery(self, db, session_factory):
        sid = session_factory()
        fid = self._insert_file(db, sid, "/photos/a.jpg")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sd_id = db.record_soft_delete(
            sid, fid, "/photos/a.jpg", "/trash/a.jpg", now, "2026-04-01"
        )

        # Before recovery
        assert len(db.get_active_soft_deletes(sid)) == 1

        # After recovery
        db.record_recovery(sd_id, now)
        assert len(db.get_active_soft_deletes(sid)) == 0

    def test_get_expired_soft_deletes(self, db, session_factory):
        sid = session_factory()
        fid1 = self._insert_file(db, sid, "/photos/a.jpg")
        fid2 = self._insert_file(db, sid, "/photos/b.jpg")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # a.jpg expired yesterday
        db.record_soft_delete(
            sid, fid1, "/photos/a.jpg", "/trash/a.jpg",
            now, "2026-03-01T00:00:00+00:00"
        )
        # b.jpg expires next month
        db.record_soft_delete(
            sid, fid2, "/photos/b.jpg", "/trash/b.jpg",
            now, "2026-04-01T00:00:00+00:00"
        )

        expired = db.get_expired_soft_deletes("2026-03-02T00:00:00+00:00")
        assert len(expired) == 1
        assert expired[0]["original_path"] == "/photos/a.jpg"

    def test_upsert_soft_delete(self, db, session_factory):
        """Re-inserting same session_id+file_id updates existing row."""
        sid = session_factory()
        fid = self._insert_file(db, sid, "/photos/a.jpg")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.record_soft_delete(
            sid, fid, "/photos/a.jpg", "/trash/old.jpg", now, "2026-04-01"
        )
        db.record_soft_delete(
            sid, fid, "/photos/a.jpg", "/trash/new.jpg", now, "2026-05-01"
        )

        active = db.get_active_soft_deletes(sid)
        assert len(active) == 1
        assert active[0]["trash_path"] == "/trash/new.jpg"


class TestPlanSummary:
    """Tests for get_plan_summary()."""

    def _insert_file(self, db, session_id, path, size=1000):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return db.insert_file(session_id, path, size, ts, ts)

    def test_empty_plan(self, db, session_factory):
        sid = session_factory()
        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 0
        assert summary["delete_bytes"] == 0
        assert summary["keep_count"] == 0
        assert summary["ignore_count"] == 0
        assert summary["folder_delete_count"] == 0

    def test_mixed_actions(self, db, session_factory):
        sid = session_factory()
        fid1 = self._insert_file(db, sid, "/photos/a.jpg", size=5000)
        fid2 = self._insert_file(db, sid, "/photos/b.jpg", size=3000)
        fid3 = self._insert_file(db, sid, "/photos/c.jpg", size=2000)

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.set_file_action(sid, fid1, "delete", scope="file", decided_at=ts)
        db.set_file_action(sid, fid2, "keep", scope="file", decided_at=ts)
        db.set_file_action(sid, fid3, "ignore", scope="file", decided_at=ts)

        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 1
        assert summary["delete_bytes"] == 5000
        assert summary["keep_count"] == 1
        assert summary["ignore_count"] == 1

    def test_folder_delete_count(self, db, session_factory):
        sid = session_factory()
        fid1 = self._insert_file(db, sid, "/backup/a.jpg", size=1000)
        fid2 = self._insert_file(db, sid, "/backup/b.jpg", size=2000)

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.set_file_action(sid, fid1, "delete", scope="folder", decided_at=ts)
        db.set_file_action(sid, fid2, "delete", scope="folder", decided_at=ts)

        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 2
        assert summary["delete_bytes"] == 3000
        assert summary["folder_delete_count"] == 2

    def test_excludes_executed_actions(self, db, session_factory):
        sid = session_factory()
        fid = self._insert_file(db, sid, "/photos/a.jpg", size=5000)

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.set_file_action(sid, fid, "delete", scope="file", decided_at=ts)

        # Simulate execution
        db.conn.execute(
            "UPDATE file_actions SET executed_at = ? WHERE session_id = ? AND file_id = ?",
            (ts, sid, fid)
        )
        db.conn.commit()

        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 0


class TestDeleteActionsWithPaths:
    """Tests for get_delete_actions_with_paths()."""

    def _insert_file(self, db, session_id, path, size=1000):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return db.insert_file(session_id, path, size, ts, ts)

    def test_returns_delete_actions_only(self, db, session_factory):
        sid = session_factory()
        fid1 = self._insert_file(db, sid, "/photos/a.jpg", size=5000)
        fid2 = self._insert_file(db, sid, "/photos/b.jpg", size=3000)

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.set_file_action(sid, fid1, "delete", scope="file", decided_at=ts)
        db.set_file_action(sid, fid2, "keep", scope="file", decided_at=ts)

        rows = db.get_delete_actions_with_paths(sid)
        assert len(rows) == 1
        assert rows[0]["path"] == "/photos/a.jpg"
        assert rows[0]["size"] == 5000

    def test_includes_scope_info(self, db, session_factory):
        sid = session_factory()
        fid = self._insert_file(db, sid, "/backup/a.jpg")

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.set_file_action(sid, fid, "delete", scope="folder", decided_at=ts)

        rows = db.get_delete_actions_with_paths(sid)
        assert len(rows) == 1
        assert rows[0]["scope"] == "folder"

    def test_ordered_by_path(self, db, session_factory):
        sid = session_factory()
        fid_b = self._insert_file(db, sid, "/photos/b.jpg")
        fid_a = self._insert_file(db, sid, "/photos/a.jpg")

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.set_file_action(sid, fid_b, "delete", decided_at=ts)
        db.set_file_action(sid, fid_a, "delete", decided_at=ts)

        rows = db.get_delete_actions_with_paths(sid)
        assert rows[0]["path"] == "/photos/a.jpg"
        assert rows[1]["path"] == "/photos/b.jpg"
