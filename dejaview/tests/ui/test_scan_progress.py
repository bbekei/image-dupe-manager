"""
tests/ui/test_scan_progress.py — UI tests for ui/scan_progress.py.

Tests the ScanProgressWidget displays correct state for scan lifecycle events
using the unified multi-step progress layout.
"""

import pytest

from ui.scan_progress import ScanProgressWidget


def test_initial_state(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    assert "progress" in w._title.text().lower() or "scanning" in w._title.text().lower()
    assert w._overall_bar.value() == 0


def test_scan_started_resets_state(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    assert w._overall_bar.value() == 0
    assert w._hash_current == 0
    assert w._hash_total == 0


def test_progress_updated_tracks_hashing(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_progress_updated(50, 100)
    assert w._hash_current == 50
    assert w._hash_total == 100
    assert w._discovery_done is True
    assert w._phase == "hashing"
    # Overall bar should be > 0 (discovery weight + partial hashing weight).
    assert w._overall_bar.value() > 0


def test_progress_reaches_100(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_progress_updated(100, 100)
    # Hashing is 90% weight without similarity, so bar should be near 950.
    assert w._overall_bar.value() >= 900


def test_scan_complete_updates_title(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.on_scan_started()
    w.on_scan_complete()
    assert "complete" in w._title.text().lower()
    assert w._overall_bar.value() == 1000


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


def test_similarity_progress_tracked(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.set_similarity_enabled(True)
    w.on_scan_started()
    w.on_progress_updated(100, 100)  # hashing done
    w.on_similarity_progress(50, 200)
    assert w._sim_current == 50
    assert w._sim_total == 200
    assert w._phase == "similarity"
    assert w._hashing_done is True


def test_similarity_done_transitions_to_finalize(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.set_similarity_enabled(True)
    w.on_scan_started()
    w.on_progress_updated(100, 100)
    w.on_similarity_progress(200, 200)  # similarity complete
    assert w._similarity_done is True
    assert w._phase == "finalize"


def test_grouping_complete(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.set_similarity_enabled(True)
    w.on_scan_started()
    w.on_progress_updated(100, 100)
    w.on_similarity_progress(200, 200)
    w.on_similarity_grouping_complete(10)
    assert w._finalize_done is True


def test_similarity_rows_hidden_when_disabled(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.set_similarity_enabled(False)
    assert w._step_similarity.widget.isHidden()
    assert w._step_finalize.widget.isHidden()


def test_similarity_rows_visible_when_enabled(qtbot):
    w = ScanProgressWidget()
    qtbot.addWidget(w)
    w.set_similarity_enabled(True)
    assert not w._step_similarity.widget.isHidden()
    assert not w._step_finalize.widget.isHidden()
