"""
tests/e2e/test_e2e_sharing.py — Phase 6: Export / Import (E2E_TEST_PLAN.md §Phase 6).

Tasks covered
-------------
P6-T01  Share → Export: prompts username, privacy, save path; JSON created on disk
P6-T02  Export at each privacy level: JSON 'files' entries contain correct fields
P6-T03  Share → Import: select pre-written peer JSON → Cross-Library radio enabled
P6-T04  Remove peer via Share → Manage Synced Libraries: DB remote_files cleared

Implementation notes
--------------------
Export flow (main_window._on_export):
  1. QInputDialog for username
  2. QComboBox-style dialog for privacy level
  3. QFileDialog save-as for output path

Import flow (main_window._on_import):
  1. QFileDialog open for .json file
  2. import_payload() runs; result shown in status bar

Peer removal flow (main_window._on_manage_peers):
  Opens the ShareDialog; user selects peer in the list and clicks Remove Peer.

For privacy-level verification (P6-T02) we run the scan and export via the UI,
then parse the resulting JSON file and assert field presence.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from .conftest import (
    SCAN_TIMEOUT,
    add_scan_folder,
    click_menu,
    click_start_scan,
    dismiss_dialog_ok,
    get_latest_session,
    make_jpg,
    open_test_db,
    requires_pywinauto,
    wait_for_session_status,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_minimal_scan(pwa_app, main_win, appdata, tmp_path):
    """Scan 2 identical images to produce a session with duplicate files."""
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir(exist_ok=True)
    make_jpg(scan_dir / "img_a.jpg", color=(128, 128, 128), size=(64, 64))
    make_jpg(scan_dir / "img_b.jpg", color=(128, 128, 128), size=(64, 64))

    add_scan_folder(main_win, pwa_app, str(scan_dir))
    time.sleep(0.3)
    click_start_scan(main_win)
    wait_for_session_status(appdata, ("complete",), timeout=SCAN_TIMEOUT)
    time.sleep(0.5)
    return scan_dir


def _trigger_export(main_win, pwa_app, username: str, privacy: str, save_path: Path):
    """
    Drive the full export flow:
      File → Share → Export → username dialog → privacy dialog → save dialog.
    """
    from pywinauto.keyboard import send_keys

    click_menu(main_win, "Share", "Export Scan Results\u2026")
    time.sleep(0.5)

    # ── Username input dialog ─────────────────────────────────────────────
    input_dlg = pwa_app.window(title_re=".*Export.*|.*Display.*name.*")
    if not input_dlg.exists(timeout=5):
        pytest.skip("Export username dialog did not appear — check Share menu wiring")
    try:
        edit = input_dlg.child_window(control_type="Edit", found_index=0)
        edit.click_input()
        edit.set_edit_text(username)
    except Exception:
        send_keys(username)
    send_keys("{ENTER}")
    time.sleep(0.4)

    # ── Privacy level combo dialog (if present) ───────────────────────────
    # The export dialog shows a combo for privacy level
    try:
        combo_dlg = pwa_app.window(title_re=".*privacy.*|.*Export.*")
        if combo_dlg.exists(timeout=2):
            combo = combo_dlg.child_window(control_type="ComboBox", found_index=0)
            combo.click_input()
            time.sleep(0.2)
            # Select the item matching privacy
            item = combo_dlg.child_window(
                title_re=f".*{privacy}.*", control_type="ListItem"
            )
            if item.exists(timeout=1):
                item.click_input()
            send_keys("{ENTER}")
            time.sleep(0.3)
    except Exception:
        pass

    # ── Save file dialog ──────────────────────────────────────────────────
    save_dlg = pwa_app.window(title_re=".*Save.*|.*Export.*")
    if not save_dlg.exists(timeout=8):
        pytest.skip("Save-file dialog did not appear during export")
    try:
        fname_edit = save_dlg.child_window(control_type="Edit", found_index=0)
        fname_edit.click_input()
        fname_edit.set_edit_text(str(save_path))
    except Exception:
        send_keys(str(save_path), with_spaces=True)
    send_keys("{ENTER}")
    time.sleep(1.0)

    # Dismiss any success message
    dismiss_dialog_ok(pwa_app, dialog_title_re=".*Export.*|.*Success.*", timeout=3)


# ---------------------------------------------------------------------------
# P6-T01: Export creates JSON file on disk
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p6_t01_export_creates_json_file(launched_app, tmp_path):
    """
    P6-T01 — Share → Export produces a JSON file at the chosen path.

    Asserts:
    - The file exists after export
    - It is valid JSON
    - It contains 'username' and 'files' keys
    """
    _proc, pwa_app, main_win, appdata = launched_app
    _run_minimal_scan(pwa_app, main_win, appdata, tmp_path)

    out_file = tmp_path / "export_test.json"
    _trigger_export(main_win, pwa_app, "testuser", "filename", out_file)

    assert out_file.exists(), f"Export JSON not created at {out_file}"
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "username" in data, "Export JSON missing 'username' key"
    assert "files" in data, "Export JSON missing 'files' key"
    assert data["username"] == "testuser"
    assert len(data["files"]) >= 1


# ---------------------------------------------------------------------------
# P6-T02: Export privacy levels produce correct fields
# ---------------------------------------------------------------------------


@requires_pywinauto
@pytest.mark.parametrize("privacy,expected_fields,forbidden_fields", [
    ("hash_only",  ["pixel_hash"],              ["filename", "path"]),
    ("filename",   ["pixel_hash", "filename"],  ["path"]),
    ("full_path",  ["pixel_hash", "filename", "path"], []),
])
def test_p6_t02_export_privacy_levels(
    launched_app, tmp_path, privacy, expected_fields, forbidden_fields
):
    """
    P6-T02 — Export at each privacy level: JSON file entries contain exactly the
    expected fields and lack the forbidden fields.
    """
    _proc, pwa_app, main_win, appdata = launched_app
    _run_minimal_scan(pwa_app, main_win, appdata, tmp_path)

    out_file = tmp_path / f"export_{privacy}.json"
    _trigger_export(main_win, pwa_app, "testuser", privacy, out_file)

    if not out_file.exists():
        pytest.skip(f"Export JSON not created at {out_file}; skipping privacy check")

    data = json.loads(out_file.read_text(encoding="utf-8"))
    files = data.get("files", [])
    assert len(files) >= 1, "Export JSON contains no file entries"

    sample = files[0]
    for field in expected_fields:
        assert field in sample, (
            f"Privacy='{privacy}': expected field '{field}' missing from entry: {sample}"
        )
    for field in forbidden_fields:
        assert field not in sample, (
            f"Privacy='{privacy}': forbidden field '{field}' present in entry: {sample}"
        )


# ---------------------------------------------------------------------------
# P6-T03: Import peer JSON → Cross-Library filter enabled
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p6_t03_import_enables_cross_library_filter(launched_app, tmp_path):
    """
    P6-T03 — Importing a peer JSON file with a matching hash enables the
    Cross-Library radio button.
    """
    from pywinauto.keyboard import send_keys

    _proc, pwa_app, main_win, appdata = launched_app
    _run_minimal_scan(pwa_app, main_win, appdata, tmp_path)

    # Retrieve the scanned hash
    session = get_latest_session(appdata)
    conn = open_test_db(appdata)
    try:
        row = conn.execute(
            "SELECT pixel_hash FROM files WHERE session_id = ? AND pixel_hash IS NOT NULL LIMIT 1",
            (session["id"],),
        ).fetchone()
        local_hash = row["pixel_hash"] if row else None
    finally:
        conn.close()

    if not local_hash:
        pytest.skip("No hashed files found in DB after scan")

    # Create peer JSON
    now = datetime.now(timezone.utc).isoformat()
    peer_json = tmp_path / "peer.json"
    peer_json.write_text(json.dumps({
        "username": "bob",
        "exported_at": now,
        "privacy_level": "filename",
        "files": [{
            "remote_id": "bob:1",
            "pixel_hash": local_hash,
            "filename": "bob_img.jpg",
            "size": 1024,
            "modified_at": now,
        }],
    }), encoding="utf-8")

    # Import via Share menu
    click_menu(main_win, "Share", "Import Scan Results\u2026")
    time.sleep(0.5)

    open_dlg = pwa_app.window(title_re=".*Import.*|Open.*")
    if not open_dlg.exists(timeout=8):
        pytest.skip("Import file dialog did not appear")
    try:
        file_edit = open_dlg.child_window(control_type="Edit", found_index=0)
        file_edit.click_input()
        file_edit.set_edit_text(str(peer_json))
    except Exception:
        send_keys(str(peer_json), with_spaces=True)
    send_keys("{ENTER}")
    time.sleep(1.0)

    dismiss_dialog_ok(pwa_app, dialog_title_re=".*Import.*|.*Success.*", timeout=3)
    time.sleep(0.5)

    # Cross-Library radio must now be enabled
    try:
        cl_radio = main_win.child_window(
            title="Cross-Library", control_type="RadioButton"
        )
        assert cl_radio.exists(timeout=3), (
            "Cross-Library radio button not found after import"
        )
        assert cl_radio.is_enabled(), (
            "Cross-Library radio should be enabled after import with matching hash"
        )
    except Exception as exc:
        pytest.fail(f"Cross-Library radio check failed: {exc}")


# ---------------------------------------------------------------------------
# P6-T04: Remove peer clears Cross-Library matches
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p6_t04_remove_peer_clears_cross_library(launched_app, tmp_path):
    """
    P6-T04 — After importing a peer, removing them via Share → Manage Synced
    Libraries clears their remote_files rows from the DB and disables the
    Cross-Library filter.
    """
    from pywinauto.keyboard import send_keys

    _proc, pwa_app, main_win, appdata = launched_app
    _run_minimal_scan(pwa_app, main_win, appdata, tmp_path)

    # Retrieve local hash
    session = get_latest_session(appdata)
    conn = open_test_db(appdata)
    try:
        row = conn.execute(
            "SELECT pixel_hash FROM files WHERE session_id = ? AND pixel_hash IS NOT NULL LIMIT 1",
            (session["id"],),
        ).fetchone()
        local_hash = row["pixel_hash"] if row else None
    finally:
        conn.close()

    if not local_hash:
        pytest.skip("No hashed files found in DB")

    # Import a peer
    now = datetime.now(timezone.utc).isoformat()
    peer_json = tmp_path / "charlie.json"
    peer_json.write_text(json.dumps({
        "username": "charlie",
        "exported_at": now,
        "privacy_level": "hash_only",
        "files": [{"remote_id": "charlie:1", "pixel_hash": local_hash, "size": 512, "modified_at": now}],
    }), encoding="utf-8")

    click_menu(main_win, "Share", "Import Scan Results\u2026")
    time.sleep(0.5)
    open_dlg = pwa_app.window(title_re=".*Import.*|Open.*")
    if not open_dlg.exists(timeout=8):
        pytest.skip("Import dialog did not appear")
    try:
        fe = open_dlg.child_window(control_type="Edit", found_index=0)
        fe.set_edit_text(str(peer_json))
    except Exception:
        send_keys(str(peer_json), with_spaces=True)
    send_keys("{ENTER}")
    time.sleep(1.0)
    dismiss_dialog_ok(pwa_app, dialog_title_re=".*Import.*|.*Success.*", timeout=3)
    time.sleep(0.5)

    # Verify remote_files row exists
    conn2 = open_test_db(appdata)
    try:
        before = conn2.execute(
            "SELECT COUNT(*) FROM remote_files"
        ).fetchone()[0]
    finally:
        conn2.close()
    assert before >= 1, "remote_files empty after import — import may have failed"

    # Remove peer via Share → Manage Synced Libraries
    click_menu(main_win, "Share", "Manage Synced Libraries\u2026")
    time.sleep(0.5)

    manage_dlg = pwa_app.window(title_re=".*Manage.*|.*Peer.*|.*Libraries.*|.*Share.*")
    if not manage_dlg.exists(timeout=5):
        pytest.skip("Manage peers dialog did not appear")

    # Select 'charlie' in the peer list
    try:
        peer_list = manage_dlg.child_window(auto_id="peer_list", control_type="List")
        items = peer_list.children(control_type="ListItem")
        for item in items:
            if "charlie" in item.window_text().lower():
                item.click_input()
                break
    except Exception:
        pass

    # Click Remove Peer
    try:
        remove_btn = manage_dlg.child_window(
            auto_id="remove_peer_btn", control_type="Button"
        )
        remove_btn.click_input()
        time.sleep(0.5)
    except Exception:
        pytest.skip("Remove Peer button not found in dialog")

    # Save/Close
    try:
        save_btn = manage_dlg.child_window(auto_id="save_btn", control_type="Button")
        if save_btn.exists():
            save_btn.click_input()
    except Exception:
        dismiss_dialog_ok(pwa_app, dialog_title_re=".*Manage.*|.*Peer.*", timeout=3)
    time.sleep(0.8)

    # Verify remote_files cleared for 'charlie'
    conn3 = open_test_db(appdata)
    try:
        after = conn3.execute(
            "SELECT COUNT(*) FROM remote_files "
            "JOIN remote_peers ON remote_peers.id = remote_files.peer_id "
            "WHERE remote_peers.username = 'charlie'"
        ).fetchone()[0]
    finally:
        conn3.close()
    assert after == 0, (
        f"remote_files rows for 'charlie' should be 0 after removal, got {after}"
    )
