"""
tests/stress/test_stress.py — Nightly stress suite.

Phase 3: 10k+ images, pipe saturation, rapid event storms.

These tests run in a separate CI job with extended timeout (nightly only),
not per-PR. They validate the scanner under production-scale workloads.

Run locally: pytest tests/stress -v --override-ini="addopts="
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
from sidecar.output import StdoutOutput


# ── Helpers ──────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from data.db import Database
    d = Database(tmp_path / "stress.db")
    d.open()
    yield d
    d.close()


@pytest.fixture
def thumb_dir(tmp_path):
    t = tmp_path / "thumbs"
    t.mkdir()
    return t


# ═════════════════════════════════════════════════════════════════════════════
# Large corpus scan
# ═════════════════════════════════════════════════════════════════════════════

class TestLargeCorpus:

    def test_1000_files_with_duplicates(self, db, thumb_dir, tmp_path):
        """
        1000 files: 100 duplicate groups × 10 copies each.
        Validates scanner completes without hanging or data loss.
        """
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()

        for group in range(100):
            group_dir = scan_dir / f"group_{group:03d}"
            group_dir.mkdir()
            color = (group * 2 % 256, (group * 5 + 30) % 256, (group * 7 + 60) % 256)
            for copy in range(10):
                _jpg(group_dir / f"copy_{copy:02d}.jpg", color=color)

        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="stress 1k", created_at=now)
        db.add_session_folder(sid, str(scan_dir))

        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        done = threading.Event()
        dup_count = [0]

        scanner.scan_complete.connect(lambda: done.set())
        scanner.duplicate_found.connect(lambda h, ids: dup_count.__setitem__(0, dup_count[0] + 1))
        scanner.start()

        assert done.wait(timeout=120.0), "1000-file scan did not complete"

        files = db.get_files_for_session(sid)
        assert len(files) == 1000
        assert dup_count[0] == 100  # one signal per group


# ═════════════════════════════════════════════════════════════════════════════
# Pipe saturation
# ═════════════════════════════════════════════════════════════════════════════

class TestPipeSaturation:

    def test_50000_events_through_output(self):
        """
        50,000 events through StdoutOutput — simulates extreme event volume.
        All events must drain without data loss.
        """
        buf = io.StringIO()
        output = StdoutOutput(stream=buf)

        for i in range(50000):
            output.notify("scan:progress", {"current": i, "total": 50000})

        output.shutdown()

        lines = buf.getvalue().strip().split("\n")
        # Each notify for a forwarded event produces one line
        assert len(lines) == 50000, f"Expected 50000, got {len(lines)}"


# ═════════════════════════════════════════════════════════════════════════════
# Rapid event storms
# ═════════════════════════════════════════════════════════════════════════════

class TestEventStorm:

    def test_concurrent_producers(self):
        """
        10 producer threads each emit 1000 events simultaneously.
        All 10,000 events must be captured without drops.
        """
        buf = io.StringIO()
        output = StdoutOutput(stream=buf)
        barrier = threading.Barrier(10)

        def producer(thread_id):
            barrier.wait()  # all threads start simultaneously
            for i in range(1000):
                output.notify("scan:progress", {"thread": thread_id, "i": i})

        threads = [threading.Thread(target=producer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        output.shutdown()

        lines = buf.getvalue().strip().split("\n")
        assert len(lines) == 10000, f"Expected 10000, got {len(lines)}"
