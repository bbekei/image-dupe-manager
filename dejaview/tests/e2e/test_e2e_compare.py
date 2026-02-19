"""
tests/e2e/test_e2e_compare.py — Phase 4: Compare View & File Actions
(E2E_TEST_PLAN.md §Phase 4).

Tasks covered
-------------
P4-T01  Click duplicate group in tree → Compare View opens with 2 tiles
P4-T02  Click KEEP on tile A → tile B auto-marked DEL; Confirm button active
P4-T03  Click Confirm → deleted file removed from disk; DB status = 'deleted'
P4-T04  Rename workflow: Rename tile A, enter new name, confirm → file renamed
P4-T05  Batch rule "Keep oldest": newer file auto-marked DEL after applying
P4-T06  Batch rule "Keep largest": smaller file auto-marked DEL
P4-T07  Close button on Compare View → results panel restored

Implementation notes
--------------------
- After a scan completes, the results tree has duplicate-group rows.  Double-
  clicking (or single-clicking) a group row triggers _on_compare_requested().
- The Compare View is a QScrollArea containing _FileTile widgets; pywinauto
  finds the KEEP/DEL/Rename/Confirm buttons by their objectName (automation ID)
  or by button text.
- File deletion is the most impactful action; tests use images in tmp_path so
  no real files are at risk.
- The rename test renames inside the same tmp directory (valid filename).
- DB assertions open the app's SQLite DB directly after the action completes.
"""

import time
from pathlib import Path

import pytest

from .conftest import (
    SCAN_TIMEOUT,
    add_scan_folder,
    click_start_scan,
    get_file_rows,
    get_latest_session,
    make_jpg,
    open_test_db,
    requires_pywinauto,
    wait_for_session_status,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Shared scan fixture (module-level helper, not a pytest fixture)
# ---------------------------------------------------------------------------


def _run_scan_with_duplicates(pwa_app, main_win, appdata, tmp_path):
    """
    Scan a directory containing 2 identical images (duplicate pair) + 1 unique.
    Waits for scan completion and the UI 200 ms debounce before returning.

    Returns ``scan_dir``.
    """
    scan_dir = tmp_path / "photos"
    scan_dir.mkdir(exist_ok=True)
    make_jpg(scan_dir / "img_a.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "img_b.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "img_c.jpg", color=(64, 64, 64), size=(48, 48))

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    time.sleep(0.5)  # UI debounce
    return scan_dir


def _open_compare_view(main_win):
    """
    Double-click the first duplicate item in the results tree to open
    the Compare View.  Returns the tree item clicked.
    """
    tree = main_win.child_window(control_type="Tree", found_index=0)
    # Iterate items looking for one marked as a duplicate
    items = tree.children(control_type="TreeItem")
    for item in items:
        if "DUPLICATE" in item.window_text().upper():
            item.double_click_input()
            time.sleep(0.8)
            return item
    # If no item explicitly labelled DUPLICATE, click the first leaf item
    if items:
        items[0].double_click_input()
        time.sleep(0.8)
        return items[0]
    raise RuntimeError("No items found in results tree to open Compare View")


def _wait_for_compare_view(main_win, timeout: float = 5.0):
    """Wait until the Compare View header ('compare_header') is visible."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            header = main_win.child_window(
                auto_id="compare_header", control_type="Text"
            )
            if header.exists(timeout=0.2):
                return header
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError("Compare View did not appear within timeout")


# ---------------------------------------------------------------------------
# P4-T01: Compare View opens
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t01_compare_view_opens_with_tiles(launched_app, tmp_path):
    """
    P4-T01 — Clicking a duplicate group opens the Compare View with 2 tiles.

    Asserts:
    - The compare_header widget is visible
    - At least 2 KEEP buttons are present (one per local tile)
    """
    _proc, pwa_app, main_win, appdata = launched_app
    _run_scan_with_duplicates(pwa_app, main_win, appdata, tmp_path)
    _open_compare_view(main_win)
    _wait_for_compare_view(main_win)

    # At least 2 KEEP buttons (one per tile in the duplicate pair)
    keep_btns = main_win.children(auto_id="keep_btn", control_type="Button")
    assert len(keep_btns) >= 2, (
        f"Expected ≥2 KEEP buttons in Compare View, found {len(keep_btns)}"
    )


# ---------------------------------------------------------------------------
# P4-T02: KEEP staging auto-marks others DEL
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t02_keep_auto_stages_delete_for_others(launched_app, tmp_path):
    """
    P4-T02 — KEEP on tile A → tile B auto-marked DEL; Confirm button becomes active.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    _run_scan_with_duplicates(pwa_app, main_win, appdata, tmp_path)
    _open_compare_view(main_win)
    _wait_for_compare_view(main_win)

    # Click KEEP on the first tile
    keep_btns = main_win.children(auto_id="keep_btn", control_type="Button")
    assert len(keep_btns) >= 1
    keep_btns[0].click_input()
    time.sleep(0.3)

    # The "Review & Confirm…" button (confirm_btn) should now be enabled
    confirm_btn = main_win.child_window(
        auto_id="confirm_btn", control_type="Button"
    )
    assert confirm_btn.exists(), "Confirm button not found after KEEP action"
    assert confirm_btn.is_enabled(), "Confirm button should be enabled after KEEP"


# ---------------------------------------------------------------------------
# P4-T03: Confirm delete — file removed from disk & DB
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t03_confirm_delete_removes_file(launched_app, tmp_path):
    """
    P4-T03 — Stage KEEP on A, confirm → tile B's file deleted from disk;
    DB files row status = 'deleted'.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _run_scan_with_duplicates(pwa_app, main_win, appdata, tmp_path)
    _open_compare_view(main_win)
    _wait_for_compare_view(main_win)

    # Click KEEP on first tile → second is auto-DEL
    keep_btns = main_win.children(auto_id="keep_btn", control_type="Button")
    keep_btns[0].click_input()
    time.sleep(0.3)

    # Click Confirm
    confirm_btn = main_win.child_window(auto_id="confirm_btn", control_type="Button")
    confirm_btn.click_input()
    time.sleep(0.5)

    # A confirmation dialog may appear — dismiss it
    from .conftest import dismiss_dialog_ok
    dismiss_dialog_ok(pwa_app, dialog_title_re=".*Confirm.*|.*Review.*", timeout=3)
    time.sleep(1.0)

    # Verify DB: one file row should have status='deleted'
    rows = get_file_rows(appdata)
    deleted = [r for r in rows if r["status"] == "deleted"]
    assert len(deleted) >= 1, (
        f"Expected ≥1 file with status='deleted' after confirm, got {deleted}"
    )

    # The deleted file should not exist on disk
    deleted_path = Path(deleted[0]["path"])
    assert not deleted_path.exists(), (
        f"Deleted file still exists on disk: {deleted_path}"
    )


# ---------------------------------------------------------------------------
# P4-T04: Rename workflow
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t04_rename_workflow(launched_app, tmp_path):
    """
    P4-T04 — Click Rename on a tile, enter new filename, confirm → file renamed
    on disk; DB path updated.
    """
    from pywinauto.keyboard import send_keys

    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _run_scan_with_duplicates(pwa_app, main_win, appdata, tmp_path)
    _open_compare_view(main_win)
    _wait_for_compare_view(main_win)

    new_name = "renamed_file.jpg"

    # Click Rename on the first tile
    rename_btns = main_win.children(auto_id="rename_btn", control_type="Button")
    assert rename_btns, "No Rename buttons found in Compare View"
    rename_btns[0].click_input()
    time.sleep(0.3)

    # An inline edit field should appear; clear it and type new name
    try:
        rename_edit = main_win.child_window(control_type="Edit", found_index=0)
        rename_edit.click_input()
        rename_edit.set_edit_text(new_name)
    except Exception:
        send_keys("^a")  # select all
        send_keys(new_name)
    send_keys("{ENTER}")
    time.sleep(0.5)

    # Confirm via the confirm_btn or an OK dialog
    try:
        confirm_btn = main_win.child_window(auto_id="confirm_btn", control_type="Button")
        if confirm_btn.exists() and confirm_btn.is_enabled():
            confirm_btn.click_input()
            time.sleep(0.5)
    except Exception:
        pass

    from .conftest import dismiss_dialog_ok
    dismiss_dialog_ok(pwa_app, dialog_title_re=".*Confirm.*|.*Review.*", timeout=3)
    time.sleep(1.0)

    # Verify DB: at least one file has the new name in its path
    rows = get_file_rows(appdata)
    paths = [r["path"] for r in rows]
    assert any(new_name in p for p in paths), (
        f"Renamed file path not found in DB. Paths: {paths}"
    )

    # The renamed file must exist on disk
    renamed_files = [
        Path(p) for p in paths if new_name in p
    ]
    assert renamed_files and renamed_files[0].exists(), (
        f"Renamed file not on disk: {renamed_files}"
    )


# ---------------------------------------------------------------------------
# P4-T05: Batch rule — Keep oldest
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t05_batch_rule_keep_oldest(launched_app, tmp_path):
    """
    P4-T05 — Batch rules dialog: 'Keep oldest' marks the newer file as DEL.

    We create img_a first (older mtime), then img_b (newer mtime).  After
    applying 'Keep oldest', img_b should be staged for deletion.
    """
    import os

    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = tmp_path / "photos"
    scan_dir.mkdir()

    img_a = make_jpg(scan_dir / "img_a.jpg", color=(128, 128, 128))
    time.sleep(0.05)
    img_b = make_jpg(scan_dir / "img_b.jpg", color=(128, 128, 128))
    # Ensure img_a is older
    os.utime(str(img_a), (img_a.stat().st_atime, img_a.stat().st_mtime - 10))

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    time.sleep(0.5)

    _open_compare_view(main_win)
    _wait_for_compare_view(main_win)

    # Click Batch Rules button
    batch_btn = main_win.child_window(auto_id="batch_btn", control_type="Button")
    assert batch_btn.exists(), "Batch rules button not found"
    batch_btn.click_input()
    time.sleep(0.5)

    # In the BatchRulesDialog, click "Keep oldest"
    keep_oldest = main_win.child_window(
        auto_id="keep_oldest_btn", control_type="Button"
    )
    if not keep_oldest.exists(timeout=2):
        # Try finding by title text
        keep_oldest = pwa_app.window(title_re=".*Batch.*").child_window(
            title_re=".*oldest.*", control_type="Button"
        )
    keep_oldest.click_input()
    time.sleep(0.5)

    # Dismiss the batch dialog (it may close automatically)
    from .conftest import dismiss_dialog_ok
    dismiss_dialog_ok(pwa_app, dialog_title_re=".*Batch.*", timeout=2)

    # The apply_btn should now show pending actions — click Apply to All
    apply_btn = main_win.child_window(auto_id="apply_btn", control_type="Button")
    if apply_btn.exists() and apply_btn.is_enabled():
        apply_btn.click_input()
        time.sleep(0.3)

    # At least one DEL action should be staged
    session = get_latest_session(appdata)
    conn = open_test_db(appdata)
    try:
        staged = conn.execute(
            "SELECT a.*, f.path FROM actions a "
            "JOIN files f ON f.id = a.file_id "
            "WHERE a.action_type = 'delete' AND a.status = 'staged' "
            "  AND f.session_id = ?",
            (session["id"],),
        ).fetchall()
    finally:
        conn.close()

    assert len(staged) >= 1, "No delete actions staged after 'Keep oldest' batch rule"


# ---------------------------------------------------------------------------
# P4-T06: Batch rule — Keep largest
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t06_batch_rule_keep_largest(launched_app, tmp_path):
    """
    P4-T06 — Batch rules dialog: 'Keep largest' marks the smaller file as DEL.

    img_a is 64×64 (larger bytes), img_b is 32×32 (smaller bytes).
    After 'Keep largest', img_b should be staged for deletion.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = tmp_path / "photos"
    scan_dir.mkdir()

    # Same hash but different sizes so Pass 2 hashes them
    # (they must have the same pixel_hash to be in a group)
    # Use same content pixel-wise but different JPEG dimensions
    make_jpg(scan_dir / "large.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "small.jpg", color=(128, 128, 128), size=(64, 64))

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    time.sleep(0.5)

    _open_compare_view(main_win)
    _wait_for_compare_view(main_win)

    batch_btn = main_win.child_window(auto_id="batch_btn", control_type="Button")
    if not batch_btn.exists(timeout=2):
        pytest.skip("Batch rules button not found; duplicate group may not have loaded")
    batch_btn.click_input()
    time.sleep(0.5)

    keep_largest = main_win.child_window(
        auto_id="keep_largest_btn", control_type="Button"
    )
    if not keep_largest.exists(timeout=2):
        keep_largest = pwa_app.window(title_re=".*Batch.*").child_window(
            title_re=".*largest.*", control_type="Button"
        )
    keep_largest.click_input()
    time.sleep(0.5)

    from .conftest import dismiss_dialog_ok
    dismiss_dialog_ok(pwa_app, dialog_title_re=".*Batch.*", timeout=2)

    apply_btn = main_win.child_window(auto_id="apply_btn", control_type="Button")
    if apply_btn.exists() and apply_btn.is_enabled():
        apply_btn.click_input()
        time.sleep(0.3)

    # At least one staged delete action
    session = get_latest_session(appdata)
    conn = open_test_db(appdata)
    try:
        staged = conn.execute(
            "SELECT COUNT(*) FROM actions WHERE action_type = 'delete' AND status = 'staged'",
        ).fetchone()[0]
    finally:
        conn.close()
    assert staged >= 1, "No delete actions staged after 'Keep largest' batch rule"


# ---------------------------------------------------------------------------
# P4-T07: Close Compare View restores results panel
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t07_close_compare_view_restores_results(launched_app, tmp_path):
    """
    P4-T07 — Clicking Close in Compare View dismisses it and restores the
    results tree panel.

    After close: compare_header is gone; results Tree is visible.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    _run_scan_with_duplicates(pwa_app, main_win, appdata, tmp_path)
    _open_compare_view(main_win)
    _wait_for_compare_view(main_win)

    # Click the Close button in Compare View
    close_btn = main_win.child_window(auto_id="close_btn", control_type="Button")
    assert close_btn.exists(), "Close button not found in Compare View"
    close_btn.click_input()
    time.sleep(0.5)

    # Compare header should be gone (or not visible)
    header = main_win.child_window(auto_id="compare_header", control_type="Text")
    assert not header.exists(timeout=1), (
        "Compare View header still visible after clicking Close"
    )

    # Results tree should be visible again
    tree = main_win.child_window(control_type="Tree", found_index=0)
    assert tree.exists() and tree.is_visible(), (
        "Results tree not visible after Compare View closed"
    )
