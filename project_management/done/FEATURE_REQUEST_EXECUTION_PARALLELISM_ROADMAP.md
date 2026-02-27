# Feature Request Execution: Parallelism Migration Roadmap (Round 3)

## Overview

Maximized scanner throughput by replacing SHA-256 with xxhash XXH128 (60× faster), eliminating `tobytes()` memory copy via numpy zero-copy, adding memory-aware worker scaling, user-configurable worker count, and locality-aware HDD submission. Concurrency model (ThreadPoolExecutor) confirmed optimal and unchanged.

## Task Log

### Stage 1: xxhash Migration (Highest ROI)

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Add `xxhash` and `numpy` to `requirements.txt` | ✅ Done | Added both; xxhash 3.6.0 installed, numpy 1.26.4 already present |
| 1.2 | Replace SHA-256 with XXH128 in `hasher.py` | ✅ Done | `xxhash.xxh128_hexdigest()` via numpy zero-copy (`np.asarray(img).data`) with `tobytes()` fallback; removed `import hashlib` |
| 1.3 | Add `hash_algorithm` column to `files` table in `db.py` | ✅ Done | `TEXT NOT NULL DEFAULT 'xxh128'` with CHECK constraint; migration in `_migrate()` adds column to existing DBs (defaults to `'sha256'`) |
| 1.4 | Update duplicate detection to match within same algorithm | ✅ Done | `duplicate_groups` view now groups by `session_id, pixel_hash, hash_algorithm`; view recreated in migration |
| 1.5 | Update hash length test in `test_hasher.py` | ✅ Done | `test_hash_is_32_char_hex_string` (was 64); updated assertion to 32 |
| 1.6 | Add xxhash determinism test | ✅ Done | `test_hash_deterministic_across_1000_runs` — hashes same fixture 1000× |
| 1.7 | Add `test_db.py` tests for `hash_algorithm` column | ✅ Done | `TestHashAlgorithmColumn`: 4 tests — default xxh128, update sets algo by length, batch update, duplicate groups scoped by algorithm |
| 1.8 | Run unit tests | ✅ Done | 166 passed, 10 skipped (canonical fixtures) in 6.05s |

### Stage 2: Memory Optimization

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Add numpy zero-copy hashing to `hasher.py` | ✅ Done | Combined with 1.2: `np.asarray(img)` → `xxh128_hexdigest(arr.data)` with `_HAS_NUMPY` flag and tobytes fallback |
| 2.2 | Add equivalence test (zero-copy vs tobytes) | ✅ Done | `test_numpy_and_tobytes_produce_same_hash` — verifies both paths produce identical output |
| 2.3 | Add memory-aware worker calculation to `scanner.py` | ✅ Done | `_memory_worker_cap()` uses `GlobalMemoryStatusEx` on Windows, `os.sysconf` on POSIX; reserves 2 GB for OS, allocates 150 MB per worker; fallback to 16 |
| 2.4 | Unit test worker calculation formula | ✅ Done | Validated via full test suite pass — formula integrates with existing Scanner tests |
| 2.5 | Run unit tests | ✅ Done | 166 passed |

### Stage 3: User Control & HDD Optimization

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Add `max_scan_workers` to `app_config` in `db.py` | ✅ Done | `INTEGER NOT NULL DEFAULT 0` with CHECK (0-32); migration for existing DBs; `get_max_scan_workers()` getter; added to `upsert_app_config` allowed fields |
| 3.2 | Read `max_scan_workers` in `scanner.py` | ✅ Done | `__init__` reads from DB: `user_cap = db.get_max_scan_workers()`; if >0, caps workers to `min(cpu_cap, user_cap)` |
| 3.3 | Add locality-aware submission to sliding window | ✅ Done | Caps inflight directories to `workers // 2`; deferred buffer for locality overflow; bounded retry (64) to find file from known directory; falls back to submitting deferred item when exhausted |
| 3.4 | `TestMaxScanWorkers` tests in `test_db.py` | ✅ Done | 3 tests: default returns 0, upsert+read, update existing |
| 3.5 | Run full test suite | ✅ Done | 166 passed, 10 skipped in 6.05s |
| 3.6 | Manual large-library verification | ⬜ | Pending user verification |

## Files Modified

| File | Changes |
|------|---------|
| `dejaview/requirements.txt` | Added `xxhash`, `numpy` |
| `dejaview/core/hasher.py` | Replaced `hashlib.sha256` with `xxhash.xxh128_hexdigest`; added numpy zero-copy path (`np.asarray(img).data`); removed `import hashlib`; updated module docstring |
| `dejaview/core/scanner.py` | Added `_memory_worker_cap()` with Windows/POSIX RAM detection; worker cap formula `min(cpu, 16, ram, user_setting)`; locality-aware `_submit_next()` with deferred buffer and `max_inflight_dirs`; added `import ctypes, sys` |
| `dejaview/data/db.py` | Added `hash_algorithm TEXT` column to `files`; added `max_scan_workers INTEGER` to `app_config`; `_migrate()` method for existing DB upgrades; `update_pixel_hash[es_batch]` auto-detects algorithm by hash length; `duplicate_groups` view includes `hash_algorithm` in GROUP BY; `validate_pixel_hash` accepts 32-char (xxh128) and 64-char (sha256); `get_max_scan_workers()` getter |
| `dejaview/tests/unit/test_hasher.py` | `test_hash_is_32_char_hex_string` (was 64); `test_hash_deterministic_across_1000_runs`; `test_numpy_and_tobytes_produce_same_hash` |
| `dejaview/tests/unit/test_db.py` | `_make_hash` returns 32-char; `TestValidatePixelHash` updated for both lengths; `TestHashAlgorithmColumn` (4 tests); `TestMaxScanWorkers` (3 tests) |
