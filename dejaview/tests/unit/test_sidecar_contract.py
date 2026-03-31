"""
tests/unit/test_sidecar_contract.py — P0 contract tests for sidecar IPC.

Phase 1, Week 2: P0 contract tests using the injectable ListOutput.

Tests the JSON-RPC protocol contracts, event filtering, and scanner
cancellation — the architectural boundaries where production bugs lived.
"""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from sidecar.output import (
    FORWARDED_EVENTS,
    ListOutput,
    StdoutOutput,
    Output,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


# ═════════════════════════════════════════════════════════════════════════════
# Output protocol compliance
# ═════════════════════════════════════════════════════════════════════════════

class TestOutputProtocol:
    """Verify both Output implementations satisfy the protocol."""

    def test_list_output_is_output(self):
        assert isinstance(ListOutput(), Output)

    def test_stdout_output_is_output(self):
        import io
        stream = io.StringIO()
        out = StdoutOutput(stream=stream)
        assert isinstance(out, Output)
        out.shutdown()

    def test_list_output_ok_format(self):
        out = ListOutput()
        out.ok(1, {"key": "value"})
        assert len(out.messages) == 1
        msg = out.messages[0]
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 1
        assert msg["result"] == {"key": "value"}
        assert "error" not in msg

    def test_list_output_err_format(self):
        out = ListOutput()
        out.err(2, -32601, "Method not found")
        msg = out.messages[0]
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 2
        assert msg["error"]["code"] == -32601
        assert msg["error"]["message"] == "Method not found"

    def test_list_output_response_filter(self):
        out = ListOutput()
        out.ok(1, "result1")
        out.notify("scan:progress", {"current": 1, "total": 10})
        out.ok(2, "result2")
        assert len(out.responses) == 2
        assert len(out.events) == 1

    def test_list_output_error_filter(self):
        out = ListOutput()
        out.ok(1, "ok")
        out.err(2, -32700, "parse error")
        assert len(out.errors) == 1
        assert out.errors[0]["id"] == 2


# ═════════════════════════════════════════════════════════════════════════════
# Event filtering contract
# ═════════════════════════════════════════════════════════════════════════════

class TestNotifyFilter:
    """
    P0 contract test: test_notify_filters_non_forwarded_events.

    The sidecar must only forward events in the FORWARDED_EVENTS set.
    Non-forwarded events (e.g. scan:hash_complete, scan:hash_batch) must
    be silently dropped — they were never consumed by the frontend and
    forwarding them wastes pipe bandwidth.
    """

    def test_forwarded_events_pass_through(self):
        out = ListOutput()
        for event in sorted(FORWARDED_EVENTS):
            out.notify(event, {"test": True})
        assert len(out.events) == len(FORWARDED_EVENTS)

    def test_non_forwarded_events_are_dropped(self):
        """Events not in FORWARDED_EVENTS must be silently dropped."""
        out = ListOutput()
        non_forwarded = [
            "scan:hash_complete",
            "scan:hash_batch",
            "scan:directory_hashed",
            "scan:similarity_complete",
            "some:random:event",
            "",
        ]
        for event in non_forwarded:
            out.notify(event, {"test": True})
        assert len(out.events) == 0, (
            f"Non-forwarded events leaked through: {out.events}"
        )

    def test_mixed_forwarded_and_non_forwarded(self):
        """Only forwarded events appear in output."""
        out = ListOutput()
        out.notify("scan:progress", {"current": 1, "total": 10})       # forwarded
        out.notify("scan:hash_complete", {"file_id": 1, "hash": "x"})  # dropped
        out.notify("scan:status", {"status": "complete"})               # forwarded
        out.notify("scan:hash_batch", {"batch": []})                    # dropped
        assert len(out.events) == 2
        assert out.events[0]["params"]["name"] == "scan:progress"
        assert out.events[1]["params"]["name"] == "scan:status"

    def test_notify_event_payload_format(self):
        """Verify the JSON-RPC notification structure."""
        out = ListOutput()
        out.notify("scan:duplicate_found", {"pixel_hash": "abc", "count": 3})
        msg = out.events[0]
        assert msg["jsonrpc"] == "2.0"
        assert "id" not in msg
        assert msg["method"] == "event"
        assert msg["params"]["name"] == "scan:duplicate_found"
        assert msg["params"]["detail"] == {"pixel_hash": "abc", "count": 3}


# ═════════════════════════════════════════════════════════════════════════════
# Scanner stop cancels futures
# ═════════════════════════════════════════════════════════════════════════════

class TestScannerStopCancels:
    """
    P0 contract test: test_scanner_stop_cancels_futures.

    When stop() is called mid-scan, the scanner must:
    1. Cancel in-flight hashing futures (not wait for them to complete).
    2. Flush pending hash updates to DB (so resume works).
    3. Emit scan_stopped signal.
    4. Mark session as 'stopped' in DB.
    """

    def test_stop_during_pass2_cancels_futures(self, db, thumb_dir, tmp_path):
        """Stop mid-hash: scanner exits promptly, session marked stopped."""
        from core.scanner import Scanner

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()

        # Create enough same-size files to trigger Pass 2 hashing
        for i in range(50):
            _jpg(scan_dir / f"img_{i:03d}.jpg", color=(100, 100, 100))

        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="stop test", created_at=now)
        db.add_session_folder(sid, str(scan_dir))

        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)

        stopped = threading.Event()
        completed = threading.Event()
        progress_seen = threading.Event()

        scanner.scan_stopped.connect(lambda: stopped.set())
        scanner.scan_complete.connect(lambda: completed.set())
        scanner.progress_updated.connect(lambda c, t: progress_seen.set())

        scanner.start()

        # Wait for hashing to begin, then stop
        progress_seen.wait(timeout=10.0)
        scanner.stop()

        # Scanner must exit promptly after stop (not wait for all futures)
        assert stopped.wait(timeout=10.0), "Scanner did not emit scan_stopped after stop()"
        assert not completed.is_set(), "Scanner should not emit scan_complete when stopped"

        # Session marked as stopped in DB
        session = db.get_session(sid)
        assert session["status"] == "stopped"

    def test_stop_during_pass1_exits_cleanly(self, db, thumb_dir, tmp_path):
        """Stop during discovery: scanner exits without crashing."""
        from core.scanner import Scanner

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        for i in range(20):
            _jpg(scan_dir / f"img_{i:02d}.jpg", size=(64 + i, 64 + i))

        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="stop pass1", created_at=now)
        db.add_session_folder(sid, str(scan_dir))

        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        stopped = threading.Event()
        scanner.scan_stopped.connect(lambda: stopped.set())
        scanner.scan_complete.connect(lambda: stopped.set())  # either outcome is OK

        scanner.start()
        # Stop immediately — may catch it in Pass 1 or Pass 2
        scanner.stop()

        assert stopped.wait(timeout=10.0), "Scanner did not exit after stop()"

        session = db.get_session(sid)
        assert session["status"] in ("stopped", "complete")
