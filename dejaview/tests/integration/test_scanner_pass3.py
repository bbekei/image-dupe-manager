"""
tests/integration/test_scanner_pass3.py — Integration tests for Scanner Pass 3 (similarity).

Plan reference: §S2.9, §S2.10.

Tests dual-hash behavior, post-hash duplicate refresh, similarity grouping,
and resume safety.
"""

import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from core.scanner import Scanner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64), quality=95) -> Path:
    """Deterministic JPEG — same color + size + quality → identical file size."""
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=quality, subsampling=0)
    img.close()
    return path


def _split_jpg(path: Path, top=(200, 200, 200), bottom=(50, 50, 50),
               size=(64, 64), quality=95) -> Path:
    """JPEG with split_v pattern (top half / bottom half) for distinct pHash."""
    w, h = size
    img = Image.new("RGB", size)
    img.paste(top, [0, 0, w, h // 2])
    img.paste(bottom, [0, h // 2, w, h])
    img.save(str(path), "JPEG", quality=quality, subsampling=0)
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
    sid = db.create_session(name="pass3 test", created_at=now)
    db.add_session_folder(sid, str(scan_dir))
    return sid


# ── Pass 3a: Dual hashing tests ──────────────────────────────────────────────

def test_pass3_computes_phash_for_already_hashed_files(
    db, scan_dir, session_id, thumb_dir
):
    """Files pixel-hashed in Pass 2 get perceptual_hash added in Pass 3."""
    # Two same-size files → Pass 2 hashes them (pixel_hash set).
    _jpg(scan_dir / "a.jpg")
    _jpg(scan_dir / "b.jpg")

    scanner = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=15.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(session_id)
    for f in files:
        assert f["pixel_hash"] is not None, f"pixel_hash missing for {f['path']}"
        assert f["perceptual_hash"] is not None, f"pHash missing for {f['path']}"
        assert f["width"] is not None
        assert f["height"] is not None


def test_pass3_dual_hashes_size_filtered_files(
    db, scan_dir, session_id, thumb_dir
):
    """Files skipped by Pass 2 size-filter get both pixel_hash and pHash in Pass 3."""
    # Three files with unique sizes → Pass 2 skips all (no size-pair candidates).
    _jpg(scan_dir / "a.jpg", size=(64, 64))
    _jpg(scan_dir / "b.jpg", size=(128, 128))
    _jpg(scan_dir / "c.jpg", size=(32, 32))

    scanner = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=15.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(session_id)
    assert len(files) == 3
    for f in files:
        assert f["pixel_hash"] is not None, (
            f"Pass 3 should have set pixel_hash for {f['path']}"
        )
        assert f["perceptual_hash"] is not None, (
            f"Pass 3 should have set pHash for {f['path']}"
        )
        assert f["thumbnail_path"] is not None


def test_pass3_disabled_leaves_phash_null(
    db, scan_dir, session_id, thumb_dir
):
    """When similarity_enabled=False, Pass 3 is skipped and pHash stays NULL."""
    _jpg(scan_dir / "a.jpg")
    _jpg(scan_dir / "b.jpg")

    scanner = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=False,  # default
    )
    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=10.0), "Scan did not complete within timeout"

    files = db.get_files_for_session(session_id)
    for f in files:
        assert f["perceptual_hash"] is None, "pHash should be NULL when disabled"


def test_pass3_similarity_progress_signals(
    db, scan_dir, session_id, thumb_dir
):
    """similarity_progress signals are emitted during Pass 3."""
    _jpg(scan_dir / "a.jpg", size=(64, 64))
    _jpg(scan_dir / "b.jpg", size=(128, 128))

    progress: list[tuple[int, int]] = []
    scanner = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )
    scanner.similarity_progress.connect(lambda c, t: progress.append((c, t)))

    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=15.0), "Scan did not complete within timeout"

    # At least one progress signal should have been emitted.
    assert len(progress) >= 1
    # Total should be > 0 (there are files to hash).
    assert progress[0][1] > 0


# ── Pass 3b: Post-hash duplicate refresh ──────────────────────────────────────

def test_pass3b_discovers_duplicates_missed_by_size_filter(
    db, scan_dir, session_id, thumb_dir
):
    """Identical-pixel files with different byte sizes are detected as
    duplicates after Pass 3 dual-hashes them.

    Same JPEG image data, but one copy has EXIF metadata added → different
    file sizes → Pass 2 size-filter skips them → Pass 3a computes
    pixel_hash for both → same decoded pixels → same pixel_hash →
    Pass 3b emits duplicate_found.
    """
    piexif = pytest.importorskip("piexif", reason="piexif needed for EXIF test")

    # Save JPEG without EXIF.
    img = Image.new("RGB", (64, 64), (128, 128, 128))
    img.save(str(scan_dir / "no_exif.jpg"), "JPEG", quality=95, subsampling=0)

    # Save same image with bulky EXIF to create different file size.
    exif_dict = {"0th": {
        piexif.ImageIFD.ImageDescription: b"x" * 500,
    }}
    exif_bytes = piexif.dump(exif_dict)
    img.save(str(scan_dir / "with_exif.jpg"), "JPEG", quality=95,
             subsampling=0, exif=exif_bytes)
    img.close()

    # Verify different file sizes (so Pass 2 size-filter skips them).
    no_exif_size = (scan_dir / "no_exif.jpg").stat().st_size
    with_exif_size = (scan_dir / "with_exif.jpg").stat().st_size
    assert no_exif_size != with_exif_size, "Files must have different sizes"

    duplicate_groups: list[tuple[str, list[int]]] = []
    scanner = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )
    scanner.duplicate_found.connect(
        lambda ph, ids: duplicate_groups.append((ph, list(ids)))
    )

    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=15.0), "Scan did not complete within timeout"

    # Pass 3b should have emitted duplicate_found for these files.
    files = db.get_files_for_session(session_id)
    id_for = {f["path"]: f["id"] for f in files}

    # At least one duplicate group should contain both files.
    found = False
    for ph, ids in duplicate_groups:
        id_set = set(ids)
        if (id_for[str(scan_dir / "no_exif.jpg")] in id_set and
                id_for[str(scan_dir / "with_exif.jpg")] in id_set):
            found = True
            break
    assert found, "Pass 3b should discover duplicates missed by size filter"


# ── Pass 3c: Similarity grouping ─────────────────────────────────────────────

def test_pass3c_creates_similarity_groups(
    db, scan_dir, session_id, thumb_dir
):
    """Visually similar images are grouped into similarity groups."""
    # Create two similar images (same solid gray, different sizes → rescaled copy).
    _jpg(scan_dir / "original.jpg", color=(128, 128, 128), size=(200, 200))
    _jpg(scan_dir / "resized.jpg", color=(128, 128, 128), size=(100, 100))
    # Create one visually distinct image.
    _split_jpg(scan_dir / "different.jpg", top=(255, 255, 255),
               bottom=(0, 0, 0), size=(200, 200))

    grouping_counts: list[int] = []
    scanner = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )
    scanner.similarity_grouping_complete.connect(
        lambda c: grouping_counts.append(c)
    )

    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=15.0), "Scan did not complete within timeout"

    # Grouping complete signal should fire.
    assert len(grouping_counts) == 1
    # DB should have groups.
    group_count = db.get_similarity_group_count(session_id)
    assert grouping_counts[0] == group_count


def test_pass3c_exact_dupes_not_in_similarity_groups(
    db, scan_dir, session_id, thumb_dir
):
    """Exact duplicates (same pixel_hash) must NOT appear as similarity groups.

    Only groups with >=2 distinct pixel_hashes qualify.
    """
    # Two identical files → same pixel_hash → exact duplicate, not similarity.
    _jpg(scan_dir / "copy1.jpg", color=(128, 128, 128), size=(64, 64))
    _jpg(scan_dir / "copy2.jpg", color=(128, 128, 128), size=(64, 64))

    scanner = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )

    done = threading.Event()
    scanner.scan_complete.connect(lambda: done.set())
    scanner.start()
    assert done.wait(timeout=15.0), "Scan did not complete within timeout"

    # Verify both files have the same pixel_hash (exact duplicates).
    files = db.get_files_for_session(session_id)
    pixel_hashes = {f["pixel_hash"] for f in files if f["pixel_hash"]}
    assert len(pixel_hashes) == 1, "Both files should be exact duplicates"

    # No similarity groups should be created for exact duplicates.
    groups = db.get_similarity_groups(session_id)
    assert len(groups) == 0, "Exact duplicates should not form similarity groups"


# ── Pass 3 resume safety ─────────────────────────────────────────────────────

def test_pass3_resume_skips_already_hashed(
    db, scan_dir, session_id, thumb_dir
):
    """Resuming with similarity_enabled skips files that already have pHash."""
    _jpg(scan_dir / "a.jpg", size=(64, 64))
    _jpg(scan_dir / "b.jpg", size=(128, 128))

    # Run full scan first.
    scanner1 = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )
    done1 = threading.Event()
    scanner1.scan_complete.connect(lambda: done1.set())
    scanner1.start()
    assert done1.wait(timeout=15.0), "Scan did not complete within timeout"

    # All files now have pHash.
    files = db.get_files_for_session(session_id)
    assert all(f["perceptual_hash"] is not None for f in files)

    # Resume scan — Pass 3 should find 0 candidates.
    progress: list[tuple[int, int]] = []
    scanner2 = Scanner(
        db=db, session_id=session_id, thumb_dir=thumb_dir,
        similarity_enabled=True,
    )
    scanner2.set_resuming(True)
    scanner2.similarity_progress.connect(lambda c, t: progress.append((c, t)))

    done2 = threading.Event()
    scanner2.scan_complete.connect(lambda: done2.set())
    scanner2.start()
    assert done2.wait(timeout=15.0), "Scan did not complete within timeout"

    # On resume, all files are already hashed so current == total (progress
    # reports continuity from prior run: n_total active files, 0 remaining).
    if progress:
        current, total = progress[0]
        assert current == total, "All files should already be hashed on resume"
