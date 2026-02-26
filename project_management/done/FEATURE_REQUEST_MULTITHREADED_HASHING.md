# DejaView — Feature Request: Multi-threaded Hashing + ETA Progress

## Overview

Two related improvements to the scanning experience:

1. **Multi-threaded hashing** — Parallelized Pass 2 hashing in `scanner.py` using
   `concurrent.futures.ThreadPoolExecutor` to utilize all available CPU cores.
2. **ETA progress display** — Added estimated time remaining to the scan progress bar,
   calculated from running average throughput, updated every second.

---

## Part 1: Multi-threaded Hashing

### Problem

`_run_pass2()` iterated over size-duplicate candidates and called `hash_file()` one at a time in a
serial `for` loop. On a machine with 8+ cores, only one core did useful work while the rest sat
idle. For large photo libraries this was the primary performance bottleneck.

### Why ThreadPoolExecutor (not multiprocessing)?

- Pillow and hashlib release the GIL → threads get true CPU parallelism
- No pickle/serialization overhead — images stay in-process
- Qt signals work from any thread — no cross-process IPC needed
- DB already configured for multi-thread access (`check_same_thread=False`, WAL mode)
- `hash_file()` is a pure function — no shared mutable state

### Changes to `scanner.py` only

1. Added `max_workers` optional kwarg to Scanner constructor (default: `min(os.cpu_count(), 8)`)
2. Rewrote `_run_pass2()` to submit hash jobs via `ThreadPoolExecutor` and collect via `as_completed()`
3. DB writes + duplicate detection serialized under `threading.Lock`
4. Falls back to 1 worker when `scan_delay_ms > 0` (throttle mode)
5. Pause/stop cancels pending futures via `executor.shutdown(cancel_futures=True)`

No changes to `hasher.py` — already a pure function.

### Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add `_max_workers` to Scanner `__init__` | ✅ Done | Default `min(os.cpu_count() or 1, 8)`, optional kwarg after `parent` |
| 2 | Add `import threading` | ✅ Done | Added alongside existing `concurrent.futures` import |
| 3 | Rewrite `_run_pass2()` with ThreadPoolExecutor | ✅ Done | Submit → `as_completed` → DB write under `threading.Lock` → signals. Falls back to 1 worker when `scan_delay_ms > 0`. |
| 4 | Update module docstring | ✅ Done | Added note about ThreadPoolExecutor in Pass 2 description |
| 5 | Run unit tests | ✅ Done | 151 passed, 10 skipped. Integration: 14 passed, 1 pre-existing failure (unrelated). |

---

## Part 2: ETA Progress Display

### Problem

Progress bar showed `"47 / 100"` with no time estimate. For large libraries, users couldn't tell
if scanning would take 5 minutes or 2 hours.

### Solution

ETA calculated entirely in `scan_control.py` — no signal changes needed.

1. Records `time.monotonic()` when first file completes (`current == 1`)
2. On each update: `rate = current / elapsed`, `remaining = (total - current) / rate`
3. Rate-limited to 1 update per second to avoid flickering
4. On completion: shows total elapsed time instead of ETA
5. Resets on scan start / resume (pause invalidates the rate)

### Time format (human-readable, largest unit first)

| Range | Format |
|-------|--------|
| < 60s | `~45s left` |
| 1–59 min | `~2m 15s left` |
| 1–23 hours | `~1h 23m left` |
| >= 24 hours | `~1d 2h left` |
| Completion | `100 / 100 — 1m 42s` |

### Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add ETA timing + display to `scan_control.py` | ✅ Done | `time.monotonic()`, `_format_duration()` helper, 1s rate-limit, zero-division guard, label widened to 200px |
| 2 | Add i18n strings for ETA | ✅ Done | `"{0} / {1} — {2}"` and `"~{0} left"` in both app.ts and app_hu.ts |
| 3 | Run tests | ✅ Done | Unit: 151 passed, 10 skipped. Integration: 33 passed (excluding 3 pre-existing failures). |

---

## Verification

- Unit tests: `python -m pytest tests/unit/ --no-cov -q` → 151 passed, 10 skipped
- Integration tests: 33 passed (excluding pre-existing failures)
- Manual verification: scan a folder with images, verify ETA appears, converges, and shows elapsed on completion
- Pause/stop during Pass 2: should stop cleanly
- `scan_delay_ms > 0`: should behave like original serial mode
