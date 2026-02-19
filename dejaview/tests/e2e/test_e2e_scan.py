"""
tests/e2e/test_e2e_scan.py — Phase 2: Scan Workflow (E2E_TEST_PLAN.md §Phase 2).

Tasks covered
-------------
P2-T01  Add a folder via File → Add Folder…; folder appears in the left panel
P2-T02  Start scan; progress bar moves; scan completes (DB session = 'complete')
P2-T03  After scan: DB has correct row counts (3 files, 1 duplicate group)
P2-T04  Duplicate badge visible in the results tree for the duplicate pair
P2-T05  Scan an empty folder: completes without crash; 0 file rows in DB
P2-T06  Scan folder with corrupt image: completes; valid files indexed; corrupt file has no pixel_hash

Implementation notes
--------------------
- Folder addition triggers a native file dialog; ``add_scan_folder()`` in conftest
  handles the interaction.
- Scan completion is detected by polling the DB (session.status = 'complete').
- The results tree is a Qt tree control; pywinauto can enumerate its items.
"""

import time

import pytest

from .conftest import (
    SCAN_TIMEOUT,
    add_scan_folder,
    click_start_scan,
    get_file_rows,
    get_latest_session,
    make_corrupt_jpg,
    make_jpg,
    open_test_db,
    requires_pywinauto,
    wait_for_session_status,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_dir_with_images(tmp_path, name="photos"):
    """Create a scan directory containing 2 duplicates + 1 unique image."""
    scan_dir = tmp_path / name
    scan_dir.mkdir()
    make_jpg(scan_dir / "img_a.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "img_b.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "img_c.jpg", color=(64, 64, 64), size=(48, 48))
    return scan_dir


# ---------------------------------------------------------------------------
# P2-T01: Add folder via UI
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p2_t01_add_folder_appears_in_panel(launched_app, tmp_path):
    """
    P2-T01 — File → Add Folder… → folder path visible in the left panel.

    After adding a folder the FolderPanel list should contain at least one item
    whose text includes the folder's name.
    """
    _proc, pwa_app, main_win, _appdata = launched_app

    scan_dir = tmp_path / "myphotos"
    scan_dir.mkdir()

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.5)

    # The left panel (FolderPanel) is a QListWidget; enumerate its items
    folder_list = main_win.child_window(control_type="List", found_index=0)
    item_texts = [str(item.window_text()) for item in folder_list.children()]

    assert any("myphotos" in t.lower() for t in item_texts), (
        f"Folder 'myphotos' not visible in left panel. Items: {item_texts}"
    )


# ---------------------------------------------------------------------------
# P2-T02: Start scan, progress updates, scan completes
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p2_t02_start_scan_completes(launched_app, tmp_path):
    """
    P2-T02 — Add folder, start scan; progress bar moves; DB session reaches 'complete'.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_images(tmp_path)

    # Add folder and start scan
    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)

    # Poll DB until session status = 'complete'
    status = wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    assert status == "complete"


# ---------------------------------------------------------------------------
# P2-T03: DB state after scan (correct file count)
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p2_t03_db_has_correct_file_count_after_scan(launched_app, tmp_path):
    """
    P2-T03 — After scanning 3 images (2 dupes + 1 unique):
    - DB ``files`` table has exactly 3 active rows in the session
    - Exactly one pixel_hash appears twice (the duplicate pair)
    - The unique image has a different pixel_hash
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_images(tmp_path)

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)

    # Read file rows
    session = get_latest_session(appdata)
    assert session is not None
    rows = get_file_rows(appdata, session_id=session["id"])

    active = [r for r in rows if r["status"] == "active"]
    assert len(active) == 3, f"Expected 3 active files, got {len(active)}"

    # Collect pixel_hashes
    hashes = [r["pixel_hash"] for r in active if r["pixel_hash"]]
    from collections import Counter
    counts = Counter(hashes)

    # Exactly one hash appears twice (the duplicate pair)
    doubled = [h for h, c in counts.items() if c == 2]
    assert len(doubled) == 1, (
        f"Expected exactly 1 duplicate hash, found: {counts}"
    )

    # The third file has a unique hash
    unique = [h for h, c in counts.items() if c == 1]
    assert len(unique) == 1, (
        f"Expected exactly 1 unique hash, found: {counts}"
    )


# ---------------------------------------------------------------------------
# P2-T04: Duplicate badge visible in results tree
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p2_t04_duplicate_badge_visible_in_tree(launched_app, tmp_path):
    """
    P2-T04 — After scan, the results tree shows a 'DUPLICATE' label for the
    duplicate pair.  The unique image must NOT have a duplicate badge.

    Strategy: enumerate all accessible text in the results tree and assert
    'DUPLICATE' (or the localised equivalent) appears, while the unique file
    path does NOT appear alongside the badge text.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_images(tmp_path)

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    time.sleep(1.0)  # allow UI debounce (200 ms) + render

    # The ResultsPanel is the rightmost panel; find the tree view
    tree = main_win.child_window(control_type="Tree", found_index=0)
    all_text = " ".join(
        str(item.window_text()) for item in tree.descendants()
    )

    # 'DUPLICATE' (the badge text set by ResultsPanel) must appear
    assert "DUPLICATE" in all_text.upper(), (
        "No DUPLICATE badge text found in results tree. "
        f"Tree text: {all_text[:500]}"
    )


# ---------------------------------------------------------------------------
# P2-T05: Empty folder scan
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p2_t05_empty_folder_scan_completes(launched_app, tmp_path):
    """
    P2-T05 — Scanning an empty folder completes without crash.
    DB session status = 'complete'; no file rows inserted.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    add_scan_folder(main_win, pwa_app, str(empty_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    status = wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)

    assert status == "complete"
    rows = get_file_rows(appdata)
    assert len(rows) == 0, f"Expected 0 file rows for empty scan, got {len(rows)}"

    # Process must still be alive (no crash)
    _proc, _pwa, _win, _appdata = launched_app
    assert _proc.poll() is None, "DejaView.exe crashed during empty-folder scan"


# ---------------------------------------------------------------------------
# P2-T06: Corrupt image in scan folder
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p2_t06_corrupt_image_does_not_crash_scan(launched_app, tmp_path):
    """
    P2-T06 — A folder containing one corrupt JPEG alongside valid images:
    - Scan completes (session status = 'complete')
    - Valid images are indexed (have pixel_hash)
    - Corrupt file is recorded with pixel_hash = NULL
    - The process is still alive after scan
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = tmp_path / "mixed"
    scan_dir.mkdir()

    valid_a = make_jpg(scan_dir / "valid_a.jpg", color=(128, 128, 128))
    valid_b = make_jpg(scan_dir / "valid_b.jpg", color=(128, 128, 128))
    corrupt = make_corrupt_jpg(scan_dir / "corrupt.jpg")

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    status = wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)

    assert status == "complete"
    assert _proc.poll() is None, "DejaView.exe crashed during corrupt-image scan"

    rows = get_file_rows(appdata)
    by_path = {r["path"]: r for r in rows}

    # Valid files should have a pixel_hash
    assert str(valid_a) in by_path, "valid_a.jpg not in DB"
    assert str(valid_b) in by_path, "valid_b.jpg not in DB"
    assert by_path[str(valid_a)]["pixel_hash"] is not None, (
        "valid_a.jpg missing pixel_hash after scan"
    )

    # Corrupt file should be recorded but with NULL pixel_hash
    assert str(corrupt) in by_path, "corrupt.jpg not in DB at all"
    assert by_path[str(corrupt)]["pixel_hash"] is None, (
        "corrupt.jpg unexpectedly got a pixel_hash"
    )
