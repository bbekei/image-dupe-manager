"""
tests/e2e/conftest.py — Fixtures and helpers for E2E binary tests (E2E_TEST_PLAN.md).

Architecture
------------
- built_binary (session-scoped): runs lrelease + pyinstaller once per pytest session.
- app_env (function-scoped): creates an isolated APPDATA directory per test.
- launched_app (function-scoped): launches DejaView.exe, connects pywinauto,
  yields (proc, pwa_app, main_win, appdata_path), kills process on teardown.

Test isolation
--------------
Each test gets its own APPDATA path via tmp_path.  The app resolves its DB and
thumbnail cache as os.environ["APPDATA"]\\DejaView, so injecting APPDATA=<tmp_path>
completely separates tests from the developer's real data.

Tools
-----
- pywinauto (UIA backend): Windows UI Automation — finds Qt widgets by title /
  control-type / automation-id (objectName).
- sqlite3: direct DB assertions without a running Python interpreter.
- PIL: creates synthetic JPEG fixtures.
- subprocess: process lifecycle.
"""

import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Optional pywinauto import — tests skip gracefully if not installed
# ---------------------------------------------------------------------------

try:
    import pywinauto  # noqa: F401
    from pywinauto import Application as _PwaApplication
    from pywinauto.keyboard import send_keys
    _HAS_PYWINAUTO = True
except ImportError:  # pragma: no cover
    _HAS_PYWINAUTO = False
    _PwaApplication = None  # type: ignore[assignment,misc]
    send_keys = None  # type: ignore[assignment]

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Path constants (relative to this file)
# ---------------------------------------------------------------------------

# dejaview/
DEJAVIEW_DIR: Path = Path(__file__).parent.parent.parent

# Compiled binary produced by PyInstaller
BINARY_PATH: Path = DEJAVIEW_DIR / "dist" / "DejaView" / "DejaView.exe"

# Build inputs
_SPEC_PATH: Path    = DEJAVIEW_DIR / "dejaview.spec"
_TS_PATH: Path      = DEJAVIEW_DIR / "resources" / "i18n" / "app_hu.ts"
_QM_PATH: Path      = DEJAVIEW_DIR / "resources" / "i18n" / "app_hu.qm"

# Scan completion timeout (seconds) — generous to handle slow CI machines
SCAN_TIMEOUT: float = 60.0

# ---------------------------------------------------------------------------
# pytest marker registration
# ---------------------------------------------------------------------------


def pytest_configure(config) -> None:  # noqa: D401
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests that build and exercise the compiled binary",
    )


# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

#: Decorator: skip the test if pywinauto is not installed.
requires_pywinauto = pytest.mark.skipif(
    not _HAS_PYWINAUTO,
    reason="pywinauto not installed — run: pip install pywinauto",
)


# ---------------------------------------------------------------------------
# Session-scoped: build pipeline
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def built_binary():
    """
    Compile translations and build the PyInstaller binary (once per session).

    Skips the entire E2E suite if:
    - ``lrelease`` is not on PATH
    - ``pyinstaller`` is not on PATH

    Returns the ``Path`` to ``dist/DejaView/DejaView.exe``.
    """
    if shutil.which("lrelease") is None:
        pytest.skip(
            "lrelease not on PATH — compile translations manually:\n"
            "  lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm"
        )
    if shutil.which("pyinstaller") is None:
        pytest.skip(
            "pyinstaller not on PATH — install it:\n"
            "  pip install pyinstaller"
        )

    # ── Step 1: compile Hungarian translations ────────────────────────────
    subprocess.run(
        ["lrelease", str(_TS_PATH), "-qm", str(_QM_PATH)],
        cwd=str(DEJAVIEW_DIR),
        check=True,
        timeout=60,
    )
    assert _QM_PATH.exists() and _QM_PATH.stat().st_size > 0, (
        f"lrelease produced an empty/missing .qm file: {_QM_PATH}"
    )

    # ── Step 2: PyInstaller build ─────────────────────────────────────────
    subprocess.run(
        ["pyinstaller", str(_SPEC_PATH), "--noconfirm"],
        cwd=str(DEJAVIEW_DIR),
        check=True,
        timeout=600,  # up to 10 minutes on slow machines
    )

    assert BINARY_PATH.exists(), (
        f"PyInstaller finished but binary not found: {BINARY_PATH}"
    )
    return BINARY_PATH


# ---------------------------------------------------------------------------
# Function-scoped: isolated APPDATA per test
# ---------------------------------------------------------------------------


@pytest.fixture
def app_env(tmp_path):
    """
    Create a temporary APPDATA root so the binary reads/writes its DB and
    thumbnail cache inside ``tmp_path`` rather than the real user profile.

    Returns ``(env_dict, appdata_path)`` where ``appdata_path`` is the value
    injected as the ``APPDATA`` environment variable.
    """
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    env = {**os.environ, "APPDATA": str(appdata)}
    return env, appdata


# ---------------------------------------------------------------------------
# Function-scoped: launch the binary and connect pywinauto
# ---------------------------------------------------------------------------


@pytest.fixture
def launched_app(built_binary, app_env):
    """
    Launch ``DejaView.exe`` with the isolated APPDATA and connect pywinauto.

    Yields ``(proc, pwa_app, main_win, appdata_path)``.
    The process is killed in teardown regardless of test outcome.

    Skips if pywinauto is not installed.
    """
    if not _HAS_PYWINAUTO:
        pytest.skip("pywinauto not installed")

    env, appdata = app_env
    proc = subprocess.Popen([str(built_binary)], env=env)
    try:
        pwa_app = _PwaApplication(backend="uia").connect(
            process=proc.pid, timeout=20
        )
        main_win = pwa_app.window(title_re="DejaView.*")
        main_win.wait("visible", timeout=10)
        yield proc, pwa_app, main_win, appdata
    finally:
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def open_test_db(appdata: Path) -> sqlite3.Connection:
    """
    Open the app's SQLite DB for direct assertion.

    The DB is created at ``<appdata>/DejaView/library.db`` by the app on first
    launch.  Call this only after the app has initialised its database.
    """
    db_path = appdata / "DejaView" / "library.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def wait_for_session_status(
    appdata: Path,
    target_statuses: tuple = ("complete", "stopped"),
    timeout: float = SCAN_TIMEOUT,
) -> str:
    """
    Poll the DB until the newest session row reaches one of ``target_statuses``.

    Returns the actual status string.
    Raises ``TimeoutError`` if the deadline passes without matching.
    """
    db_path = appdata / "DejaView" / "library.db"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if db_path.exists():
            try:
                with sqlite3.connect(str(db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT status FROM sessions ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if row and row["status"] in target_statuses:
                        return row["status"]
            except sqlite3.OperationalError:
                pass  # DB not yet initialised
        time.sleep(0.3)
    raise TimeoutError(
        f"Session did not reach {target_statuses} within {timeout} s"
    )


def get_file_rows(appdata: Path, session_id: int | None = None) -> list:
    """Return all rows from the ``files`` table (optionally filtered by session)."""
    db_path = appdata / "DejaView" / "library.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if session_id is not None:
            rows = conn.execute(
                "SELECT * FROM files WHERE session_id = ?", (session_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM files").fetchall()
    return [dict(r) for r in rows]


def get_latest_session(appdata: Path) -> dict | None:
    """Return the newest sessions row as a dict, or None if no sessions exist."""
    db_path = appdata / "DejaView" / "library.db"
    if not db_path.exists():
        return None
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def make_jpg(path: Path, color: tuple = (128, 128, 128), size: tuple = (64, 64)) -> Path:
    """
    Create a minimal JPEG image.

    Use achromatic (R=G=B) colours so the pixel hash survives JPEG YCbCr
    encoding — see MEMORY.md for the round-trip rule.
    """
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


def make_corrupt_jpg(path: Path) -> Path:
    """Create a file with a JPEG magic number but truncated/invalid content."""
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
    return path


# ---------------------------------------------------------------------------
# UI interaction helpers
# ---------------------------------------------------------------------------


def click_menu(main_win, *menu_path: str) -> None:
    """
    Navigate a menu hierarchy and activate the final item.

    Example::

        click_menu(win, "File", "Add Folder\u2026")
    """
    main_win.set_focus()
    time.sleep(0.1)
    menu_bar = main_win.child_window(control_type="MenuBar")
    top = menu_bar.child_window(title=menu_path[0], control_type="MenuItem")
    top.click_input()
    time.sleep(0.15)
    for item_title in menu_path[1:]:
        item = main_win.child_window(title=item_title, control_type="MenuItem", found_index=0)
        item.click_input()
        time.sleep(0.15)


def select_folder_in_dialog(
    pwa_app,
    folder_path: str,
    dialog_title_re: str = "Select.*Folder|Browse.*Folder",
) -> None:
    """
    Interact with the Windows folder-picker dialog opened by Qt.

    Strategy:
    1. Wait for the dialog to appear.
    2. Press Alt+D to focus the address / path bar.
    3. Type the folder path and press Enter to navigate there.
    4. Click the "Select Folder" / "OK" confirm button.
    """
    dialog = pwa_app.window(title_re=dialog_title_re)
    dialog.wait("exists visible", timeout=10)
    time.sleep(0.4)  # let the dialog fully render

    # Try to type directly into the filename field (works in Qt file dialogs)
    try:
        filename_edit = dialog.child_window(control_type="Edit", found_index=0)
        filename_edit.click_input()
        filename_edit.set_edit_text(folder_path)
    except Exception:
        # Fallback: Alt+D (address bar shortcut in Explorer-style dialogs)
        send_keys("%d")
        time.sleep(0.2)
        send_keys(folder_path, with_spaces=True)
    send_keys("{ENTER}")
    time.sleep(0.5)

    # Click the confirm button
    for title in ("Select Folder", "Open", "OK", "Choose"):
        try:
            btn = dialog.child_window(title=title, control_type="Button")
            if btn.exists():
                btn.click_input()
                return
        except Exception:
            continue
    # Last resort: press Enter once more
    send_keys("{ENTER}")


def add_scan_folder(main_win, pwa_app, folder_path: str) -> None:
    """File → Add Folder… → select folder_path in the picker dialog."""
    click_menu(main_win, "File", "Add Folder\u2026")
    select_folder_in_dialog(pwa_app, folder_path)
    time.sleep(0.3)


def click_start_scan(main_win) -> None:
    """Click the ▶ Start (or ▶ Resume) button in the scan control bar."""
    # Buttons are found by partial text match on the Unicode arrow character
    btn = main_win.child_window(title_re="\u25b6.*", control_type="Button")
    btn.click_input()


def click_pause(main_win) -> None:
    """Click the ⏸ Pause button."""
    btn = main_win.child_window(title_re="\u23f8.*", control_type="Button")
    btn.click_input()


def click_stop(main_win) -> None:
    """Click the ⏹ Stop button."""
    btn = main_win.child_window(title_re="\u23f9.*", control_type="Button")
    btn.click_input()


def dismiss_dialog_ok(pwa_app, dialog_title_re: str = ".*", timeout: float = 5.0) -> bool:
    """
    Find a modal dialog and click its OK / Yes / Close button.
    Returns True if a dialog was found and dismissed, False otherwise.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            dlg = pwa_app.window(title_re=dialog_title_re, control_type="Window")
            if dlg.exists(timeout=0.2):
                for label in ("OK", "Yes", "Close"):
                    try:
                        dlg.child_window(title=label, control_type="Button").click_input()
                        return True
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(0.3)
    return False
