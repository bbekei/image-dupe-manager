# DejaView — Feature Request Plan: Performance RCA3 — Infinite Loop in Locality-Aware Hashing Pipeline

## Overview

Fix a critical bug where the scanner never terminates during large scans. The locality-aware submission logic in `_submit_next()` re-defers items from the `_deferred` queue back into itself, creating an infinite cycle that hashes the same files repeatedly.

## Problem

After the RCA2 performance fixes and the Scan Progress View feature, a 70,499-file scan (30,539 hashing candidates) never terminates. The scanner ran for 80 minutes, hashing 224,335 files (7.3x the candidate count) before the user killed it. The `current` counter exceeded `total` at the 10-minute mark and kept climbing indefinitely.

**Key telemetry (`project_management/debug/rca3/`):**
- Scan duration: 77 minutes (user-killed), 224,335 files hashed vs 30,539 candidates
- `directory_hashed` signals: 196,574 (vs ~1,262 actual directories)
- 200k log lines, 196k "current exceeded total" warnings

### Root cause: two bugs in `_submit_next()` locality gate

**Bug A — StopIteration fallthrough:** When the main iterator is exhausted, the `StopIteration` handler pops from `_deferred` but falls through to the locality gate. The gate re-appends the item to `_deferred`, then the item is also submitted at line 470. Result: item is both submitted AND in `_deferred`. When the future completes, `dir_pending` is cleaned up, and the next `_submit_next()` call pops the same item again → infinite cycle.

**Bug B — Retry loop break on StopIteration:** The locality gate appends the original item to `_deferred` (line 455) before trying to find a swap. If the 64-retry loop hits `StopIteration` and `break`s, the `else` clause doesn't run, so `d, fr` still points to the original item. Line 470 submits it, but it's also still in `_deferred`. Same infinite cycle.

**Both bugs share the same root cause:** the original item is appended to `_deferred` eagerly (before a swap is found), creating a window where the item exists in both `_deferred` and `active`.

## Solution

### Fix 1 (P0): Rewrite locality gate — defer original only after swap is found

Move the `_deferred.append((d, fr))` from before the retry loop to inside the `if d2 in dir_pending:` branch. The original item is only deferred when a valid swap exists. If no swap is found (retries exhausted or iterator empty), the original is submitted directly. Locality is best-effort; don't defer indefinitely.

### Fix 2 (P0): Early return when draining `_deferred` after iterator exhaustion

In the `StopIteration` handler, submit popped deferred items directly and return — skip the locality gate entirely. There's no point deferring when the iterator is empty.

### Fix 3 (P1): Reduce diagnostic logging to once per scan

Change per-file WARNING to a single warning with `_overshoot_logged` flag.

### Fix 4 (P1): Add regression test

Create 6 directories with `max_workers=1` (`max_inflight_dirs=2`), verify scan completes with `current == total`.

## Files to Modify

| File | Change |
|------|--------|
| `core/scanner.py` | Fixes 1-3: rewrite locality gate, early return in StopIteration handler, reduce logging |
| `tests/integration/test_scanner_pass2.py` | Fix 4: regression test `test_deferred_queue_drains_without_infinite_loop` |

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Rewrite locality gate — defer only after swap found | ✅ Done | Original item stays in `d, fr` and is submitted at line 476 if no swap; only appended to `_deferred` inside the `if d2 in dir_pending` branch |
| 2 | Early return in StopIteration handler | ✅ Done | Pop from `_deferred`, submit directly, return True — skip locality gate entirely |
| 3 | Reduce diagnostic logging to once per scan | ✅ Done | `_overshoot_logged` flag, single WARNING |
| 4 | Add regression test for deferred draining | ✅ Done | 6 dirs, max_workers=1, assert `current == total` |
| 5 | Run full test suite | ✅ Done | 301 tests pass (204 unit/integration + 97 UI), 10 skipped |

## Verification

1. `cd dejaview && python -m pytest tests/unit/ --no-cov -q`
2. `cd dejaview && python -m pytest tests/integration/ --no-cov -q`
3. `cd dejaview && python -m pytest tests/ui/ --no-cov -q`
4. Manual test — scan the 70k+ file directory with perf logging:
   - Scan terminates normally
   - `current` equals `total` at completion (no overshoot warnings in log)
   - `files_hashed_total` in CSV equals the candidate count
   - `directory_hashed` signal count is reasonable (≈ number of actual directories)
