"""
tests/integration/test_scanner_pass2.py — Integration tests for Scanner Pass 2 (hashing).

Plan §Integration Tests: test_scanner_pass2.py

Tests the size-filter pre-screening, duplicate detection signals, thumbnail storage,
and progress signal monotonicity.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from core.scanner import Scanner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    """Deterministic JPEG — same color + size + quality → identical file size."""
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
    sid = db.create_session(name="pass2 test", created_at=now)
    db.add_session_folder(sid, str(scan_dir))
    return sid


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_only_size_duplicate_candidates_are_hashed(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_only_size_duplicate_candidates_are_hashed
    # Two same-size JPEGs (64×64) are size-pair candidates → hashed in Pass 2.
    # Two unique-size JPEGs are not candidates → pixel_hash stays NULL.
    a = _jpg(scan_dir / "a.jpg", size=(64, 64))
    b = _jpg(scan_dir / "b.jpg", size=(64, 64))   # identical bytes → same size as a
    c = _jpg(scan_dir / "c.jpg", size=(128, 128))  # larger → unique size
    d = _jpg(scan_dir / "d.jpg", size=(32, 32))    # smaller → unique size

    # Sanity: verify our size assumptions hold before the test proceeds.
    assert a.stat().st_size == b.stat().st_size, "a and b must be same size"
    assert c.stat().st_size != a.stat().st_size
    assert d.stat().st_size != a.stat().st_size
    assert c.stat().st_size != d.stat().st_size

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    files = db.get_files_for_session(session_id)
    hashed = {f["path"] for f in files if f["pixel_hash"] is not None}
    unhashed = {f["path"] for f in files if f["pixel_hash"] is None}

    assert str(a) in hashed
    assert str(b) in hashed
    assert str(c) in unhashed
    assert str(d) in unhashed


def test_badge_signal_emitted_for_confirmed_duplicate(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_badge_signal_emitted_for_confirmed_duplicate
    # Two files with identical pixel content → same pixel_hash → duplicate_found signal.
    a = _jpg(scan_dir / "a.jpg")   # default gray 64×64
    b = _jpg(scan_dir / "b.jpg")   # identical content → same pixel_hash

    assert a.stat().st_size == b.stat().st_size, "files must be same size to be hashed"

    duplicate_groups: list[list[int]] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.duplicate_found.connect(lambda ids: duplicate_groups.append(list(ids)))

    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    # At least one duplicate_found signal must have been emitted.
    assert len(duplicate_groups) >= 1
    # The final group must include file ids for both a and b.
    files = db.get_files_for_session(session_id)
    id_for = {f["path"]: f["id"] for f in files}
    final_group = duplicate_groups[-1]
    assert id_for[str(a)] in final_group
    assert id_for[str(b)] in final_group


def test_unique_file_never_emits_duplicate_signal(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_unique_file_never_emits_duplicate_signal
    # Three files with different dimensions → three different file sizes → no size-pair
    # candidates → Pass 2 hashes nothing → duplicate_found signal never emitted.
    _jpg(scan_dir / "a.jpg", size=(60, 60))
    _jpg(scan_dir / "b.jpg", size=(70, 70))
    _jpg(scan_dir / "c.jpg", size=(80, 80))

    duplicates_seen: list = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.duplicate_found.connect(lambda ids: duplicates_seen.extend(ids))

    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    assert duplicates_seen == []


def test_thumbnail_path_stored_in_db(qtbot, db, scan_dir, session_id, thumb_dir):
    # Plan §Integration Tests: test_thumbnail_path_stored_in_db
    # After a successful hash, thumbnail_path must be non-NULL and the file must exist.
    a = _jpg(scan_dir / "a.jpg")
    b = _jpg(scan_dir / "b.jpg")   # same size → both hashed
    assert a.stat().st_size == b.stat().st_size

    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    files = db.get_files_for_session(session_id)
    hashed = [f for f in files if f["pixel_hash"] is not None]
    assert len(hashed) == 2
    for f in hashed:
        assert f["thumbnail_path"] is not None
        assert Path(f["thumbnail_path"]).exists()


def test_progress_signals_advance_monotonically(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    # Plan §Integration Tests: test_progress_signals_advance_monotonically
    # Three same-size JPEGs → all three are size-pair candidates → all hashed.
    # progress_updated(current, total) must be non-decreasing in 'current'.
    for i in range(3):
        _jpg(scan_dir / f"img{i}.jpg")

    progress: list[tuple[int, int]] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.progress_updated.connect(lambda c, t: progress.append((c, t)))

    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    assert len(progress) >= 1
    currents = [p[0] for p in progress]
    assert currents == sorted(currents), "progress 'current' values must be non-decreasing"
    # All totals must be non-negative.
    assert all(t >= 0 for _, t in progress)


# ── Directory-batched hashing tests ──────────────────────────────────────────

def test_directory_hashed_signal_emitted_per_directory(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    """directory_hashed fires once per directory that contains candidates."""
    sub_a = scan_dir / "sub_a"
    sub_b = scan_dir / "sub_b"
    sub_a.mkdir()
    sub_b.mkdir()

    # Same-size files in two different directories.
    _jpg(sub_a / "a1.jpg")
    _jpg(sub_a / "a2.jpg")
    _jpg(sub_b / "b1.jpg")
    _jpg(sub_b / "b2.jpg")

    dirs_hashed: list[str] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.directory_hashed.connect(lambda d: dirs_hashed.append(d))

    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    assert set(dirs_hashed) == {str(sub_a), str(sub_b)}


def test_directories_processed_leaf_first(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    """Both parent and child directories are hashed; leaf-first submission
    order is preserved but completion order is nondeterministic with the
    sliding-window pipeline (files from multiple dirs are in flight
    simultaneously)."""
    parent = scan_dir / "parent"
    child = parent / "child"
    parent.mkdir()
    child.mkdir()

    # All same-size files so all are candidates.
    _jpg(parent / "p1.jpg")
    _jpg(parent / "p2.jpg")
    _jpg(child / "c1.jpg")
    _jpg(child / "c2.jpg")

    dirs_hashed: list[str] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.directory_hashed.connect(lambda d: dirs_hashed.append(d))

    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    assert len(dirs_hashed) == 2
    # Both directories must be hashed (order is nondeterministic).
    assert set(dirs_hashed) == {str(child), str(parent)}


def test_progress_remains_global_across_directory_batches(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    """Progress current/total stays global across directory batches."""
    sub_a = scan_dir / "a"
    sub_b = scan_dir / "b"
    sub_a.mkdir()
    sub_b.mkdir()

    _jpg(sub_a / "a1.jpg")
    _jpg(sub_a / "a2.jpg")
    _jpg(sub_b / "b1.jpg")
    _jpg(sub_b / "b2.jpg")

    progress: list[tuple[int, int]] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.progress_updated.connect(lambda c, t: progress.append((c, t)))

    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    # Total should be consistent (4 candidates).
    totals = {t for _, t in progress}
    assert totals == {4}

    # current should go 0..4 monotonically.
    currents = [c for c, _ in progress]
    assert currents == sorted(currents)
    assert currents[-1] == 4


def test_pipeline_hashes_multiple_directories_concurrently(
    qtbot, db, scan_dir, session_id, thumb_dir
):
    """Pipeline submits files from multiple directories simultaneously;
    all directories are hashed and scan completes correctly."""
    dirs = []
    for name in ("d1", "d2", "d3", "d4"):
        d = scan_dir / name
        d.mkdir()
        dirs.append(d)
        _jpg(d / "a.jpg")
        _jpg(d / "b.jpg")

    dirs_hashed: list[str] = []
    scanner = Scanner(db=db, session_id=session_id, thumb_dir=thumb_dir)
    scanner.directory_hashed.connect(lambda d: dirs_hashed.append(d))

    with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
        scanner.start()

    # All 4 directories must receive a directory_hashed signal.
    assert set(dirs_hashed) == {str(d) for d in dirs}
    # All 8 files should be hashed in the DB.
    rows = db.get_unhashed_files_grouped_by_size(session_id)
    assert len(rows) == 0
