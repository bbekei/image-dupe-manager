"""
tests/unit/test_executor.py — Unit tests for Phase 3 (Execution Engine).

Tests the PlanExecutor QThread and the db.mark_file_action_executed() method.
No PyQt6 event loop needed — we call executor.run() directly (synchronous).
"""

import datetime

import pytest

from core.executor import PlanExecutor
from data.db import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _insert_file(db: Database, session_id: int, path: str, size: int = 1000) -> int:
    """Insert a file row and return its id."""
    return db.insert_file(session_id, path, size, _now(), _now())


# ---------------------------------------------------------------------------
# TestMarkFileActionExecuted — DB method
# ---------------------------------------------------------------------------

class TestMarkFileActionExecuted:

    def test_sets_executed_at_timestamp(self, db: Database, session_factory):
        sid = session_factory()
        fid = _insert_file(db, sid, "/photos/img1.jpg")
        db.set_file_action(sid, fid, "delete", decided_at=_now())

        ts = _now()
        db.mark_file_action_executed(sid, fid, ts)

        row = db.conn.execute(
            "SELECT executed_at FROM file_actions WHERE session_id = ? AND file_id = ?",
            (sid, fid),
        ).fetchone()
        assert row is not None
        assert row["executed_at"] == ts

    def test_noop_for_nonexistent_action(self, db: Database, session_factory):
        """Calling mark on a nonexistent action should not raise."""
        sid = session_factory()
        db.mark_file_action_executed(sid, 99999, _now())


# ---------------------------------------------------------------------------
# TestPlanExecutor — Core execution flow
# ---------------------------------------------------------------------------

class TestPlanExecutor:

    def test_empty_plan(self, db: Database, session_factory, tmp_path):
        """No delete actions → immediate completion with 0/0."""
        sid = session_factory()
        trash = tmp_path / "trash"

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        results = []
        executor.execution_complete.connect(lambda s, e: results.append((s, e)))

        executor.run()  # synchronous

        assert results == [(0, 0)]

    def test_executes_delete_actions(self, db: Database, session_factory, tmp_path):
        """Files are moved to trash and DB is updated."""
        sid = session_factory()
        trash = tmp_path / "trash"

        # Create real files
        src1 = tmp_path / "photos" / "img1.jpg"
        src2 = tmp_path / "photos" / "img2.jpg"
        src1.parent.mkdir(parents=True, exist_ok=True)
        src1.write_bytes(b"image1data")
        src2.write_bytes(b"image2data")

        fid1 = _insert_file(db, sid, str(src1), 10)
        fid2 = _insert_file(db, sid, str(src2), 10)
        db.set_file_action(sid, fid1, "delete", decided_at=_now())
        db.set_file_action(sid, fid2, "delete", decided_at=_now())

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        results = []
        executor.execution_complete.connect(lambda s, e: results.append((s, e)))

        executor.run()

        assert results == [(2, 0)]
        # Original files should be gone
        assert not src1.exists()
        assert not src2.exists()
        # Trash should have the files
        trash_files = list(trash.rglob("*"))
        assert any(f.is_file() for f in trash_files)

    def test_marks_executed_at(self, db: Database, session_factory, tmp_path):
        """file_actions.executed_at is set after execution."""
        sid = session_factory()
        trash = tmp_path / "trash"
        src = tmp_path / "img.jpg"
        src.write_bytes(b"data")

        fid = _insert_file(db, sid, str(src), 4)
        db.set_file_action(sid, fid, "delete", decided_at=_now())

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        executor.run()

        row = db.conn.execute(
            "SELECT executed_at FROM file_actions WHERE session_id = ? AND file_id = ?",
            (sid, fid),
        ).fetchone()
        assert row["executed_at"] is not None

    def test_records_soft_deletes(self, db: Database, session_factory, tmp_path):
        """soft_deletes table is populated after execution."""
        sid = session_factory()
        trash = tmp_path / "trash"
        src = tmp_path / "img.jpg"
        src.write_bytes(b"data")

        fid = _insert_file(db, sid, str(src), 4)
        db.set_file_action(sid, fid, "delete", decided_at=_now())

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        executor.run()

        soft_dels = db.get_active_soft_deletes(sid)
        assert len(soft_dels) == 1
        assert soft_dels[0]["file_id"] == fid
        assert soft_dels[0]["original_path"] == str(src)

    def test_updates_file_status(self, db: Database, session_factory, tmp_path):
        """files.status changes to 'deleted' after execution."""
        sid = session_factory()
        trash = tmp_path / "trash"
        src = tmp_path / "img.jpg"
        src.write_bytes(b"data")

        fid = _insert_file(db, sid, str(src), 4)
        db.set_file_action(sid, fid, "delete", decided_at=_now())

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        executor.run()

        file_row = db.get_file(fid)
        assert file_row["status"] == "deleted"

    def test_skips_missing_files(self, db: Database, session_factory, tmp_path):
        """File already gone → error emitted, execution continues."""
        sid = session_factory()
        trash = tmp_path / "trash"

        # File that exists
        src_ok = tmp_path / "ok.jpg"
        src_ok.write_bytes(b"data")
        fid_ok = _insert_file(db, sid, str(src_ok), 4)
        db.set_file_action(sid, fid_ok, "delete", decided_at=_now())

        # File that does NOT exist
        fid_missing = _insert_file(db, sid, str(tmp_path / "gone.jpg"), 4)
        db.set_file_action(sid, fid_missing, "delete", decided_at=_now())

        errors = []
        results = []

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        executor.execution_error.connect(lambda p, m: errors.append((p, m)))
        executor.execution_complete.connect(lambda s, e: results.append((s, e)))

        executor.run()

        assert results == [(1, 1)]  # 1 success, 1 error
        assert len(errors) == 1
        assert "gone.jpg" in errors[0][0]

    def test_stop_halts_execution(self, db: Database, session_factory, tmp_path):
        """Calling stop() before run() should halt immediately."""
        sid = session_factory()
        trash = tmp_path / "trash"

        src = tmp_path / "img.jpg"
        src.write_bytes(b"data")
        fid = _insert_file(db, sid, str(src), 4)
        db.set_file_action(sid, fid, "delete", decided_at=_now())

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        executor.stop()  # request stop before run

        results = []
        executor.execution_complete.connect(lambda s, e: results.append((s, e)))
        executor.run()

        assert results == [(0, 0)]
        # File should still exist
        assert src.exists()

    def test_plan_summary_excludes_executed(self, db: Database, session_factory, tmp_path):
        """After execution, get_plan_summary should show 0 pending deletes."""
        sid = session_factory()
        trash = tmp_path / "trash"
        src = tmp_path / "img.jpg"
        src.write_bytes(b"data")

        fid = _insert_file(db, sid, str(src), 100)
        db.set_file_action(sid, fid, "delete", decided_at=_now())

        # Before execution
        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 1

        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash)
        executor.run()

        # After execution — executed actions excluded from summary
        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 0
