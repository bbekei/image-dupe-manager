"""
tests/integration/test_scanner_pass1.py — Integration tests for Scanner Pass 1 (discovery).

Plan §Integration Tests: test_scanner_pass1.py

Req 4.1 coverage: folder walk inserts all discovered image files into the DB.
Security coverage: symlink/junction guard (plan §Security — symlink guard).
"""

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from core.scanner import Scanner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    """Create a minimal JPEG image at path with fixed quality for deterministic size."""
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def scan_dir(tmp_path):
    d = tmp_path / "scan"
    d.mkdir()
    return d


@pytest.fixture
def session_id(db, scan_dir):
    now = datetime.now(timezone.utc).isoformat()
    sid = db.create_session(name="pass1 test", created_at=now)
    db.add_session_folder(sid, str(scan_dir))
    return sid


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_discovery_pass_inserts_all_files(db, scan_dir, session_id, thumb_dir):
    # Plan §Integration Tests: test_discovery_pass_inserts_all_files
    # Each file gets a unique size (different image dimensions) so that the
    # size pre-filter eliminates all of them from Pass 2 — no hashing occurs.
    for i in range(5):
        _jpg(scan_dir / f"img{i:02d}.jpg", size=(64 + i * 10, 64 + i * 10))

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(session_id)
    assert len(files) == 5
    # No size-duplicates → Pass 2 skips all → pixel_hash stays NULL.
    assert all(f["pixel_hash"] is None for f in files)


def test_discovery_pass_records_correct_path_and_size(
    db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_discovery_pass_records_correct_path_and_size
    img = _jpg(scan_dir / "img.jpg")
    expected_size = img.stat().st_size

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(session_id)
    assert len(files) == 1
    assert files[0]["path"] == str(img)
    assert files[0]["size"] == expected_size


def test_discovery_pass_skips_symlinked_directory(
    db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_discovery_pass_does_not_enter_excluded_dirs
    # Implemented via the symlink/junction guard (plan §Security — symlink guard).
    # os.path.islink() is mocked to return True for the "junction" directory so
    # that this test runs without admin privileges on Windows.
    real_sub = scan_dir / "real"
    real_sub.mkdir()
    _jpg(real_sub / "real.jpg")

    link_sub = scan_dir / "junction"
    link_sub.mkdir()            # physically a real dir…
    _jpg(link_sub / "secret.jpg")   # …but mocked as a symlink below

    orig_islink = os.path.islink

    def mock_islink(path):
        return Path(path).name == "junction" or orig_islink(path)

    with patch("core.scanner.os.path.islink", side_effect=mock_islink):
        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()
        assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(session_id)
    paths = [f["path"] for f in files]
    assert any("real.jpg" in p for p in paths)
    assert not any("secret.jpg" in p for p in paths)


def test_discovery_pass_completes_before_hash_pass_begins(
    db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_discovery_pass_completes_before_hash_pass_begins
    # Three identical JPEGs → same file size → all three become Pass 2 candidates.
    # All file_discovered signals must appear before the first hash_complete signal.
    for i in range(3):
        _jpg(scan_dir / f"img{i}.jpg")

    events: list[str] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.file_discovered.connect(lambda fid, path: events.append("discovered"))
    scanner.hash_complete.connect(lambda fid, h: events.append("hashed"))

    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    # If any hashing happened, every event before the first "hashed" must be "discovered".
    if "hashed" in events:
        first_hash_idx = events.index("hashed")
        assert all(e == "discovered" for e in events[:first_hash_idx])


def test_discovery_pass_handles_empty_folder(
    db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_discovery_pass_handles_empty_folder
    # scan_dir exists but contains no image files — scan must complete without error.
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    assert db.get_files_for_session(session_id) == []


def test_discovery_pass_handles_unreadable_file(
    db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_discovery_pass_handles_unreadable_file
    # os.stat is mocked to raise PermissionError for one file; the scanner must
    # log/signal the error, skip that file, and insert the remaining ones.
    good = _jpg(scan_dir / "good.jpg")
    bad = _jpg(scan_dir / "bad.jpg")

    orig_stat = os.stat

    def mock_stat(path, **kwargs):
        if str(path) == str(bad):
            raise PermissionError("Access denied (mocked)")
        return orig_stat(path, **kwargs)

    errors: list[str] = []
    with patch("core.scanner.os.stat", side_effect=mock_stat):
        scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
        scanner.scan_error.connect(lambda path, msg: errors.append(path))
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()
        assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(session_id)
    paths = [f["path"] for f in files]
    assert str(good) in paths            # good file was inserted
    assert str(bad) not in paths         # bad file was skipped
    assert any(str(bad) in e for e in errors)  # error was signalled
