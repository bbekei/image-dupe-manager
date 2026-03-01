# DejaView — Feature Request Plan: Scan Progress View (Deferred Tree Population)

## Overview
Replace the live-updating ResultsPanel during scanning with a dedicated progress view. The tree is populated once after scan completes, eliminating the entire class of UI responsiveness problems caused by incremental tree updates on 70k+ file scans.

## Problem
The current architecture live-updates a QStandardItemModel tree during scanning — creating/updating 70k+ QStandardItem objects, recomputing folder badges, and invalidating filter proxies in real-time. Even with batched signals and debouncing (RCA1 + RCA2 fixes), the main thread can't keep up with the volume of work at scale, causing progressive UI freezes.

The user gains no actionable benefit from partial results during scan: a file that appears "unique" at 30% progress may become a duplicate when its match is hashed later. Professional tools (Lightroom, backup software, disk utilities) solve this by showing progress and presenting results only when ready.

## User Experience

### During scan (new progress view replaces ResultsPanel):
```
┌─────────────────────────────────────────────┐
│                                             │
│         🔍 Scanning in progress...          │
│                                             │
│    ████████████░░░░░░░░░░░  52%             │
│                                             │
│    36,259 / 70,499 files — ~14 min left     │
│                                             │
│    Pass 1: Discovery ✓  (70,499 files)      │
│    Pass 2: Hashing...   (36,259 / 70,499)   │
│                                             │
│    [  Pause  ]  [  Stop  ]                  │
│                                             │
└─────────────────────────────────────────────┘
```

### After scan completes (tree populated, filter auto-set):
Same as today — ResultsPanel shows full tree with "Duplicates Only" filter pre-selected, status bar shows summary. The only difference is the tree appears all at once (~2-3 seconds to build from DB) instead of incrementally.

## Solution

### 1. Create `ScanProgressWidget` — lightweight progress panel
New file `ui/scan_progress.py`. A simple QWidget with:
- Large centered status label ("Scanning in progress...")
- Progress bar (duplicates `ScanControl` progress, or reads from it)
- File count + ETA label
- Phase indicators (Pass 1 done, Pass 2 in progress)
- No tree, no model, no filter proxy — pure display widget

Connects to the same scanner signals that `ScanControl` uses:
- `progress_updated(current, total)` for the progress bar and count
- `status_message(str)` for phase transitions
- `scan_complete` / `scan_paused` / `scan_stopped` for state changes

### 2. Add panel swapping in `MainWindow`
Use the existing hide/show pattern (same as CompareView swap):
- **Scan starts:** `_results_panel.hide()`, show `ScanProgressWidget` in the splitter
- **Scan completes:** hide `ScanProgressWidget`, `_results_panel.show()`, call `_results_panel.reload()`
- **Scan paused:** hide `ScanProgressWidget`, `_results_panel.show()`, call `_results_panel.reload()` (user can browse partial results while paused)
- **Scan resumed:** `_results_panel.hide()`, show `ScanProgressWidget` again

### 3. Disconnect ResultsPanel from scanner signals during scan
In `_wire_scanner()`, do NOT connect:
- `file_discovered` → ResultsPanel (no live tree inserts during Pass 1)
- `hash_complete_batch` → ResultsPanel (no live badge updates during Pass 2)
- `duplicate_found` → ResultsPanel (no live duplicate tracking)
- `directories_hashed` → ResultsPanel (no live folder recompute)

These signals still fire (scanner unchanged), but nothing on the main thread processes them into tree items. The `ScanControl` + `ScanProgressWidget` + status bar connections remain.

Keep `directories_hashed` → `FolderPanel` wired (already throttled, lightweight).

### 4. Wire ScanProgressWidget to scanner
Connect the minimal set of signals needed for progress display:
- `progress_updated` → update bar + count
- `status_message` → update phase label
- `scan_started` / `scan_complete` / `scan_paused` / `scan_stopped` → state transitions

### 5. Adjust `_on_scan_complete` for one-shot tree build
Current flow already calls `_results_panel.reload()` on resume — extend this:
- After showing ResultsPanel, call `reload()` which builds the full tree from DB in one pass
- This is already implemented and works — it's what happens on app startup when loading an existing session

## Files to Modify

| File | Change |
|------|--------|
| `ui/scan_progress.py` | **New file** — ScanProgressWidget (progress bar, count, phase labels) |
| `ui/main_window.py` | Panel swap logic in `_on_start`, `_on_scan_complete`, pause/stop handlers; disconnect ResultsPanel from scanner signals |
| `ui/results_panel.py` | No changes needed — `reload()` already builds the full tree from DB |
| `ui/scan_control.py` | No changes needed — continues to work as-is in the bottom bar |
| `core/scanner.py` | No changes needed — signals still emitted for ScanControl/telemetry |

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Create `ui/scan_progress.py` — ScanProgressWidget | ✅ Done | Progress bar, count + ETA, phase labels, centered layout |
| 2 | Add panel swap in MainWindow: scan start → show progress, hide results | ✅ Done | `_show_scan_progress()` / `_hide_scan_progress()` helpers |
| 3 | Add panel swap in MainWindow: scan complete → hide progress, show results + reload | ✅ Done | `_on_scan_complete` calls `_hide_scan_progress()` + `reload()` |
| 4 | Handle pause: show results with partial data; resume: swap back to progress | ✅ Done | `_on_scan_paused` slot added; resume re-creates progress widget |
| 5 | Handle stop: show results with partial data | ✅ Done | `_on_scan_stopped` slot added |
| 6 | Disconnect ResultsPanel from live scanner signals in `_wire_scanner` | ✅ Done | Removed all 4 live signal connections to ResultsPanel |
| 7 | Wire ScanProgressWidget to scanner signals | ✅ Done | `progress_updated`, `status_message`, `file_discovered`, lifecycle signals |
| 8 | Add UI test for ScanProgressWidget | ✅ Done | 8 tests in `tests/ui/test_scan_progress.py` |
| 9 | Run full test suite | ✅ Done | 300 tests pass (10 skipped) |

## Verification

1. `cd dejaview && python -m pytest tests/unit/ --no-cov -q`
2. `cd dejaview && python -m pytest tests/integration/ --no-cov -q`
3. `cd dejaview && python -m pytest tests/ui/ --no-cov -q`
4. Manual test — small scan (few hundred files):
   - Progress view shows during scan with updating count/bar
   - Tree appears populated after completion
   - Pause shows partial results; resume shows progress view again
   - Stop shows partial results
5. Manual test — large scan (70k+ files) with perf logging:
   - No UI freezes (main thread does zero tree work during scan)
   - Progress bar and ETA update smoothly
   - Tree builds in ~2-3 seconds on completion
