# Fix: Duplicate Signal Storm — Execution Log

**Date:** 2026-02-28
**RCA:** RCA1_DUPLICATE_SIGNAL_STORM.md
**Status:** COMPLETE

---

## Changes

### Modified: `core/scanner.py` (~10 lines changed)
- Changed `duplicate_found` signal from `pyqtSignal(list)` to `pyqtSignal(str, list)` — now passes `(pixel_hash, [file_id, ...])`
- Removed `elif pixel_hash in known_dup_hashes` branch that emitted `duplicate_found` for every subsequent duplicate copy
- Now only emits once per hash when `len(ids) == 2` (first duplicate pair detected)
- Emit call updated to `self.duplicate_found.emit(pixel_hash, list(ids))`

### Modified: `ui/results_panel.py` (~5 lines changed)
- `on_duplicate_found()` signature changed to `(self, pixel_hash: str, file_ids: list[int])`
- Slot decorator updated to `@pyqtSlot(str, list)`
- Replaced `get_duplicate_groups()` VIEW query with `self._duplicate_hashes.add(pixel_hash)` — O(1), zero DB cost
- `_flush_pending()`: `_pending_hash_ids` now deduplicated via `dict.fromkeys()` before processing

### Modified: `tests/integration/test_scanner_pass2.py` (~2 lines changed)
- Updated `duplicate_found.connect()` lambdas to accept new `(pixel_hash, file_ids)` signature

### Modified: `tests/ui/test_results_panel.py` (~1 line changed)
- Updated direct `on_duplicate_found()` call to pass `(hash_val, [fid1, fid2])`

---

## Verification

- [x] `python -m pytest tests/unit/ tests/integration/ --no-cov -q` — 203 passed, 10 skipped
- [ ] Large scan with telemetry: `signal_duplicate_found` count reduced, no UI freezes
