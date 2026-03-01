# RCA: Progressive Scan Slowdown (30k+ files)

**Date:** 2026-02-28
**Symptom:** Each batch/directory takes progressively longer to process during a 30k-file scan. No memory leak observed (steady 53%). Telemetry CSV confirms the pattern.

---

## Telemetry Validation (perf_20260228_075820.csv)

CSV analysis of the 8-hour, 70k-file scan produced these findings:

| Hypothesis | Predicted Pattern | Actual CSV Evidence | Verdict |
|-----------|-------------------|---------------------|---------|
| RC#1: O(N²) tree lookups | `pending_hash_ids` peaks grow over time | Peaks **decrease** (331 → 13) | **Not the bottleneck** |
| RC#2: O(N) folder recompute | Directory-hashed gaps grow | 1.76x gap growth (moderate) | **Minor contributor** |
| RC#3: DB batch cost growth | `db_batch_ms` grows over time | **4.43x growth** (173ms → 767ms, peak 4,125ms) | **Primary bottleneck** |

**Throughput degradation:** 33 files/sec (peak) → 8 files/sec (end) = **4x drop**, matching the 4.43x DB cost increase almost exactly.

**Key insight:** The `_emit_deferred_duplicates()` call was un-timed and ran every 500 files, performing a full table scan via the `duplicate_groups` view (no composite index). The `update_pixel_hashes_batch()` UPDATE+COMMIT also slowed with growing WAL and 4 separate index updates per row.

---

## Root Cause #1 (Primary): DB Query & Batch Cost Growth

**File:** `core/scanner.py`, `data/db.py`
**Severity:** Critical — 4.43x cost growth, directly causes the throughput collapse

Two DB-side issues compound:

### 1a. `_emit_deferred_duplicates()` full table scan
`get_all_duplicate_file_ids()` executes a subquery through the `duplicate_groups` view (GROUP BY + HAVING on the full `files` table). Called every 500 files, growing linearly in cost.

### 1b. Missing composite index
The WHERE clauses `session_id = ? AND pixel_hash IS NOT NULL AND status = 'active'` hit three separate single-column indexes. SQLite can only use one per query; the rest require table scans.

### 1c. WAL checkpoint pressure
Each `update_pixel_hashes_batch()` commits after 32 rows, maintaining 4 separate indexes. As WAL grows, checkpoint cost increases.

**Fixes applied:**
- Added composite index `(session_id, pixel_hash, status)` — covers the duplicate view and all file queries
- Replaced `_emit_deferred_duplicates()` with O(1) incremental detection in memory (hash→file_ids dict)
- Eliminated `_DUPE_CHECK_INTERVAL` and the periodic full-table query entirely

---

## Root Cause #2 (Secondary): O(N) Tree Walk in `_compute_folder_duplication()`

**File:** `ui/results_panel.py`
**Severity:** Moderate — 1.76x slowdown confirmed by telemetry

`_compute_folder_duplication()` walked the **entire tree** at every directory boundary.

**Fix applied:** Incremental recompute — only the completed directory's subtree + parent chain are walked. Uses cached `ROLE_FOLDER_DUP_COUNT` data role for O(folder_size) per directory instead of O(total_tree_size).

---

## Root Cause #3 (Preventive): O(N²) Tree Lookups in `_find_file_item()`

**File:** `ui/results_panel.py`
**Severity:** Not currently dominant (telemetry showed UI keeping up), but would become the bottleneck after DB fixes

`_find_file_item()` performed a recursive O(N) linear scan of the entire tree.

**Fix applied:** Added `_file_id_to_item: dict[int, QStandardItem]` populated in `_add_file_to_tree()`. Replaced recursive search with O(1) dict lookup.

---

## Root Cause #4 (Deferred): Thumbnail Directory Growth

**File:** `core/hasher.py` — `thumb_path.exists()` check
**Severity:** Low on NTFS, potentially moderate with antivirus

Not addressed in this round. Can be fixed by sharding thumbnails into subdirectories by hash prefix if needed.

---

## Fix Priority (Corrected by Telemetry)

| Priority | Fix | Impact | Status |
|----------|-----|--------|--------|
| **P0** | Composite index + incremental dupe detection | Eliminates DB bottleneck | **Done** |
| **P1** | Incremental folder recompute | Eliminates O(N×D) → O(D) | **Done** |
| **P1** | `_file_id_to_item` dict | Eliminates O(N²) → O(N) (preventive) | **Done** |
| **P3** | Shard thumbnails directory | Reduces I/O latency | Deferred |
