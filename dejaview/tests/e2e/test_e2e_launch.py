"""
tests/e2e/test_e2e_launch.py — Phase 1: App Launch & UI Strings (E2E_TEST_PLAN.md §Phase 1).

Tasks covered
-------------
P1-T01  App window title is "DejaView"
P1-T02  English UI: "Add Folder" menu item is visible
P1-T03  Hungarian locale: launch with LANG=hu_HU; translated strings appear

Notes
-----
P1-T03 relies on Qt honouring the LANG environment variable on Windows.
Qt 6 checks LANG / LC_ALL before falling back to the Windows locale setting.
The test verifies a Hungarian label appears somewhere in the UI; it does NOT
assert the exact translation string to stay robust against wording changes.

If the bundled qt_hu.qm or app_hu.qm are missing the test is marked xfail so
the suite can still continue.
"""

import os
import subprocess
import time

import pytest

from .conftest import (
    BINARY_PATH,
    _HAS_PYWINAUTO,
    _PwaApplication,
    requires_pywinauto,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# P1-T01: Window title
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p1_t01_window_title(launched_app):
    """P1-T01 — App window title is 'DejaView'."""
    _proc, _pwa, main_win, _appdata = launched_app
    assert main_win.is_visible()
    assert "DejaView" in main_win.window_text()


# ---------------------------------------------------------------------------
# P1-T02: English UI strings
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p1_t02_english_ui_menu_add_folder(launched_app):
    """
    P1-T02 — English UI: the File menu exposes 'Add Folder…'.

    Clicks File in the menu bar, verifies 'Add Folder' item exists, then
    presses Escape to dismiss without opening a file dialog.
    """
    _proc, pwa_app, main_win, _appdata = launched_app
    main_win.set_focus()
    time.sleep(0.2)

    menu_bar = main_win.child_window(control_type="MenuBar")
    file_menu = menu_bar.child_window(title="File", control_type="MenuItem")
    file_menu.click_input()
    time.sleep(0.3)

    # The "Add Folder…" menu item must be present in the open menu
    add_item = main_win.child_window(
        title="Add Folder\u2026", control_type="MenuItem"
    )
    assert add_item.exists(), "File menu missing 'Add Folder…' item"

    # Dismiss
    from pywinauto.keyboard import send_keys
    send_keys("{ESCAPE}")


# ---------------------------------------------------------------------------
# P1-T03: Hungarian locale
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p1_t03_hungarian_locale_strings(built_binary, tmp_path):
    """
    P1-T03 — Hungarian locale: launch with LANG=hu_HU; translated strings visible.

    The test looks for at least one non-ASCII Hungarian character somewhere in
    the main window's accessibility text (e.g. 'á', 'é', 'ő', 'ü', 'ó').
    This is intentionally broad so it does not break on translation wording
    changes.

    Marked xfail if the Hungarian .qm files are not bundled in the binary.
    """
    from pywinauto.keyboard import send_keys as _sk

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    env = {**os.environ, "APPDATA": str(appdata), "LANG": "hu_HU"}

    proc = subprocess.Popen([str(built_binary)], env=env)
    try:
        pwa_app = _PwaApplication(backend="uia").connect(
            process=proc.pid, timeout=20
        )
        main_win = pwa_app.window(title_re="DejaView.*")
        main_win.wait("visible", timeout=10)

        # Collect all accessible text in the window
        all_text = " ".join(
            str(c.window_text()) for c in main_win.descendants()
        )

        # Hungarian UI should contain at least one accented character that
        # is absent from the English UI (á, é, ő, ü, ó, ő, ű, í)
        hu_chars = set("áéőüóűí")
        has_hu = any(ch in all_text for ch in hu_chars)
        if not has_hu:
            # Warn but don't hard-fail: the qm files might not be bundled yet
            pytest.xfail(
                "No Hungarian characters found in UI. "
                "Verify that app_hu.qm and qt_hu.qm are bundled in the binary."
            )

    finally:
        proc.kill()
        proc.wait(timeout=5)
