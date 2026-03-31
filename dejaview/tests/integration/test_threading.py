"""
tests/integration/test_threading.py — Threading and concurrency tests.

Phase 2: Scanner queue saturation, writer thread shutdown, DB WAL contention.

These tests exercise the concurrency boundaries that production bugs live in:
pipe pressure, thread lifecycle, and database lock contention under load.
"""

import io
import json
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from core.scanner import Scanner
from sidecar.output import StdoutOutput, ListOutput


# ── Helpers ──────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def scan_dir(tmp_path):
    d = tmp_path / "scan"
    d.mkdir()
    return d


@pytest.fixture
def session_id(db, scan_dir):
    now = datetime.now(timezone.utc).isoformat()
    sid = db.create_session(name="threading test", created_at=now)
    db.add_session_folder(sid, str(scan_dir))
    return sid


# ═════════════════════════════════════════════════════════════════════════════
# Scanner queue saturation
# ═════════════════════════════════════════════════════════════════════════════

class TestQueueSaturation:
    """Test the scanner pipeline under high-volume workloads."""

    def test_many_same_size_files_complete(self, db, scan_dir, session_id, thumb_dir):
        """
        200 same-size files all become hash candidates.
        Verifies the sliding-window pipeline handles a fully-saturated
        work queue without deadlock or data loss.
        """
        for i in range(200):
            _jpg(scan_dir / f"img_{i:03d}.jpg", color=(100, 100, 100))

        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()

        assert done.wait(timeout=60.0), "Scan with 200 same-size files did not complete"

        files = db.get_files_for_session(session_id)
        hashed = [f for f in files if f["pixel_hash"] is not None]
        assert len(hashed) == 200, f"Expected all 200 files hashed, got {len(hashed)}"

    def test_single_worker_completes(self, db, scan_dir, session_id, thumb_dir):
        """
        With max_workers=1, the pipeline must still complete.
        Tests the degenerate case where there's no parallelism.
        """
        for i in range(20):
            _jpg(scan_dir / f"img_{i:02d}.jpg", color=(50, 50, 50))

        scanner = Scanner(
            db=db, session_id=session_id, thumb_dir=thumb_dir, max_workers=1
        )
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()

        assert done.wait(timeout=30.0), "Single-worker scan did not complete"

    def test_many_directories_with_locality(self, db, thumb_dir, tmp_path):
        """
        30 directories with same-size files each.
        Tests the locality gate and deferred queue under directory pressure.
        """
        root = tmp_path / "multi"
        root.mkdir()
        for d in range(30):
            dir_path = root / f"dir_{d:02d}"
            dir_path.mkdir()
            # 2 same-size files per dir → size candidates
            _jpg(dir_path / "a.jpg", color=(d * 8 % 256, 100, 100))
            _jpg(dir_path / "b.jpg", color=(d * 8 % 256, 100, 100))

        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="locality test", created_at=now)
        db.add_session_folder(sid, str(root))

        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()

        assert done.wait(timeout=30.0), "Multi-directory scan did not complete"

        files = db.get_files_for_session(sid)
        assert len(files) == 60


# ═════════════════════════════════════════════════════════════════════════════
# Writer thread lifecycle
# ═════════════════════════════════════════════════════════════════════════════

class TestWriterShutdown:
    """Test the StdoutOutput writer thread lifecycle."""

    def test_shutdown_drains_all_messages(self):
        """All enqueued messages must be written before shutdown returns."""
        buf = io.StringIO()
        output = StdoutOutput(stream=buf)

        for i in range(50):
            output.write({"id": i})

        output.shutdown()

        lines = [ln for ln in buf.getvalue().strip().split("\n") if ln]
        assert len(lines) == 50, f"Expected 50 lines drained, got {len(lines)}"

        # Verify each line is valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "id" in parsed

    def test_shutdown_is_idempotent(self):
        """Calling shutdown twice must not raise."""
        buf = io.StringIO()
        output = StdoutOutput(stream=buf)
        output.write({"test": True})
        output.shutdown()
        # Second shutdown — writer thread already exited
        output.shutdown()

    def test_write_after_shutdown_does_not_crash(self):
        """Writing after shutdown enqueues but doesn't crash."""
        buf = io.StringIO()
        output = StdoutOutput(stream=buf)
        output.shutdown()
        # This enqueues but nobody drains — should not raise
        output.write({"late": True})

    def test_high_throughput_no_drops(self):
        """10,000 rapid writes must all drain without data loss."""
        buf = io.StringIO()
        output = StdoutOutput(stream=buf)

        for i in range(10000):
            output.ok(i, "ok")

        output.shutdown()

        lines = [ln for ln in buf.getvalue().strip().split("\n") if ln]
        assert len(lines) == 10000, f"Expected 10000, got {len(lines)}"


# ═════════════════════════════════════════════════════════════════════════════
# DB WAL contention
# ═════════════════════════════════════════════════════════════════════════════

class TestWALContention:
    """Test database access under concurrent read/write pressure."""

    def test_concurrent_read_during_scan(self, db, scan_dir, session_id, thumb_dir):
        """
        Reading from DB while scanner writes must not raise or corrupt.
        WAL mode allows concurrent readers + single writer.
        """
        for i in range(50):
            _jpg(scan_dir / f"img_{i:02d}.jpg", color=(80, 80, 80))

        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        done = threading.Event()
        read_errors: list[str] = []

        scanner.scan_complete.connect(lambda: done.set())

        # Reader thread: poll DB continuously while scan runs
        def reader():
            while not done.is_set():
                try:
                    db.get_files_for_session(session_id)
                    db.get_session(session_id)
                except Exception as exc:
                    read_errors.append(str(exc))
                time.sleep(0.01)

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        scanner.start()
        assert done.wait(timeout=30.0), "Scan did not complete"
        reader_thread.join(timeout=5.0)

        assert not read_errors, f"DB read errors during scan: {read_errors}"

    def test_session_status_consistent_after_scan(self, db, scan_dir, session_id, thumb_dir):
        """DB state must be consistent after scan completes."""
        for i in range(10):
            _jpg(scan_dir / f"img_{i}.jpg", color=(60, 60, 60))

        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()
        done.wait(timeout=15.0)

        session = db.get_session(session_id)
        assert session["status"] == "complete"

        files = db.get_files_for_session(session_id)
        assert len(files) == 10
