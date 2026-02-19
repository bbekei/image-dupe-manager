"""
tests/ui/test_scan_control.py — UI tests for ui/scan_control.py.
Plan §UI Tests: scan_control.

Req 4.2 — Pause, resume, or stop the scanning process.
"""

import pytest

from ui.scan_control import ScanControl


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def ctrl(qtbot):
    c = ScanControl()
    qtbot.addWidget(c)
    return c


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_initial_state_only_start_enabled(ctrl):
    # Req 4.2 — plan §UI Tests: test_initial_state_only_start_enabled
    assert ctrl._start_btn.isEnabled()
    assert not ctrl._pause_btn.isEnabled()
    assert not ctrl._stop_btn.isEnabled()


def test_after_start_pause_and_stop_become_enabled(ctrl):
    # Req 4.2 — plan §UI Tests: test_after_start_pause_and_stop_become_enabled
    ctrl.on_scan_started()
    assert not ctrl._start_btn.isEnabled()
    assert ctrl._pause_btn.isEnabled()
    assert ctrl._stop_btn.isEnabled()


def test_after_pause_resume_enabled_not_pause(ctrl):
    # Req 4.2 — plan §UI Tests: test_after_pause_resume_enabled_not_pause
    ctrl.on_scan_started()
    ctrl.on_scan_paused()
    assert ctrl._start_btn.isEnabled()    # shows "Resume"
    assert not ctrl._pause_btn.isEnabled()
    assert ctrl._stop_btn.isEnabled()


def test_after_stop_only_start_enabled(ctrl):
    # Req 4.2 — plan §UI Tests: test_after_stop_only_start_enabled
    ctrl.on_scan_started()
    ctrl.on_scan_stopped()
    assert ctrl._start_btn.isEnabled()
    assert not ctrl._pause_btn.isEnabled()
    assert not ctrl._stop_btn.isEnabled()


def test_after_complete_only_start_enabled(ctrl):
    # Scan complete resets to initial state (Start enabled, others disabled).
    ctrl.on_scan_started()
    ctrl.on_scan_complete()
    assert ctrl._start_btn.isEnabled()
    assert not ctrl._pause_btn.isEnabled()
    assert not ctrl._stop_btn.isEnabled()


def test_progress_bar_updates_on_signal(ctrl):
    # Req 4.2 — plan §UI Tests: test_progress_bar_updates_on_signal
    ctrl.on_scan_started()
    ctrl.on_progress_updated(47, 100)
    assert ctrl._progress.value() == 47
    assert "47" in ctrl._status_label.text()
    assert "100" in ctrl._status_label.text()


def test_status_label_shows_paused_badge_when_paused(ctrl):
    # Req 4.2 — plan §UI Tests: test_status_label_shows_paused_badge_when_paused
    ctrl.on_scan_started()
    ctrl.on_scan_paused()
    assert "PAUSED" in ctrl._status_label.text()


def test_start_btn_shows_resume_label_when_paused(ctrl):
    # Start button text changes to "Resume" in paused state.
    ctrl.on_scan_started()
    ctrl.on_scan_paused()
    assert "Resume" in ctrl._start_btn.text()


def test_start_btn_reverts_to_start_after_resumed(ctrl):
    # After on_scan_resumed, start btn is disabled (scan running again).
    ctrl.on_scan_started()
    ctrl.on_scan_paused()
    ctrl.on_scan_resumed()
    assert not ctrl._start_btn.isEnabled()
    assert ctrl._pause_btn.isEnabled()


def test_progress_bar_zero_on_zero_total(ctrl):
    # Guard against division by zero when total=0 (plan §Pass 2 edge case).
    ctrl.on_scan_started()
    ctrl.on_progress_updated(0, 0)   # must not raise
    assert ctrl._progress.value() == 0


def test_set_state_paused_mirrors_on_scan_paused(ctrl):
    # Used by MainWindow to restore paused state on startup (plan §Session restore).
    ctrl.set_state_paused()
    assert ctrl._start_btn.isEnabled()
    assert not ctrl._pause_btn.isEnabled()
    assert "PAUSED" in ctrl._status_label.text()


def test_complete_status_label_shows_complete(ctrl):
    ctrl.on_scan_started()
    ctrl.on_scan_complete()
    assert "Complete" in ctrl._status_label.text()


def test_start_requested_signal_emitted_on_click(qtbot, ctrl):
    with qtbot.waitSignal(ctrl.start_requested, timeout=1000):
        ctrl._start_btn.click()


def test_pause_requested_signal_emitted_on_click(qtbot, ctrl):
    ctrl.on_scan_started()   # enable the button first
    with qtbot.waitSignal(ctrl.pause_requested, timeout=1000):
        ctrl._pause_btn.click()


def test_stop_requested_signal_emitted_on_click(qtbot, ctrl):
    ctrl.on_scan_started()   # enable the button first
    with qtbot.waitSignal(ctrl.stop_requested, timeout=1000):
        ctrl._stop_btn.click()
