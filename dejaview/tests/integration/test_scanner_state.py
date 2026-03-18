"""
tests/integration/test_scanner_state.py — Integration tests for Scanner state machine.

Plan §Integration Tests: test_scanner_state.py

Tests the pause / resume / stop / complete lifecycle and crash recovery.

Strategy for pause/stop tests:
  - Files are pre-inserted into the DB so is_resuming=True skips Pass 1.
  - hash_file is patched with a 50 ms sleep so the scanner thread releases the
    Python GIL, giving the main thread time to process the hash_complete signal
    and call pause() / stop() before the next iteration.
  - Scanning 5 same-size files at 50 ms/file → total ~250 ms; the pause/stop
    flag is set after the first hash_complete (~50 ms), so at least 3 files
    remain when the flag is checked.
"""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from core.hasher import hash_file as _real_hash_file
from core.scanner import Scanner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


def _slow_hash(path, thumb_dir):
    """hash_file wrapper with a 50 ms delay; releases GIL during sleep."""
    time.sleep(0.05)
    return _real_hash_file(path, thumb_dir)


def _insert_files(db, session_id, paths):
    """
    Pre-insert file rows for all paths so Pass 1 can be skipped.
    Returns list of file ids in the same order as paths.
    """
    now = datetime.now(timezone.utc).isoformat()
    ids = []
    for p in paths:
        st = p.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        fid = db.insert_file(session_id, str(p), st.st_size, mtime, now)
        ids.append(fid)
    return ids


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def scan_dir(tmp_path):
    d = tmp_path / "scan"
    d.mkdir()
    return d


@pytest.fixture
def session_id(db, scan_dir):
    now = datetime.now(timezone.utc).isoformat()
    sid = db.create_session(name="state test", created_at=now)
    db.add_session_folder(sid, str(scan_dir))
    return sid


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_session_status_set_to_complete_when_scan_finishes_normally(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_session_status_set_to_complete_when_scan_finishes_normally
    for i in range(3):
        _jpg(scan_dir / f"img{i}.jpg")

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    assert db.get_session(session_id)["status"] == "complete"


def test_stop_sets_session_status_to_stopped(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_stop_sets_session_status_to_stopped
    paths = [_jpg(scan_dir / f"img{i}.jpg") for i in range(5)]
    _insert_files(db, session_id, paths)

    with patch("core.scanner.hash_file", side_effect=_slow_hash):
        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        scanner.set_resuming(True)
        # stop() is called from the main thread via the hash_complete signal slot.
        scanner.hash_complete.connect(lambda *_: scanner.stop())

        completed = []
        scanner.scan_complete.connect(lambda: completed.append(True))

        stopped = threading.Event()
        scanner.scan_stopped.connect(lambda: stopped.set())
        scanner.start()
        assert stopped.wait(timeout=10.0), "Scan did not stop within timeout"

    assert db.get_session(session_id)["status"] == "stopped"
    # Stop and complete are mutually exclusive — scan_complete must NOT fire.
    assert completed == []


def test_partial_results_remain_after_stop(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_partial_results_remain_after_stop
    paths = [_jpg(scan_dir / f"img{i}.jpg") for i in range(5)]
    _insert_files(db, session_id, paths)

    with patch("core.scanner.hash_file", side_effect=_slow_hash):
        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        scanner.set_resuming(True)
        scanner.hash_complete.connect(lambda *_: scanner.stop())

        stopped = threading.Event()
        scanner.scan_stopped.connect(lambda: stopped.set())
        scanner.start()
        assert stopped.wait(timeout=10.0), "Scan did not stop within timeout"

    # At least the file that triggered stop() must have a pixel_hash.
    hashed = [
        f for f in db.get_files_for_session(session_id)
        if f["pixel_hash"] is not None
    ]
    assert len(hashed) >= 1


def test_pause_sets_session_status_to_paused(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_pause_sets_session_status_to_paused
    paths = [_jpg(scan_dir / f"img{i}.jpg") for i in range(5)]
    _insert_files(db, session_id, paths)

    with patch("core.scanner.hash_file", side_effect=_slow_hash):
        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        scanner.set_resuming(True)
        scanner.hash_complete.connect(lambda *_: scanner.pause())

        paused = threading.Event()
        scanner.scan_paused.connect(lambda: paused.set())
        scanner.start()
        assert paused.wait(timeout=10.0), "Scan did not pause within timeout"

    status = db.get_session(session_id)["status"]
    assert status == "paused"


def test_pause_stops_thread_after_current_file_completes(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_pause_stops_thread_after_current_file_completes
    # After scan_paused is emitted, the thread must have exited (is_alive() == False).
    paths = [_jpg(scan_dir / f"img{i}.jpg") for i in range(5)]
    _insert_files(db, session_id, paths)

    with patch("core.scanner.hash_file", side_effect=_slow_hash):
        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        scanner.set_resuming(True)
        scanner.hash_complete.connect(lambda *_: scanner.pause())

        paused = threading.Event()
        scanner.scan_paused.connect(lambda: paused.set())
        scanner.start()
        assert paused.wait(timeout=10.0), "Scan did not pause within timeout"

    # The signal is emitted from within run(); give the thread time to exit.
    scanner.join(timeout=2.0)
    assert not scanner.is_alive()


def test_resume_skips_already_hashed_files(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_resume_skips_already_hashed_files
    # 4 same-size images; 2 are pre-hashed. On resume only the 2 NULL-hash files
    # should be processed (verified by counting hash_file() call-through invocations).
    paths = [_jpg(scan_dir / f"img{i}.jpg") for i in range(4)]
    ids = _insert_files(db, session_id, paths)

    # Pre-hash the first two files.
    for i in range(2):
        h, tp, *_ = _real_hash_file(str(paths[i]), str(thumb_dir))
        db.update_pixel_hash(ids[i], h, tp)

    db.update_session_status(session_id, "paused")

    hash_calls: list[str] = []

    def tracking_hash(path, td):
        hash_calls.append(str(path))
        return _real_hash_file(path, td)

    with patch("core.scanner.hash_file", side_effect=tracking_hash):
        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        scanner.set_resuming(True)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()
        assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    # Only paths[2] and paths[3] should have been hashed.
    assert len(hash_calls) == 2
    assert str(paths[2]) in hash_calls
    assert str(paths[3]) in hash_calls
    assert str(paths[0]) not in hash_calls
    assert str(paths[1]) not in hash_calls


def test_resume_skips_pass1_if_files_already_discovered(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_resume_skips_pass1_if_files_already_discovered
    # When is_resuming=True, the scanner must not emit file_discovered (Pass 1 skipped).
    paths = [_jpg(scan_dir / f"img{i}.jpg") for i in range(3)]
    _insert_files(db, session_id, paths)
    db.update_session_status(session_id, "paused")

    discovered: list[int] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.set_resuming(True)
    scanner.file_discovered.connect(lambda fid, p: discovered.append(fid))

    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    assert discovered == [], "Pass 1 must be skipped entirely on resume"


def test_crash_recovery_rehashes_null_hash_files(
    db, scan_dir, session_id, thumb_dir
):
    # Plan: test_crash_recovery_rehashes_null_hash_files
    # Simulate a mid-scan crash: 4 files in DB, only 2 have pixel_hash (crash left 2 NULL).
    # On resume, the 2 NULL-hash files must be re-hashed (idempotent recovery).
    paths = [_jpg(scan_dir / f"img{i}.jpg") for i in range(4)]
    ids = _insert_files(db, session_id, paths)

    # Simulate partial scan: hash only the first 2.
    for i in range(2):
        h, tp, *_ = _real_hash_file(str(paths[i]), str(thumb_dir))
        db.update_pixel_hash(ids[i], h, tp)

    null_ids = set(ids[2:])

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.set_resuming(True)
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    for f in db.get_files_for_session(session_id):
        if f["id"] in null_ids:
            assert f["pixel_hash"] is not None, (
                f"File id={f['id']} was not re-hashed during crash recovery"
            )
