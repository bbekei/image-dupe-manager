"""
tests/ui/test_scan_progress.py — UI tests for ui/scan_progress.py.

Tests the ScanProgressWidget displays correct state for scan lifecycle events.
"""

import pytest

from ui.scan_progress import ScanProgressWidget


def test_initial_state(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    assert "progress" in w._title.text().lower() or "scanning" in w._title.text().lower()
    assert w._progress.value() == 0


def test_scan_started_resets_state(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    assert w._progress.value() == 0
    assert w._current == 0
    assert w._total == 0


def test_progress_updated(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_progress_updated(50, 100)
    assert w._progress.value() == 50
    assert w._current == 50
    assert w._total == 100
    assert "50" in w._count_label.text()
    assert "100" in w._count_label.text()


def test_progress_reaches_100(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_progress_updated(100, 100)
    assert w._progress.value() == 100


def test_scan_complete_updates_title(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_scan_complete()
    assert "complete" in w._title.text().lower()


def test_scan_paused_updates_title(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_scan_paused()
    assert "paused" in w._title.text().lower()


def test_scan_stopped_updates_title(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_scan_stopped()
    assert "stopped" in w._title.text().lower()


def test_file_discovered_increments_count(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    for i in range(500):
        w.on_file_discovered(i, f"/path/img{i}.jpg")
    assert w._discovery_count == 500
    assert "500" in w._phase_label.text()
