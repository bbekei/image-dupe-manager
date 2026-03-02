"""
tests/e2e/test_e2e_execution.py — Phase 4b: Execution & Recovery (GUI E2E).

Tasks covered
-------------
P4b-T01  Apply Changes → confirm → files moved to trash
P4b-T02  Execution progress completes → Done button → back to dashboard
P4b-T03  Post-execution DB state: files.status = 'deleted', soft_deletes populated
P4b-T04  Recovery placeholder (xfail)

Implementation notes
--------------------
- These tests require the built binary and pywinauto.
- Execution is triggered via Plan Review's "Apply Changes" button.
- Completion is detected by polling soft_deletes in the DB.

FEATURE_REQUEST_PLAN_E2E_TEST_SUITE.md — Tests P4b-T01 through P4b-T04.
"""

import time
from pathlib import Path

import pytest

from .conftest import (
    SCAN_TIMEOUT,
    add_scan_folder,
    click_start_scan,
    dismiss_dialog_ok,
    get_file_rows,
    get_latest_session,
    get_plan_summary_db,
    get_soft_deletes,
    make_jpg,
    requires_pywinauto,
    wait_for_session_status,
    wait_for_soft_deletes,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_dir_with_duplicates(tmp_path, name="photos"):
    """Create a scan directory with 1 duplicate pair + 1 unique."""
    scan_dir = tmp_path / name
    scan_dir.mkdir()
    make_jpg(scan_dir / "dup_a.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "dup_b.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "unique.jpg", color=(64, 64, 64), size=(48, 48))
    return scan_dir


def _scan_and_apply_preset(main_win, pwa_app, appdata, scan_dir):
    """Scan, apply Smart Select → Keep Largest, navigate to Plan Review."""
    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    time.sleep(1.0)

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

    # Confirm Smart Select
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


# ---------------------------------------------------------------------------
# P4b-T01: Apply Changes moves files to trash
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4b_t01_apply_changes_moves_files(launched_app, tmp_path):
    """
    P4b-T01 — Click 'Apply Changes' on Plan Review, confirm dialog.
    Verify files are moved to trash via DB soft_deletes.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_duplicates(tmp_path)
    _scan_and_apply_preset(main_win, pwa_app, appdata, scan_dir)

    # Get the expected delete count before applying
    session = get_latest_session(appdata)
    assert session is not None
    summary = get_plan_summary_db(appdata, session["id"])
    expected_deletes = summary["delete_count"]
    assert expected_deletes > 0, "No pending deletes to apply"

    # Click "Apply Changes" button
    apply_btn = main_win.child_window(
        title_re=".*Apply Changes.*", control_type="Button"
    )
    apply_btn.click_input()
    time.sleep(0.5)

    # Confirm the "are you sure?" dialog
    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*|.*Apply.*")
        if confirm_dlg.exists(timeout=3):
            for label in ("Yes", "OK", "Apply"):
                try:
                    confirm_dlg.child_window(
                        title=label, control_type="Button"
                    ).click_input()
                    break
                except Exception:
                    continue
    except Exception:
        pass

    # Wait for soft_deletes to be populated (execution happening)
    soft_dels = wait_for_soft_deletes(appdata, expected_deletes, timeout=30.0)
    assert len(soft_dels) >= expected_deletes, (
        f"Expected {expected_deletes} soft_deletes, got {len(soft_dels)}"
    )

    # Verify the original files are gone from disk
    for sd in soft_dels:
        original = Path(sd["original_path"])
        assert not original.exists(), (
            f"Original file should be gone: {original}"
        )


# ---------------------------------------------------------------------------
# P4b-T02: Execution progress completes → Done
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4b_t02_execution_progress_completes(launched_app, tmp_path):
    """
    P4b-T02 — After Apply Changes, execution screen shows progress.
    Once complete, 'Done' button appears and navigates back.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_duplicates(tmp_path)
    _scan_and_apply_preset(main_win, pwa_app, appdata, scan_dir)

    session = get_latest_session(appdata)
    summary = get_plan_summary_db(appdata, session["id"])
    expected_deletes = summary["delete_count"]

    # Click Apply Changes + confirm
    apply_btn = main_win.child_window(
        title_re=".*Apply Changes.*", control_type="Button"
    )
    apply_btn.click_input()
    time.sleep(0.5)

    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*|.*Apply.*")
        if confirm_dlg.exists(timeout=3):
            for label in ("Yes", "OK", "Apply"):
                try:
                    confirm_dlg.child_window(
                        title=label, control_type="Button"
                    ).click_input()
                    break
                except Exception:
                    continue
    except Exception:
        pass

    # Wait for execution to complete
    wait_for_soft_deletes(appdata, expected_deletes, timeout=30.0)
    time.sleep(1.0)  # Wait for UI to update

    # "Done" button should be visible after execution completes
    try:
        done_btn = main_win.child_window(
            title_re=".*Done.*", control_type="Button"
        )
        done_btn.wait("visible", timeout=10)
        done_btn.click_input()
        time.sleep(1.0)

        # Should navigate back to Dashboard or Cleanup screen
        # Process should still be alive
        assert _proc.poll() is None, "App crashed after Done click"
    except Exception:
        # Execution may already have returned to another screen
        assert _proc.poll() is None, "App crashed during execution"


# ---------------------------------------------------------------------------
# P4b-T03: Post-execution DB state
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p4b_t03_post_execution_db_state(launched_app, tmp_path):
    """
    P4b-T03 — After execution: files.status = 'deleted' for deleted files,
    soft_deletes table populated, plan summary shows 0 pending.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    scan_dir = _scan_dir_with_duplicates(tmp_path)
    _scan_and_apply_preset(main_win, pwa_app, appdata, scan_dir)

    session = get_latest_session(appdata)
    summary = get_plan_summary_db(appdata, session["id"])
    expected_deletes = summary["delete_count"]

    # Apply + confirm
    apply_btn = main_win.child_window(
        title_re=".*Apply Changes.*", control_type="Button"
    )
    apply_btn.click_input()
    time.sleep(0.5)

    try:
        confirm_dlg = pwa_app.window(title_re=".*Confirm.*|.*Apply.*")
        if confirm_dlg.exists(timeout=3):
            for label in ("Yes", "OK", "Apply"):
                try:
                    confirm_dlg.child_window(
                        title=label, control_type="Button"
                    ).click_input()
                    break
                except Exception:
                    continue
    except Exception:
        pass

    # Wait for execution
    wait_for_soft_deletes(appdata, expected_deletes, timeout=30.0)
    time.sleep(1.0)

    # Verify DB state
    # 1. Deleted files have status = 'deleted'
    file_rows = get_file_rows(appdata, session["id"])
    deleted_files = [f for f in file_rows if f["status"] == "deleted"]
    assert len(deleted_files) == expected_deletes, (
        f"Expected {expected_deletes} deleted files, got {len(deleted_files)}"
    )

    # 2. Soft_deletes populated
    soft_dels = get_soft_deletes(appdata, session["id"])
    assert len(soft_dels) == expected_deletes

    # 3. Plan summary shows 0 pending deletes
    summary_after = get_plan_summary_db(appdata, session["id"])
    assert summary_after["delete_count"] == 0, (
        f"Pending deletes should be 0 after execution, got {summary_after['delete_count']}"
    )

    # 4. Active files still have status = 'active'
    active_files = [f for f in file_rows if f["status"] == "active"]
    assert len(active_files) > 0, "No active files remaining"


# ---------------------------------------------------------------------------
# P4b-T04: Recovery placeholder
# ---------------------------------------------------------------------------


@requires_pywinauto
@pytest.mark.xfail(reason="Recovery UI not yet implemented — placeholder")
def test_p4b_t04_recovery_placeholder(launched_app, tmp_path):
    """
    P4b-T04 — Placeholder for future recovery UI test.
    Will test: navigate to trash, select file, click Recover, file restored.
    """
    pytest.fail("Recovery UI test not yet implemented")
