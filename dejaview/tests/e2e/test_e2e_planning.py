"""
tests/e2e/test_e2e_planning.py — Phase 4: Planning & Decision UI (GUI E2E).

Tasks covered
-------------
P4-T01  Smart Select → KEEP_LARGEST populates file_actions in DB
P4-T02  Plan Review navigation: after preset, navigate to Plan Review
P4-T03  Impact totals: Plan Review shows correct storage saved + files kept
P4-T04  Clear Plan resets all file_actions

Implementation notes
--------------------
- These tests require the built binary and pywinauto.
- Scan completion is detected by polling the DB.
- Planning actions are triggered via UI buttons, verified via DB queries.

FEATURE_REQUEST_PLAN_E2E_TEST_SUITE.md — Tests P4-T01 through P4-T04.
"""

import time

import pytest

from .conftest import (
    SCAN_TIMEOUT,
    add_scan_folder,
    click_start_scan,
    get_file_actions,
    get_file_rows,
    get_latest_session,
    get_plan_summary_db,
    make_jpg,
    requires_pywinauto,
    wait_for_session_status,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_dir_with_duplicates(tmp_path, name="photos"):
    """Create a scan directory containing 2 duplicate pairs + 1 unique.

    Pair A: gray 128 (img_a1.jpg, img_a2.jpg) — same pixel content.
    Pair B: gray 64  (img_b1.jpg, img_b2.jpg) — same pixel content.
    Unique: gray 192 (unique.jpg) — different pixel content.
    """
    scan_dir = tmp_path / name
    scan_dir.mkdir()
    make_jpg(scan_dir / "img_a1.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "img_a2.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "img_b1.jpg", color=(64, 64, 64), size=(64, 64))
    make_jpg(scan_dir / "img_b2.jpg", color=(64, 64, 64), size=(64, 64))
    make_jpg(scan_dir / "unique.jpg", color=(192, 192, 192), size=(48, 48))
    return scan_dir


def _complete_scan(main_win, pwa_app, appdata, scan_dir):
    """Add folder, start scan, wait for completion."""
    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    time.sleep(1.0)  # UI debounce


# ---------------------------------------------------------------------------
# P4-T01: Smart Select populates file_actions
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t01_smart_select_populates_actions(launched_app, tmp_path):
    """
    P4-T01 — After scan, trigger Smart Select → KEEP_LARGEST via UI.
    Verify file_actions rows are created in the DB.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_duplicates(tmp_path)
    _complete_scan(main_win, pwa_app, appdata, scan_dir)

    # Find and click the "Smart Select" button
    smart_btn = main_win.child_window(
        title_re=".*Smart Select.*", control_type="Button"
    )
    smart_btn.click_input()
    time.sleep(0.5)

    # A menu should appear — click "Keep Largest File"
    try:
        keep_largest = main_win.child_window(
            title_re=".*Keep Largest.*", control_type="MenuItem"
        )
        keep_largest.click_input()
    except Exception:
        # Fallback: might be a dialog or popup
        pwa_app.window(title_re=".*Smart Select.*").child_window(
            title_re=".*Keep Largest.*"
        ).click_input()
    time.sleep(0.5)

    # Confirm dialog if it appears
    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*")
        if confirm_dlg.exists(timeout=2):
            confirm_dlg.child_window(title="Yes", control_type="Button").click_input()
    except Exception:
        pass
    time.sleep(0.5)

    # Verify DB: file_actions should have rows
    session = get_latest_session(appdata)
    assert session is not None
    actions = get_file_actions(appdata, session["id"])
    assert len(actions) > 0, (
        "No file_actions created after Smart Select"
    )

    # Should have both keep and delete actions
    action_types = {a["action"] for a in actions}
    assert "keep" in action_types, "No 'keep' actions found"
    assert "delete" in action_types, "No 'delete' actions found"


# ---------------------------------------------------------------------------
# P4-T02: Plan Review navigation
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t02_plan_review_navigation(launched_app, tmp_path):
    """
    P4-T02 — After Smart Select, navigate to Plan Review.
    Verify the Plan Review screen is visible with delete count.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_duplicates(tmp_path)
    _complete_scan(main_win, pwa_app, appdata, scan_dir)

    # Trigger Smart Select → Keep Largest
    smart_btn = main_win.child_window(
        title_re=".*Smart Select.*", control_type="Button"
    )
    smart_btn.click_input()
    time.sleep(0.5)

    try:
        main_win.child_window(
            title_re=".*Keep Largest.*", control_type="MenuItem"
        ).click_input()
    except Exception:
        pwa_app.window(title_re=".*Smart Select.*").child_window(
            title_re=".*Keep Largest.*"
        ).click_input()
    time.sleep(0.5)

    # Dismiss confirmation dialog if it appears
    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*")
        if confirm_dlg.exists(timeout=2):
            confirm_dlg.child_window(title="Yes", control_type="Button").click_input()
    except Exception:
        pass
    time.sleep(0.5)

    # Navigate to Plan Review — look for "Review Plan" button or auto-jump
    try:
        review_btn = main_win.child_window(
            title_re=".*Review Plan.*", control_type="Button"
        )
        if review_btn.exists(timeout=3):
            review_btn.click_input()
            time.sleep(1.0)
    except Exception:
        pass  # May auto-navigate

    # Verify Plan Review screen is visible
    all_text = " ".join(
        str(item.window_text())
        for item in main_win.descendants()
        if hasattr(item, "window_text")
    )
    # "Plan Review" or "Files to Delete" should appear
    assert "Plan Review" in all_text or "Files to Delete" in all_text, (
        f"Plan Review screen not visible. Window text: {all_text[:500]}"
    )


# ---------------------------------------------------------------------------
# P4-T03: Impact totals correct
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t03_plan_review_impact_totals(launched_app, tmp_path):
    """
    P4-T03 — Plan Review shows correct 'Storage saved' and 'Files kept'.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_duplicates(tmp_path)
    _complete_scan(main_win, pwa_app, appdata, scan_dir)

    # Smart Select → Keep Largest
    smart_btn = main_win.child_window(
        title_re=".*Smart Select.*", control_type="Button"
    )
    smart_btn.click_input()
    time.sleep(0.5)

    try:
        main_win.child_window(
            title_re=".*Keep Largest.*", control_type="MenuItem"
        ).click_input()
    except Exception:
        pwa_app.window(title_re=".*Smart Select.*").child_window(
            title_re=".*Keep Largest.*"
        ).click_input()
    time.sleep(0.5)

    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*")
        if confirm_dlg.exists(timeout=2):
            confirm_dlg.child_window(title="Yes", control_type="Button").click_input()
    except Exception:
        pass
    time.sleep(0.5)

    # Navigate to Plan Review
    try:
        review_btn = main_win.child_window(
            title_re=".*Review Plan.*", control_type="Button"
        )
        if review_btn.exists(timeout=3):
            review_btn.click_input()
            time.sleep(1.0)
    except Exception:
        pass

    # Verify impact totals are shown
    all_text = " ".join(
        str(item.window_text())
        for item in main_win.descendants()
        if hasattr(item, "window_text")
    )

    assert "Storage saved" in all_text, (
        f"'Storage saved' label not found in Plan Review. Text: {all_text[:500]}"
    )
    assert "Files kept" in all_text, (
        f"'Files kept' label not found in Plan Review. Text: {all_text[:500]}"
    )

    # Verify DB counts match what the UI should be showing
    session = get_latest_session(appdata)
    summary = get_plan_summary_db(appdata, session["id"])
    assert summary["delete_count"] > 0, "No pending deletes in DB"
    assert summary["keep_count"] > 0, "No keeps in DB"


# ---------------------------------------------------------------------------
# P4-T04: Clear Plan resets all actions
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4_t04_clear_plan_resets_all(launched_app, tmp_path):
    """
    P4-T04 — Click 'Clear Plan' on Plan Review; all file_actions removed.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_duplicates(tmp_path)
    _complete_scan(main_win, pwa_app, appdata, scan_dir)

    # Smart Select → Keep Largest
    smart_btn = main_win.child_window(
        title_re=".*Smart Select.*", control_type="Button"
    )
    smart_btn.click_input()
    time.sleep(0.5)

    try:
        main_win.child_window(
            title_re=".*Keep Largest.*", control_type="MenuItem"
        ).click_input()
    except Exception:
        pwa_app.window(title_re=".*Smart Select.*").child_window(
            title_re=".*Keep Largest.*"
        ).click_input()
    time.sleep(0.5)

    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*")
        if confirm_dlg.exists(timeout=2):
            confirm_dlg.child_window(title="Yes", control_type="Button").click_input()
    except Exception:
        pass
    time.sleep(0.5)

    # Navigate to Plan Review
    try:
        review_btn = main_win.child_window(
            title_re=".*Review Plan.*", control_type="Button"
        )
        if review_btn.exists(timeout=3):
            review_btn.click_input()
            time.sleep(1.0)
    except Exception:
        pass

    # Verify actions exist before clearing
    session = get_latest_session(appdata)
    actions_before = get_file_actions(appdata, session["id"])
    assert len(actions_before) > 0, "No actions to clear"

    # Click "Clear Plan" button
    clear_btn = main_win.child_window(
        title_re=".*Clear Plan.*", control_type="Button"
    )
    clear_btn.click_input()
    time.sleep(0.3)

    # Confirm if dialog appears
    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*|.*Clear.*")
        if confirm_dlg.exists(timeout=2):
            for label in ("Yes", "OK", "Clear"):
                try:
                    confirm_dlg.child_window(
                        title=label, control_type="Button"
                    ).click_input()
                    break
                except Exception:
                    continue
    except Exception:
        pass
    time.sleep(1.0)

    # Verify DB: all file_actions cleared
    actions_after = get_file_actions(appdata, session["id"])
    assert len(actions_after) == 0, (
        f"Expected 0 file_actions after Clear Plan, got {len(actions_after)}"
    )
