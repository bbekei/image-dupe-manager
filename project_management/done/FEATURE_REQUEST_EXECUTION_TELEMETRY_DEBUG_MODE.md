# Telemetry & Debug Mode — Execution Log

**Date:** 2026-02-28
**Plan:** FEATURE_REQUEST_PLAN_TELEMETRY_DEBUG_MODE.md
**Status:** COMPLETE (R2 — Settings UI + Diagnostics Guide)

---

## Round 1 Changes

### New File: `core/perf_monitor.py` (260 lines)
- `PerformanceMonitor` class: stage timing, queue pressure, signal rate, UI backlog, DB batch timing
- `_TrackedLock` class: drop-in `threading.Lock()` replacement that records wait/hold contention
- `ENABLED` module-level bool for zero-overhead fast-path when telemetry is off
- CSV output to `%APPDATA%/DejaView/perf_<timestamp>.csv` with 23-column schema
- 1-second interval rows + summary row at scan completion

### Modified: `core/scanner.py` (+30 lines)
- Constructor: added `perf_monitor=None` parameter
- `run()`: stage_begin/stage_end calls around Pass 1 and Pass 2, finalize() on all exit paths
- `_flush_batch()`: `record_signal("file_discovered")` per emission
- `_run_pass2()`:
  - `db_lock` uses `perf.tracked_lock()` when enabled (contention tracking)
  - Queue pressure recording before each `wait()` call
  - 1-second periodic `flush_row()` in the drain loop
  - DB batch timing around `update_pixel_hashes_batch()`
  - Signal recording for `hash_complete`, `directory_hashed`, `progress_updated`
- `_emit_deferred_duplicates()`: `record_signal("duplicate_found")`

### Modified: `ui/results_panel.py` (+5 lines)
- Constructor: added `perf_monitor=None` parameter
- `_flush_pending()`: `record_ui_backlog()` at the top, capturing pending queue sizes before flush

### Modified: `ui/main_window.py` (+8 lines)
- Added `self._perf_monitor = None` attribute
- Added `set_perf_monitor()` method that wires monitor to both MainWindow and ResultsPanel
- Scanner instantiation passes `perf_monitor=self._perf_monitor`

### Modified: `main.py` (+12 lines)
- Added `argparse` with `--perf` flag
- Sets `DEJAVIEW_PERF=1` env var when flag is present
- Creates and attaches `PerformanceMonitor` to MainWindow after construction

---

## Round 2 Changes

### Modified: `data/db.py` (+18 lines)
- Added `perf_logging INTEGER NOT NULL DEFAULT 0` column to `app_config` DDL
- Added migration for existing databases (ALTER TABLE ADD COLUMN)
- Added `get_perf_logging()` accessor method
- Added `"perf_logging"` to `upsert_app_config()` allowed fields

### Modified: `ui/settings_dialog.py` (+20 lines)
- Added `QCheckBox` import
- Added "Enable performance telemetry" checkbox under new "Diagnostics" form row
- Added hint label: "CSV saved to %APPDATA%\DejaView on next scan start."
- `_load_current()`: reads `perf_logging` from config and sets checkbox state
- `_on_save()`: persists checkbox state as `perf_logging` in `upsert_app_config()`

### Modified: `ui/main_window.py` (+10 lines, on top of R1)
- `_on_start()`: checks `self._db.get_perf_logging()` when no CLI/env monitor exists
- Creates a fresh `PerformanceMonitor` per scan (each scan gets its own CSV)
- Wires it to both scanner and results_panel

### New File: `resources/help/PERF_DIAGNOSTICS.md`
- Complete diagnostic interpretation guide with:
  - Column reference table (23 columns explained)
  - Decision tree for 4 problem scenarios (UI hang, CPU sawtooth, lock contention, slow throughput)
  - Actionable fix recommendations per diagnosis branch
  - Ready-to-run pandas + matplotlib analysis script
  - Summary row interpretation with red-flag thresholds

---

## Activation (3 methods, any one suffices)

| Method | Scope | Persists? |
|--------|-------|-----------|
| Settings > Diagnostics > Enable performance telemetry | Per-scan | Yes (DB) |
| `python main.py --perf` | Session | No |
| `DEJAVIEW_PERF=1` environment variable | Session | No |

Output: `%APPDATA%/DejaView/perf_YYYYMMDD_HHMMSS.csv` (one file per scan)

---

## Test Results

```
Unit tests:       166 passed, 10 skipped
Integration tests: 37 passed
Total:            203 passed, 0 failed
```

No regressions. All instrumentation is conditional on `self._perf` being non-None.

---

## Design Decisions

1. **Opt-in only** — zero overhead when disabled. The `if self._perf:` guards ensure no performance impact on normal usage.
2. **No new dependencies** — uses only stdlib (`csv`, `threading`, `time`, `logging`).
3. **No logic changes** — all modifications are additive `if self._perf:` blocks. The scanner pipeline, DB batching, and signal flow are untouched.
4. **Lock tracking via composition** — `_TrackedLock` wraps `threading.Lock()` rather than subclassing, ensuring identical semantics.
5. **CSV over SQLite** — chosen for easy external analysis (Excel, pandas, gnuplot) without coupling to the app's own database.
6. **Per-scan CSV** — each scan creates a fresh file, allowing easy comparison across runs.
7. **Settings persistence** — the checkbox state is stored in `app_config.perf_logging` so the user doesn't need to re-enable it each session.

---

## Next Steps (Not Implemented)

After collecting telemetry from a real 30k+ file scan, the CSV data will confirm or refute the hypotheses in the plan document. The diagnostic guide (`resources/help/PERF_DIAGNOSTICS.md`) contains the decision tree for interpreting results and choosing fixes:

1. **If Pass 1 signal rate > 500/s confirmed:** Batch `file_discovered` emissions
2. **If `pending_file_ids` grows unboundedly:** Add backpressure or suppress per-file signals during discovery
3. **If CPU sawtooth confirmed as I/O bursts:** Increase `max_inflight_dirs` or auto-detect SSD/HDD
4. **If lock contention > 50ms/interval:** Investigate unexpected lock holders
