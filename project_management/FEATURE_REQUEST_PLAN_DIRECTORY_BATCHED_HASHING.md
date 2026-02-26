# DejaView — Feature Request Plan: Directory-Batched Hashing

## Overview

Rewrite Pass 2 (hashing) to process candidates one directory at a time, deepest-first, instead of submitting all candidates to the thread pool at once. After each directory batch completes, immediately update the ResultsPanel (folder duplication badges) and FolderPanel (file counts per root folder) so the user can browse accurate, incremental results while the scan continues.

## Problem

Pass 2 currently submits ALL size-duplicate candidates to `ThreadPoolExecutor` at once. Files from many different directories complete in interleaved, unpredictable order:

- Folder-level duplication badges never stabilize for any single directory until nearly everything is done
- The user can't tell which directories are "done" vs. still in-progress — browsing mid-scan shows incomplete, misleading per-directory results
- FolderPanel shows no scan progress per root folder
- ETA updates are erratic when directories vary widely in file count
- No natural checkpoint boundaries for pause/stop

## User Experience

**Before:** User starts scan → progress bar trickles → all panels show partial results everywhere → user waits for full completion before meaningful browsing.

**After:**
```
FolderPanel (left)                    ResultsPanel (right)
┌──────────────────────┐  ┌───────────────────────────────────┐
│ C:\Photos            │  │ ▼ C:\Photos\2024\January          │
│   (120 files,        │  │     img001.jpg  ● DUPLICATE       │
│    47 hashed)        │  │     img002.jpg  ● DUPLICATE       │
│                      │  │ ▼ C:\Photos\2024\February         │
│ D:\Backup            │  │     photo1.jpg                    │
│   (85 files,         │  │ ▶ C:\Photos\2024\March  (hashing…)│
│    0 hashed)         │  │                                   │
└──────────────────────┘  └───────────────────────────────────┘
         ScanControl: [Pause] [Stop]  47 / 205 — ~3m 12s left
```

Directories complete leaf-first (deepest subdirectories first). Completed directories show accurate duplication badges. FolderPanel shows live `(N files, M hashed)` counts.

## Solution

### 1. `core/scanner.py` — Directory-batched Pass 2

**1a. New signal** (after line 104):
```python
directory_hashed = pyqtSignal(str)   # directory path
```

**1b. Rewrite `_run_pass2()`** (lines 267–321):
- Retrieve candidates (unchanged query)
- Group by `os.path.dirname(path)` into `dir_groups: dict[str, list]`
- Sort directories leaf-first: `key=lambda d: (-d.count(os.sep), d)`
- Create `ThreadPoolExecutor` **once** (reused across all batches)
- For each directory group:
  - Check pause/stop (natural checkpoint between batches)
  - Submit that directory's files to the executor
  - Process via `as_completed()` — per-file: update DB, emit `hash_complete`, check duplicates, emit `duplicate_found`, increment global `current`, emit `progress_updated`
  - After batch completes: emit `directory_hashed(dir_path)`
- On pause/stop mid-batch: cancel remaining futures in current batch (not `executor.shutdown`)

Key invariants preserved:
- `current` counter is **global** across all directories (0 → total)
- `total` is set once from the full candidate list
- Existing per-file signals unchanged
- Resume works: `get_unhashed_files_grouped_by_size()` skips already-hashed files

### 2. `data/db.py` — New query for folder file counts

Add `get_folder_file_counts(session_id, folder_prefix)`:
```python
def get_folder_file_counts(self, session_id: int, folder_prefix: str) -> tuple[int, int]:
    """Return (total_files, hashed_files) under folder_prefix for the session."""
    row = self.conn.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(pixel_hash) AS hashed
        FROM files
        WHERE session_id = ? AND path LIKE ? || '%' AND status = 'active'
        """,
        (session_id, folder_prefix),
    ).fetchone()
    return (row["total"], row["hashed"])
```

### 3. `ui/folder_panel.py` — Live file counts per root folder

**3a. New public slot `on_directory_hashed(dir_path: str)`:**
- Determine which root folder `dir_path` belongs to (check `startswith`)
- Query DB via `get_folder_file_counts()` for that root folder
- Update the `QListWidgetItem` text to show `"C:\Photos (120 files, 47 hashed)"`

**3b. New method `update_all_counts()`:**
- Called once after Pass 1 completes to show initial file counts (e.g. `"120 files, 0 hashed"`)
- Iterates all root folders, queries counts, updates item text

**3c. Reset display text** on scan complete/stop — revert items to plain folder paths.

### 4. `ui/results_panel.py` — Immediate flush at directory boundaries

Add `on_directory_hashed(dir_path: str)` slot after `on_duplicate_found` (~line 258):
- Calls `self._flush_pending()` to drain queued updates immediately
- `_flush_pending()` already calls `_compute_folder_duplication()` when hash IDs are pending, so folder badges become accurate for the completed directory

This is additive — does not replace or interfere with the existing debounced per-file updates.

**Cross-directory duplicate handling:** When directory B reveals a duplicate of a file in already-completed directory A, the existing `duplicate_found` signal emits **all** file IDs in the group (both A1 and B1). `on_duplicate_found` queues both IDs into `_pending_hash_ids`. When `on_directory_hashed` fires for dir B, `_flush_pending()` processes A1's badge update too, and `_compute_folder_duplication()` walks the entire tree — so directory A's badges also update. No additional logic needed.

### 5. `ui/main_window.py` — Wire new signal

Add in `_wire_scanner()` (~line 283):
```python
scanner.directory_hashed.connect(self._results_panel.on_directory_hashed)
scanner.directory_hashed.connect(self._folder_panel.on_directory_hashed)
```

Also wire:
- `scan_started` → `folder_panel.update_all_counts()` (show initial counts after Pass 1)
- `scan_complete` / `scan_stopped` → reset folder panel display text to plain paths

### 6. `tests/integration/test_scanner_pass2.py` — New tests

| Test | Verifies |
|------|----------|
| `test_directory_hashed_signal_emitted_per_directory` | Signal fires once per unique directory containing candidates |
| `test_directories_processed_leaf_first` | Deeper dirs emit `directory_hashed` before shallower ones |
| `test_progress_remains_global_across_directory_batches` | `current` advances 0→total without resets; `total` is constant |

Uses existing fixtures (`db`, `scan_dir`, `session_id`, `thumb_dir`, `qtbot`) and `_jpg()` helper.

## Files to Modify

| File | Change |
|------|--------|
| `dejaview/core/scanner.py` | Add `directory_hashed` signal; rewrite `_run_pass2()` to batch by directory (leaf-first) |
| `dejaview/data/db.py` | Add `get_folder_file_counts()` query |
| `dejaview/ui/folder_panel.py` | Add `on_directory_hashed` slot, `update_all_counts()`, count display in item text |
| `dejaview/ui/results_panel.py` | Add `on_directory_hashed` slot (flush + recompute) |
| `dejaview/ui/main_window.py` | Wire `directory_hashed` to both panels; wire count init/reset |
| `dejaview/tests/integration/test_scanner_pass2.py` | 3 new integration tests |

## Task Log

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Add `directory_hashed` signal to Scanner | ⬜ | New `pyqtSignal(str)` |
| 2 | Rewrite `_run_pass2()` with directory batching | ⬜ | Group by dir, sort leaf-first, process per-batch, emit signal |
| 3 | Add `get_folder_file_counts()` to db.py | ⬜ | SQL COUNT with folder prefix filter |
| 4 | Add FolderPanel count display + slots | ⬜ | `on_directory_hashed`, `update_all_counts`, reset on complete/stop |
| 5 | Add `on_directory_hashed` slot to ResultsPanel | ⬜ | Flush pending + recompute folder duplication |
| 6 | Wire signals in MainWindow `_wire_scanner()` | ⬜ | Connect to both panels + count init/reset |
| 7 | Write integration tests | ⬜ | 3 tests: signal emission, leaf-first order, global progress |
| 8 | Run tests, verify | ⬜ | `python -m pytest tests/unit/ tests/integration/ --no-cov -q` |

## Verification

```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q              # existing unit tests pass
python -m pytest tests/integration/ --no-cov -q        # new + existing integration tests pass
```

Manual test:
1. Add a folder with deeply nested subdirectories containing many images
2. Start scan — observe FolderPanel showing `(N files, M hashed)` updating per root folder
3. Observe ResultsPanel folder badges updating incrementally as directories complete
4. Browse a completed directory mid-scan — folder duplication badges should be accurate
5. Open compare view for a duplicate found mid-scan — should work
6. Verify ETA updates more frequently at directory boundaries
7. Verify pause/stop works between directory batches
8. Verify resume picks up remaining unhashed directories
9. Verify folder panel text resets to plain paths after scan completes
