"""
tests/e2e/test_e2e_build.py — Phase 0: Build Pipeline (E2E_TEST_PLAN.md §Phase 0).

Tasks covered
-------------
P0-T01  lrelease compiles app_hu.ts → app_hu.qm (non-empty, exists)
P0-T02  pyinstaller produces dist/DejaView/DejaView.exe
P0-T03  Binary smoke test: launch binary, assert window appears, close cleanly

Notes
-----
The ``built_binary`` session fixture runs the actual build steps.  These three
tests verify the *outputs* of that fixture as explicit assertions so failures
are clearly attributed to build rather than test logic.
"""

import subprocess
import time

import pytest

from .conftest import (
    BINARY_PATH,
    DEJAVIEW_DIR,
    _HAS_PYWINAUTO,
    _PwaApplication,
    _QM_PATH,
    requires_pywinauto,
)

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# P0-T01: Translation compilation
# ---------------------------------------------------------------------------


def test_p0_t01_lrelease_produces_valid_qm(built_binary):
    """
    P0-T01 — lrelease compiles app_hu.ts → app_hu.qm.

    The ``built_binary`` fixture already ran lrelease.  This test verifies the
    output file exists and is a non-trivial size (Qt .qm files are at least
    a few hundred bytes).
    """
    assert _QM_PATH.exists(), f".qm file not found: {_QM_PATH}"
    size = _QM_PATH.stat().st_size
    assert size > 500, (
        f"app_hu.qm is suspiciously small ({size} bytes); "
        "lrelease may have produced an empty or stub file"
    )


# ---------------------------------------------------------------------------
# P0-T02: PyInstaller binary
# ---------------------------------------------------------------------------


def test_p0_t02_pyinstaller_binary_exists(built_binary):
    """
    P0-T02 — PyInstaller produces dist/DejaView/DejaView.exe.

    Verifies the binary exists and is an executable (non-zero size, .exe suffix
    on Windows).  The ``built_binary`` fixture ran pyinstaller.
    """
    assert BINARY_PATH.exists(), f"Binary not found: {BINARY_PATH}"
    assert BINARY_PATH.suffix.lower() == ".exe", (
        f"Expected .exe, got: {BINARY_PATH.suffix}"
    )
    assert BINARY_PATH.stat().st_size > 1_000_000, (
        f"Binary is smaller than 1 MB ({BINARY_PATH.stat().st_size} bytes); "
        "the build may be incomplete"
    )

    # Verify key bundled resources are present in the dist folder
    dist_dir = BINARY_PATH.parent
    qm_in_dist = dist_dir / "_internal" / "resources" / "i18n" / "app_hu.qm"
    assert qm_in_dist.exists(), (
        f"Bundled app_hu.qm not found in dist: {qm_in_dist}"
    )


# ---------------------------------------------------------------------------
# P0-T03: Binary smoke test (launch + window + close)
# ---------------------------------------------------------------------------


@requires_pywinauto
def test_p0_t03_binary_smoke_launch_and_close(built_binary, app_env):
    """
    P0-T03 — Launch the binary, assert the main window appears, close cleanly.

    Uses an isolated APPDATA so the developer's data is untouched.
    """
    import os

    env, _appdata = app_env
    proc = subprocess.Popen([str(built_binary)], env=env)
    try:
        pwa_app = _PwaApplication(backend="uia").connect(
            process=proc.pid, timeout=20
        )
        main_win = pwa_app.window(title_re="DejaView.*")
        main_win.wait("visible", timeout=10)

        # Window exists and has the expected title
        assert main_win.is_visible()
        assert "DejaView" in main_win.window_text()

        # Close via the window's close button (not kill)
        main_win.close()
        proc.wait(timeout=10)
        assert proc.returncode is not None, "Process did not terminate after close"
    except Exception:
        proc.kill()
        proc.wait(timeout=5)
        raise
