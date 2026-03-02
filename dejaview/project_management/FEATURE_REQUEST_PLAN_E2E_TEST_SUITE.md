# DejaView — Feature Request Plan: End-to-End Test Suite

## Overview

Replace manual smoke testing with an automated end-to-end test suite that exercises the full application workflow: build, scan, plan (keep/delete/ignore decisions), execute (soft-delete), and verify (DB state + filesystem). The suite uses a **two-tier architecture**: headless API-level tests (fast, CI-friendly) and GUI binary tests (pywinauto, full user-experience validation).

## Problem

1. **Manual smoke testing is slow and error-prone.** After each code change the developer must manually scan folders, make keep/delete decisions, execute the plan, and verify file operations — consuming 10-15 minutes per cycle.
2. **The existing E2E suite (`tests/e2e/`) covers build, launch, scan, pause, filters, sharing, and settings — but has NO tests for the planning, execution, or recovery phases.** This is the most critical gap because the planning-through-execution flow is where data loss could occur.
3. **No headless (API-level) E2E tests exist at all.** The existing integration tests in `tests/integration/` cover individual Scanner passes but never exercise the full workflow pipeline from scan through execution and verification.

## Solution

### Test Image Fixtures

Tests use a pre-populated image directory and a manifest file for deterministic assertions.

**Directory:** `tests/fixtures/e2e_dataset/` — Created and maintained by the developer separately. Contains known duplicate sets, unique files, different formats, and corrupt files.

**Manifest:** `tests/fixtures/e2e_manifest.json` — Defines expected duplicate groups and metadata:

```json
{
  "description": "E2E test image manifest",
  "groups": [
    {
      "name": "group_name",
      "description": "Human-readable description",
      "files": ["img_a.jpg", "subdir/img_a_copy.jpg"],
      "expected_keeper": {
        "KEEP_LARGEST_FILE": "subdir/img_a_copy.jpg",
        "KEEP_NEWEST": null
      }
    }
  ],
  "unique_files": ["unique_blue.jpg"],
  "corrupt_files": ["corrupt.jpg"],
  "expected_group_count": 2,
  "expected_total_files": 8
}
```

The manifest drives:
- **Group assertions**: which files should share a `pixel_hash` after scanning
- **Keeper assertions**: which file should be kept under each preset (`null` = don't assert)
- **Count assertions**: total files, groups, unique files
- **Error handling**: corrupt files expected to scan without crash

For full-pipeline tests, images are copied from `e2e_dataset/` into a temp directory. File timestamps (`mtime`) are set programmatically since git doesn't preserve modification dates.

---

### Tier 1: Headless E2E Tests (Primary Focus)

**File:** `tests/e2e/test_e2e_headless.py` — No GUI, no build required. Exercises the full workflow pipeline by calling core modules directly.

**Marker:** `@pytest.mark.headless_e2e` (can run independently of GUI tests).

**Fixtures used:** `db`, `thumb_dir`, `image_factory`, `session_factory` (from `tests/conftest.py`) + `qtbot` (from `pytest-qt`) for Scanner signal waiting.

**Test pattern:**
```python
# Full-pipeline tests (real images + Scanner QThread):
#   1. Copy images from e2e_dataset/ into tmp_path
#   2. Set file mtimes programmatically for date-based tests
#   3. Create session + add_session_folder() + Scanner(db, sid, thumb_dir)
#   4. qtbot.waitSignal(scanner.scan_complete, timeout=30_000)
#   5. Validate duplicate groups match manifest expectations
#   6. apply_preset() or manual set_file_action()
#   7. PlanExecutor(db, sid, trash_root).run()  # synchronous
#   8. Assert: filesystem + DB (soft_deletes, file_actions, files.status)

# Direct-insert tests (skip scanning for speed):
#   1. Create real files in tmp_path via write_bytes()
#   2. db.insert_file() + db.update_pixel_hash() with shared pixel_hash
#   3. apply_preset() or manual set_file_action()
#   4. PlanExecutor.run() synchronously
#   5. Assert: filesystem + DB state
```

#### A. Full-Pipeline Tests (real images from `e2e_dataset/` + Scanner)

| ID | Test | Verifies |
|----|------|----------|
| H-01 | `test_full_pipeline_keep_largest` | Scan → KEEP_LARGEST_FILE → execute → files moved to trash, DB correct |
| H-02 | `test_full_pipeline_keep_newest` | Scan → KEEP_NEWEST → execute → newest file kept, older files trashed |
| H-07 | `test_full_pipeline_multiple_groups` | Scan → all manifest groups detected → cross-group isolation correct |
| H-08 | `test_full_pipeline_corrupt_files` | Scan with corrupt files → completes without crash, valid files hashed |
| H-11 | `test_scan_completes_within_timeout` | Scan all manifest images → completes in < 30 seconds |

**H-01: `test_full_pipeline_keep_largest`**
1. Copy all manifest group files into `tmp_path/scan/`.
2. Create session, `db.add_session_folder(sid, scan_dir)`.
3. Run Scanner, wait for `scan_complete` signal (timeout 30s).
4. Assert `db.get_duplicate_groups(sid)` count matches `manifest.expected_group_count`.
5. Call `apply_preset(db, sid, SelectionPreset.KEEP_LARGEST_FILE)`.
6. Assert `db.get_plan_summary(sid)["delete_count"]` matches expected.
7. Assert expected keeper files match manifest `expected_keeper.KEEP_LARGEST_FILE` where specified.
8. Run `PlanExecutor(db, sid, trash).run()`.
9. Assert: deleted files no longer exist on disk, kept files still exist.
10. Assert: `db.get_active_soft_deletes(sid)` count matches delete count.
11. Assert: each deleted file has `status == "deleted"`, each kept file has `status == "active"`.
12. Assert: `db.get_plan_summary(sid)["delete_count"] == 0` (all executed).

**H-02: `test_full_pipeline_keep_newest`**
Same as H-01 but:
- After copying images, set `os.utime()` on specific files to control `modified_at`.
- Apply `KEEP_NEWEST` preset.
- Assert the file with newest mtime is kept.

**H-07: `test_full_pipeline_multiple_groups`**
- Scan all manifest images.
- Verify each group in the manifest maps to a distinct `pixel_hash` in the DB.
- Apply preset, execute, verify each group independently.

**H-08: `test_full_pipeline_corrupt_files`**
- Include manifest `corrupt_files` in the scan directory.
- Assert scan completes (not crashed).
- Assert corrupt files are in DB with `pixel_hash IS NULL`.
- Assert valid files are hashed correctly.

**H-11: `test_scan_completes_within_timeout`**
- Copy all manifest images.
- Scan with `qtbot.waitSignal(scanner.scan_complete, timeout=30_000)`.
- The timeout itself IS the assertion — if scan takes longer, test fails.
- Additionally verify all files are in DB.

#### B. Direct-Insert Tests (skip scanning, faster)

| ID | Test | Verifies |
|----|------|----------|
| H-03 | `test_manual_keep_delete_decisions` | Per-file keep/delete → execute → correct files trashed |
| H-04 | `test_mixed_decisions_ignore_untouched` | Keep + delete + ignore → ignored files remain on disk + active |
| H-05 | `test_master_copy_protection` | apply_preset never marks last copy for deletion |
| H-06 | `test_two_file_auto_keep` | Delete one of two duplicates → preset keeps the other |
| H-09 | `test_soft_delete_and_recovery` | soft_delete → recover → file restored to original path |
| H-10 | `test_plan_summary_before_and_after` | Plan summary counts correct before and after execution |
| H-12 | `test_execution_within_time_boundary` | Execute 50 deletes in < 10 seconds |

**H-03: `test_manual_keep_delete_decisions`**
1. Create 4 real files in `tmp_path` (pairs: A1+A2, B1+B2).
2. Insert file rows with matching pixel_hashes per pair.
3. `db.set_file_action(sid, A1, "keep")`, `db.set_file_action(sid, A2, "delete")`.
4. `db.set_file_action(sid, B1, "delete")`, `db.set_file_action(sid, B2, "keep")`.
5. Execute → assert A2 and B1 are in trash, A1 and B2 still exist.
6. Assert DB: `file_actions.executed_at` is non-NULL for delete actions.

**H-04: `test_mixed_decisions_ignore_untouched`**
1. Create 3 files sharing one pixel_hash.
2. Mark file1 = "keep", file2 = "delete", file3 = "ignore".
3. Execute.
4. Assert: file1 exists + active, file2 in trash + deleted, file3 exists + active.
5. Assert: file3's `file_actions.executed_at IS NULL` (ignore is not executed).

**H-05: `test_master_copy_protection`**
1. Create a group of 2 files with same pixel_hash.
2. Call `apply_preset(db, sid, SelectionPreset.KEEP_LARGEST_FILE)`.
3. Assert exactly 1 "keep" action and 1 "delete" action (not 2 deletes).
4. Execute → assert one file remains.

**H-06: `test_two_file_auto_keep`**
1. Create exactly 2 files with same pixel_hash.
2. `apply_preset(db, sid, SelectionPreset.KEEP_LARGEST_FILE)`.
3. Assert: returns `(1, 1)` — 1 keep, 1 delete.
4. Execute → assert largest file still exists, smaller is trashed.

**H-09: `test_soft_delete_and_recovery`**
1. Create 2 files with same pixel_hash. Mark one for deletion.
2. Execute → file moved to trash, `soft_deletes` row created.
3. Get `trash_path` from `db.get_active_soft_deletes(sid)[0]["trash_path"]`.
4. Call `trash.recover(trash_path, original_path)`.
5. Assert: file restored to original location, trash file gone.

**H-10: `test_plan_summary_before_and_after`**
1. Create files, apply preset.
2. Before: `summary = db.get_plan_summary(sid)` → `delete_count > 0`, `keep_count > 0`.
3. Execute.
4. After: `summary = db.get_plan_summary(sid)` → `delete_count == 0` (all executed).

**H-12: `test_execution_within_time_boundary`**
1. Create 50 real files in `tmp_path`, insert rows, mark all for deletion.
2. `t0 = time.monotonic()`, `executor.run()`, `elapsed = time.monotonic() - t0`.
3. Assert `elapsed < 10.0`.
4. Assert all 50 files in trash.

---

### Tier 2: GUI E2E Tests (Secondary)

These require the built binary and pywinauto. They validate the real user experience for the planning and execution phases (the only gap in the existing GUI E2E suite).

#### Phase 4: Planning & Decision UI

**File:** `tests/e2e/test_e2e_planning.py`

| ID | Test | Description |
|----|------|-------------|
| P4-T01 | `test_smart_select_populates_actions` | After scan, trigger Smart Select → KEEP_LARGEST via UI; DB `file_actions` populated |
| P4-T02 | `test_plan_review_navigation` | After preset applied, navigate to Plan Review; delete count label visible |
| P4-T03 | `test_plan_review_impact_totals` | Plan Review shows correct "Storage saved" and "Files kept" totals |
| P4-T04 | `test_clear_plan_resets_all` | Click "Clear Plan" on Plan Review; `file_actions` emptied in DB |

#### Phase 4b: Execution & Recovery

**File:** `tests/e2e/test_e2e_execution.py`

| ID | Test | Description |
|----|------|-------------|
| P4b-T01 | `test_apply_changes_moves_files` | Click "Apply Changes" → confirm → files moved to trash |
| P4b-T02 | `test_execution_progress_completes` | Progress bars advance → "Done" button appears → click → back to dashboard |
| P4b-T03 | `test_post_execution_db_state` | After execution: `files.status = 'deleted'`, `soft_deletes` populated |
| P4b-T04 | `test_recovery_placeholder` | `xfail` — placeholder for future recovery UI test |

---

### Supporting Changes

#### `tests/e2e/conftest.py` (MODIFY)

Add helpers for the new tests:

```python
# ── Manifest loading ──────────────────────────────────────────────────────

E2E_IMAGES_DIR = Path(__file__).parent.parent / "fixtures" / "e2e_dataset"
E2E_MANIFEST_PATH = Path(__file__).parent.parent / "fixtures" / "e2e_manifest.json"

requires_e2e_images = pytest.mark.skipif(
    not E2E_IMAGES_DIR.exists(),
    reason="E2E fixture images not found — populate tests/fixtures/e2e_dataset/",
)

def load_e2e_manifest() -> dict:
    """Load and parse the E2E test manifest."""

def copy_e2e_images(tmp_path: Path, manifest: dict) -> Path:
    """Copy fixture images into a temp scan directory, return scan_dir path."""

# ── DB assertion helpers (for GUI tests polling the binary's DB) ──────────

def get_file_actions(appdata: Path, session_id: int) -> list[dict]:
    """Return all file_actions rows for direct assertion."""

def get_soft_deletes(appdata: Path, session_id: int) -> list[dict]:
    """Return soft_deletes rows for trash verification."""

def get_plan_summary_db(appdata: Path, session_id: int) -> dict:
    """Return plan summary from the binary's DB."""

def wait_for_soft_deletes(
    appdata: Path, expected_count: int, timeout: float = 30.0
) -> list[dict]:
    """Poll DB until soft_deletes reaches expected count or timeout."""
```

#### `pytest.ini` (MODIFY)

Add marker:
```ini
markers =
    e2e: end-to-end tests that build and exercise the compiled binary (deselect with -m "not e2e")
    headless_e2e: headless end-to-end workflow tests (no GUI, no build required)
```

---

## Files to Modify

| File | Change | Description |
|------|--------|-------------|
| `tests/fixtures/e2e_manifest.json` | **NEW** | Manifest mapping images to expected duplicate groups |
| `tests/e2e/test_e2e_headless.py` | **NEW** | 12 headless E2E tests (Tier 1) |
| `tests/e2e/test_e2e_planning.py` | **NEW** | 4 GUI planning tests (Tier 2) |
| `tests/e2e/test_e2e_execution.py` | **NEW** | 4 GUI execution tests (Tier 2) |
| `tests/e2e/conftest.py` | **MODIFY** | Add manifest loader, image copier, DB assertion helpers |
| `pytest.ini` | **MODIFY** | Add `headless_e2e` marker |

## Task Log

### Stage 1: Infrastructure

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Create `e2e_manifest.json` template | ⬜ | JSON schema with groups, unique, corrupt, counts |
| 1.2 | Add conftest helpers (manifest, images, DB assertions) | ⬜ | `load_e2e_manifest()`, `copy_e2e_images()`, `get_file_actions()`, etc. |
| 1.3 | Add `headless_e2e` marker to `pytest.ini` | ⬜ | New marker for headless-only runs |

### Stage 2: Headless E2E Tests

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Full-pipeline tests (H-01, H-02, H-07, H-08, H-11) | ⬜ | Real images + Scanner + execute + verify |
| 2.2 | Direct-insert tests (H-03, H-04, H-05, H-06) | ⬜ | Decision logic + execution correctness |
| 2.3 | Recovery + summary tests (H-09, H-10) | ⬜ | soft_delete → recover, plan_summary before/after |
| 2.4 | Performance boundary tests (H-11, H-12) | ⬜ | Scan < 30s, execution < 10s |

### Stage 3: GUI E2E Tests

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Planning tests (P4-T01 through P4-T04) | ⬜ | Smart Select, Plan Review, Clear Plan |
| 3.2 | Execution tests (P4b-T01 through P4b-T04) | ⬜ | Apply Changes, progress, post-execution DB |

### Stage 4: Verification

| # | Task | Status | Details |
|---|------|--------|---------|
| 4.1 | Run headless E2E tests, fix failures | ⬜ | `pytest tests/e2e/test_e2e_headless.py -m headless_e2e` |
| 4.2 | Run full GUI E2E suite (with build), fix failures | ⬜ | `pytest tests/e2e/ -m e2e` |
| 4.3 | Run existing unit tests to verify no regressions | ⬜ | `pytest tests/unit/ --no-cov -q` |

### Task Dependency Order

```
Task 1.1 (manifest) ──────┐
Task 1.2 (conftest) ──────┼──► Task 2.1 (full-pipeline) ──┐
Task 1.3 (pytest.ini) ────┘    Task 2.2 (direct-insert) ──┼──► Task 4.1 (verify headless)
                                Task 2.3 (recovery)  ──────┤
                                Task 2.4 (performance) ────┘
                           └──► Task 3.1 (planning GUI) ──┐
                                Task 3.2 (execution GUI) ──┼──► Task 4.2 (verify GUI)
                                                           └──► Task 4.3 (regressions)
```

## Verification

### Run headless E2E tests (fast, no build required)

```bash
cd dejaview
python -m pytest tests/e2e/test_e2e_headless.py -m headless_e2e --no-cov -v
```

Expected: 12 tests pass (5 full-pipeline + 7 direct-insert), total runtime < 60 seconds. Full-pipeline tests skip gracefully if `tests/fixtures/e2e_dataset/` is not populated.

### Run full GUI E2E suite (requires build + display)

```bash
cd dejaview
python -m pytest tests/e2e/ -m e2e --no-cov -v
```

Expected: all existing E2E tests (build, launch, scan, pause, filters, sharing, settings) plus new planning + execution tests pass. Build step runs once (session-scoped fixture).

### Run existing tests (regression check)

```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q
```

Expected: all pre-existing tests continue to pass, no regressions.

### Manual verification checklist

- [ ] Headless tests produce clear pass/fail output with descriptive assertion messages
- [ ] Full-pipeline tests correctly detect duplicate groups from manifest images
- [ ] Performance tests have generous timeouts that don't flake on slow CI machines
- [ ] GUI tests skip gracefully when pywinauto or built binary is unavailable
- [ ] Missing `e2e_dataset/` directory causes graceful skip, not crash
