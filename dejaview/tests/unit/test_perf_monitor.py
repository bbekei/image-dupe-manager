"""
tests/unit/test_perf_monitor.py — PerformanceMonitor unit tests.

Phase 3: CSV output format and disabled-mode noop.
"""

import csv
import time
from pathlib import Path

import pytest

from core.perf_monitor import PerformanceMonitor, _CSV_COLUMNS


class TestDisabledMode:
    """All methods must be noops when enabled=False."""

    def test_disabled_finalize_returns_empty_dict(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=False)
        result = perf.finalize()
        assert result == {}

    def test_disabled_does_not_create_csv(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=False)
        perf.stage_begin("test")
        perf.record_signal("hash_complete")
        perf.record_files_hashed(10)
        perf.record_db_batch_ms(5.0)
        perf.record_queue_state(10, 5, 3)
        perf.record_ui_backlog(100, 50)
        perf.flush_row()
        perf.stage_end("test")
        perf.finalize()
        csv_files = list(tmp_path.glob("perf_*.csv"))
        assert len(csv_files) == 0

    def test_disabled_tracked_lock_works(self, tmp_path):
        """tracked_lock should still be usable as a lock even when disabled."""
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=False)
        lock = perf.tracked_lock()
        with lock:
            pass  # should not raise


class TestEnabledMode:
    """Verify CSV output format and metric recording."""

    def test_creates_csv_on_init(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=True)
        csv_files = list(tmp_path.glob("perf_*.csv"))
        assert len(csv_files) == 1
        perf.finalize()

    def test_csv_has_correct_header(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=True)
        perf.finalize()
        csv_file = list(tmp_path.glob("perf_*.csv"))[0]
        with open(csv_file, "r") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == _CSV_COLUMNS

    def test_flush_row_writes_data(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=True, workers=4)
        perf.stage_begin("hashing")
        perf.record_signal("hash_complete")
        perf.record_signal("hash_complete")
        perf.record_files_hashed(2)
        perf.flush_row()
        perf.stage_end("hashing")
        summary = perf.finalize()

        csv_file = list(tmp_path.glob("perf_*.csv"))[0]
        with open(csv_file, "r") as f:
            content = f.read()
        # Filter out comment lines
        data_lines = [ln for ln in content.strip().split("\n")
                      if ln and not ln.startswith("#")]
        # Header + at least 1 data row + finalize row
        assert len(data_lines) >= 2

    def test_finalize_returns_summary(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=True, workers=2)
        perf.stage_begin("discovery")
        perf.record_signal("file_discovered")
        perf.record_signal("file_discovered")
        perf.record_signal("file_discovered")
        perf.record_files_hashed(5)
        perf.stage_end("discovery")

        summary = perf.finalize()
        assert "total_elapsed_s" in summary
        assert "stages" in summary
        assert "discovery" in summary["stages"]
        assert summary["signals_total"] == 3
        assert summary["signal_breakdown"]["file_discovered"] == 3
        assert summary["files_hashed"] == 5
        assert "csv_path" in summary

    def test_tracked_lock_records_contention(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=True)
        lock = perf.tracked_lock()

        for _ in range(10):
            with lock:
                time.sleep(0.001)

        summary = perf.finalize()
        assert summary["lock_acquires_total"] == 10
        assert summary["lock_hold_total_ms"] > 0

    def test_record_db_batch_accumulates(self, tmp_path):
        perf = PerformanceMonitor(output_dir=tmp_path, enabled=True)
        perf.record_db_batch_ms(10.0)
        perf.record_db_batch_ms(20.0)
        perf.record_db_batch_ms(5.0)
        # After flush, accumulators reset
        perf.flush_row()
        assert perf._db_batch_ms_accum == 0.0
        assert perf._db_batch_count == 0
        perf.finalize()
