"""
tests/unit/test_jsonrpc_schema.py — JSON-RPC schema contract tests.

Phase 2: Timeboxed to scan, progress, results methods only.

Verifies that the API methods return the expected JSON shapes that
the frontend relies on.  These are contract tests, not functional tests —
they validate structure, not business logic.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from backend.api import DejaViewAPI


# ── Helpers ──────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


@pytest.fixture
def api(db, thumb_dir, tmp_path):
    """DejaViewAPI instance with ListOutput-like emit callback."""
    return DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=tmp_path / "trash",
        app_dir=tmp_path / "app",
    )


# ═════════════════════════════════════════════════════════════════════════════
# get_scan_progress schema
# ═════════════════════════════════════════════════════════════════════════════

class TestGetScanProgressSchema:
    """Verify get_scan_progress returns the shape the frontend expects."""

    def test_idle_state_shape(self, api):
        result = api.get_scan_progress()
        assert isinstance(result, dict)

        # Required keys
        for key in ("phase", "current", "total", "discovered", "duplicates", "message"):
            assert key in result, f"Missing key: {key}"

        assert result["phase"] == "idle"
        assert isinstance(result["current"], int)
        assert isinstance(result["total"], int)
        assert isinstance(result["discovered"], int)
        assert isinstance(result["duplicates"], int)
        assert isinstance(result["message"], str)

    def test_values_are_numeric(self, api):
        result = api.get_scan_progress()
        assert result["current"] >= 0
        assert result["total"] >= 0
        assert result["discovered"] >= 0
        assert result["duplicates"] >= 0


# ═════════════════════════════════════════════════════════════════════════════
# get_sessions schema
# ═════════════════════════════════════════════════════════════════════════════

class TestGetSessionsSchema:

    def test_empty_sessions(self, api):
        result = api.get_sessions()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_session_shape_after_creation(self, api, db, tmp_path):
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="schema test", created_at=now)
        db.add_session_folder(sid, str(scan_dir))

        result = api.get_sessions()
        assert len(result) >= 1

        session = result[0]
        for key in ("id", "name", "created_at", "status", "folder_count", "file_count"):
            assert key in session, f"Missing key: {key}"

        assert isinstance(session["id"], int)
        assert isinstance(session["name"], str)
        assert isinstance(session["folder_count"], int)
        assert isinstance(session["file_count"], int)


# ═════════════════════════════════════════════════════════════════════════════
# get_scan_summary schema
# ═════════════════════════════════════════════════════════════════════════════

class TestGetScanSummarySchema:

    def test_nonexistent_session(self, api):
        result = api.get_scan_summary(session_id=99999)
        assert isinstance(result, dict)

        for key in ("session_id", "total_files", "total_groups", "total_duplicates",
                     "recoverable_bytes", "similarity_group_count"):
            assert key in result, f"Missing key: {key}"

        assert result["total_files"] == 0
        assert result["total_groups"] == 0

    def test_summary_after_scan(self, api, db, thumb_dir, tmp_path):
        import threading

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        # 2 identical files → 1 duplicate group
        _jpg(scan_dir / "a.jpg", color=(100, 100, 100))
        _jpg(scan_dir / "b.jpg", color=(100, 100, 100))

        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="summary test", created_at=now)
        db.add_session_folder(sid, str(scan_dir))

        from core.scanner import Scanner
        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()
        assert done.wait(timeout=15.0)

        result = api.get_scan_summary(session_id=sid)
        assert result["total_files"] == 2
        assert result["total_groups"] >= 1
        assert result["total_duplicates"] >= 2
        assert isinstance(result["recoverable_bytes"], int)
        assert result["recoverable_bytes"] >= 0


# ═════════════════════════════════════════════════════════════════════════════
# Event payload schemas (via emit callback)
# ═════════════════════════════════════════════════════════════════════════════

class TestEventPayloadSchemas:
    """Verify event payloads match the shapes the frontend listens for."""

    def test_scan_events_have_expected_shapes(self, api, db, thumb_dir, tmp_path):
        """Run a scan and verify all emitted event payloads have correct keys."""
        import threading

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        _jpg(scan_dir / "a.jpg", color=(100, 100, 100))
        _jpg(scan_dir / "b.jpg", color=(100, 100, 100))

        events: list[tuple[str, dict]] = []
        api.set_emit_callback(lambda name, detail: events.append((name, detail)))

        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="event schema", created_at=now)
        db.add_session_folder(sid, str(scan_dir))

        from core.scanner import Scanner
        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        api._scanner = scanner
        api._connect_scanner_signals(scanner)
        scanner.start()
        assert done.wait(timeout=15.0)

        # Verify event schemas
        for name, detail in events:
            assert isinstance(detail, dict), f"Event {name} detail must be dict"

            if name == "scan:progress":
                assert "current" in detail
                assert "total" in detail
                assert "phase" in detail

            elif name == "scan:status":
                assert "status" in detail
                assert "message" in detail

            elif name == "scan:discovery_progress":
                assert "discovered" in detail

            elif name == "scan:duplicate_found":
                assert "pixel_hash" in detail
                assert "count" in detail

            elif name == "scan:similarity_progress":
                assert "current" in detail
                assert "total" in detail

            elif name == "scan:error":
                assert "path" in detail
                assert "message" in detail


# ═════════════════════════════════════════════════════════════════════════════
# Scan lifecycle commands (branch coverage for scan_commands.py)
# ═════════════════════════════════════════════════════════════════════════════

class TestScanLifecycleCommands:
    """Cover pause/stop/resume branches in scan_commands.py."""

    def test_pause_scan_noop_when_no_scanner(self, api):
        """pause_scan must not raise when no scanner is running."""
        api.pause_scan()  # _scanner is None — should be a noop

    def test_stop_scan_noop_when_no_scanner(self, api):
        """stop_scan must not raise when no scanner is running."""
        api.stop_scan()

    def test_stop_scan_on_dead_scanner(self, api, db, thumb_dir, tmp_path):
        """stop_scan when scanner has already finished marks session stopped."""
        import threading

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        _jpg(scan_dir / "a.jpg", size=(64, 64))

        events: list[tuple[str, dict]] = []
        api.set_emit_callback(lambda name, detail: events.append((name, detail)))

        sid = api.start_scan(
            folders=[str(scan_dir)],
            session_name="stop-dead",
            enable_similarity=False,
        )

        # Wait for completion
        import time
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if api.get_scan_progress()["phase"] == "complete":
                break
            time.sleep(0.05)

        # Scanner thread has exited — stop on dead scanner
        api.stop_scan()
        # Should emit stopped status
        stop_events = [e for e in events if e[0] == "scan:status" and e[1].get("status") == "stopped"]
        assert len(stop_events) >= 1

    def test_start_scan_returns_session_id(self, api, db, thumb_dir, tmp_path):
        """start_scan must return a valid session ID."""
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        _jpg(scan_dir / "x.jpg")

        sid = api.start_scan(
            folders=[str(scan_dir)],
            session_name="id-test",
            enable_similarity=False,
        )
        assert isinstance(sid, int)
        assert sid > 0

        # Wait for completion
        import time
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if api.get_scan_progress()["phase"] in ("complete", "stopped"):
                break
            time.sleep(0.05)
