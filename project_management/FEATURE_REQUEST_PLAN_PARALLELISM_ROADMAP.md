# DejaView — Feature Request Plan: Parallelism Migration Roadmap (Round 3)

## Overview

Maximize scanner throughput on high-core-count hardware by replacing the SHA-256 hash with xxhash (60x faster), eliminating the `tobytes()` memory copy, adding memory-aware worker scaling, and providing user control over worker count. The concurrency model (ThreadPoolExecutor with GIL-releasing C extensions) is already correct and does not change.

## Problem

After R1 (batched DB, sliding window) and R2 (deferred dupe detection, proportional throttling, decoupled ETA), the scanner pipeline is well-optimized. However, profiling reveals these remaining bottlenecks:

1. **SHA-256 is overkill** — `pixel_hash` is used only for duplicate grouping and thumbnail naming. No cryptographic properties needed. SHA-256 runs at ~500 MB/s; for a 24MP image (69 MB pixel data), hashing alone takes ~138ms per file. Non-cryptographic alternatives are 60x faster.

2. **`tobytes()` memory copy** — `hasher.py:89` creates a full copy of the pixel buffer before hashing. For 24MP images, each worker holds ~140 MB peak (decoded pixels + copy). With 16 workers, that's ~2.2 GB just for pixel buffers.

3. **No memory-aware worker cap** — Worker count is `min(cpu_count, 16)`. A 16-core machine with 4 GB RAM will swap under full load.

4. **HDD random seek thrashing** — 16 workers requesting files from different directories creates a random I/O pattern. HDD throughput drops from 150 MB/s sequential to 1-5 MB/s random.

5. **No user control** — Power users on NVMe/high-RAM systems can't override the auto-detected worker count.

### Why the GIL Is NOT the Bottleneck

Every CPU-intensive operation in `hasher.py` releases the GIL:

| Step | Operation | GIL Released? |
|------|-----------|:---:|
| 1 | `Image.open()` — Pillow C extension | Yes |
| 2 | `ImageOps.exif_transpose()` — C pixel ops | Yes |
| 3 | `img.convert("RGB")` — C color conversion | Yes |
| 4 | `hashlib.sha256(img.tobytes())` — OpenSSL C | Yes |
| 5 | `img.thumbnail()` + `img.save()` — C Lanczos + JPEG encode | Yes |

**Consequence:** `ThreadPoolExecutor` already achieves true OS-level parallelism. `ProcessPoolExecutor` would add IPC serialization overhead for zero gain.

### Alternative Concurrency Models Evaluated

#### `os.scandir` + Producer/Consumer for Discovery — REJECTED

- `os.walk()` already uses `os.scandir()` internally since Python 3.5. No speed difference.
- Producer/Consumer overlap (start hashing while discovery runs) is blocked by the size-duplicate pre-filter at `scanner.py:295`: `get_unhashed_files_grouped_by_size()` requires ALL files discovered to identify sizes appearing ≥2 times. Without the filter, 100% of files get hashed instead of ~20-40% candidates — wasting 2-5x more CPU.

#### Dedicated Writer Thread for DB — DEFERRED

- Workers never touch the DB. The `db_lock` at `scanner.py:327` only protects `update_pixel_hashes_batch()` called from the drain loop on the Scanner QThread itself.
- Lock held for <0.5ms per batch of 32 rows. Zero contention.
- A writer thread + Queue adds complexity for no measurable gain. Reconsider only if DB writes become a bottleneck in future.

#### asyncio for Orchestration — REJECTED

- Scanner is a QThread. Running asyncio inside it requires a separate event loop + `qasync` bridge for Qt signals.
- `concurrent.futures.wait(timeout=0.1)` already implements effective backpressure.
- Would require rewriting ~450 lines of scanner.py for zero throughput gain.

## Solution

### 1. Replace SHA-256 with xxhash XXH128 (`core/hasher.py`)

Add `xxhash` dependency. Replace:
```python
pixel_hash = hashlib.sha256(img.tobytes()).hexdigest()
```
With:
```python
pixel_hash = xxhash.xxh128_hexdigest(img.tobytes())
```

XXH128 runs at ~30 GB/s vs SHA-256 at ~500 MB/s (60x faster). For 24MP (69 MB), hash time drops from ~138ms to ~2.3ms. Over 50,000 images this saves ~113 minutes.

128-bit digest has negligible collision probability (~10^-20 for 1 billion images). No cryptographic properties needed for duplicate grouping.

**DB migration:** Add `hash_algorithm TEXT DEFAULT 'sha256'` column to `files` table. New scans use `'xxh128'`. Duplicate detection must match within the same algorithm. Existing sessions remain valid; re-scanning updates hashes.

### 2. Eliminate `tobytes()` memory copy (`core/hasher.py`)

Use `numpy.asarray(img)` to get a zero-copy view of Pillow's internal buffer, then hash directly:
```python
import numpy as np
arr = np.asarray(img)                          # zero-copy view
pixel_hash = xxhash.xxh128_hexdigest(arr.data) # hash buffer in-place
```

Halves peak per-worker memory from ~140 MB to ~70 MB for 24MP images.

**Fallback:** If numpy is not available, fall back to `xxhash.xxh128_hexdigest(img.tobytes())` (still 60x faster than SHA-256, just without the memory saving).

### 3. Memory-aware worker count (`core/scanner.py`)

At the start of `_run_pass2`, detect available RAM and cap workers:
```python
# Windows: ctypes.windll.kernel32.GlobalMemoryStatusEx
# Fallback: conservative default (8 workers)
memory_workers = max(2, available_mb // 150)
workers = min(self._max_workers, memory_workers)
```

Prevents swapping on machines where `cpu_count > available_RAM / 150MB`.

### 4. User-configurable max workers (`data/db.py`, `core/scanner.py`, settings UI)

Add `max_scan_workers INTEGER DEFAULT 0` to `app_config` (0 = auto-detect). Expose in Settings dialog. Scanner reads on start and uses as upper bound.

### 5. Locality-aware submission for HDD (`core/scanner.py`)

Track distinct directories with in-flight futures. When inflight directories exceed `workers // 2`, delay submitting files from new directories. Keeps disk reads localized.

On SSD the threshold is high enough to have no effect. On HDD, reduces seek thrashing for 2-5x throughput improvement.

## Acceleration Libraries Evaluation

| Library | ROI | Recommendation |
|---------|-----|----------------|
| **xxhash** | HIGH — 60x faster hash, ~10 lines changed | Adopt (task 1) |
| **numpy** (zero-copy hash) | HIGH — halves per-worker memory | Adopt (task 2) |
| **Pillow-SIMD** | MEDIUM — 2-6x decode/resize, no Windows wheels | Document only |
| **PyTurboJPEG** | LOW — Pillow likely already links libjpeg-turbo | Skip |
| **numba** | NONE — no pure-Python in hot path to JIT | Reject |
| **imagehash** | NONE — perceptual hashing is a different feature | Reject |
| **ProcessPoolExecutor** | NEGATIVE — IPC overhead, zero GIL gain | Reject |
| **asyncio** | NEGATIVE — Qt event loop conflict, full rewrite needed | Reject |

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    Scanner (QThread)                              │
│                                                                  │
│  Pass 1: Discovery [NO CHANGE]                                   │
│  ─────────────────────────────                                   │
│  Single-thread os.walk() → batch insert 100 rows → DB           │
│                                                                  │
│  Pass 2: Hashing Pipeline [ENHANCED]                             │
│  ───────────────────────────────────                             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Memory-Aware Scheduler [NEW]                           │     │
│  │  workers = min(cpu_cores, 16, avail_RAM // 150MB,       │     │
│  │                user_setting or auto)                     │     │
│  │  Locality limit: max inflight dirs = workers // 2       │     │
│  └─────────────────────┬───────────────────────────────────┘     │
│                        │                                         │
│  ┌─────────────────────v───────────────────────────────────┐     │
│  │  ThreadPoolExecutor  (N workers, GIL-free)              │     │
│  │                                                         │     │
│  │  Worker 1 ─┐                                            │     │
│  │  Worker 2 ─┤  hash_file() [MODIFIED]:                   │     │
│  │  Worker 3 ─┤    Image.open → exif_transpose → RGB       │     │
│  │    ...     │    xxh128(pixel_buffer)  ← 60x faster      │     │
│  │  Worker N ─┘    zero-copy via numpy   ← 50% less RAM    │     │
│  │                 thumbnail + save (if not exists)         │     │
│  └─────────────────────┬───────────────────────────────────┘     │
│                        │                                         │
│  ┌─────────────────────v───────────────────────────────────┐     │
│  │  Drain Loop [NO CHANGE]                                 │     │
│  │  wait(FIRST_COMPLETED) → batch 32 → db_lock → DB       │     │
│  │  Emit hash_complete, progress_updated, directory_hashed │     │
│  │  Deferred dupe detection every 500 files                │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
└────────────────────────┬─────────────────────────────────────────┘
                         │ Qt signals (auto-queued)
                         v
┌──────────────────────────────────────────────────────────────────┐
│  Main Thread (Qt) [NO CHANGE]                                    │
│  ScanControl: progress bar + 1s ETA timer                        │
│  ResultsPanel: 200ms debounce, directory-aware flush             │
└──────────────────────────────────────────────────────────────────┘
```

## Files to Modify

| File | Change |
|------|--------|
| `dejaview/core/hasher.py` | Replace SHA-256 with xxhash XXH128; use numpy zero-copy buffer; add `HASH_ALGORITHM` constant |
| `dejaview/core/scanner.py` | Memory-aware worker cap; locality-aware submission; read user `max_scan_workers` setting |
| `dejaview/data/db.py` | Add `hash_algorithm` column to files table; add `max_scan_workers` to app_config; migration logic |
| `dejaview/tests/unit/test_hasher.py` | Update all expected hash values; add xxhash determinism test; add numpy zero-copy equivalence test |
| `dejaview/tests/unit/test_db.py` | Test `hash_algorithm` column; test `max_scan_workers` config |
| `dejaview/requirements.txt` | Add `xxhash`; add `numpy` (if not already transitive) |

## Task Log

### Stage 1: xxhash Migration (Highest ROI)

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Add `xxhash` to `requirements.txt` | ⬜ | Pure C extension, Windows wheels on PyPI |
| 1.2 | Replace SHA-256 with XXH128 in `hasher.py` | ⬜ | `xxhash.xxh128_hexdigest(img.tobytes())` |
| 1.3 | Add `hash_algorithm` column to `files` table in `db.py` | ⬜ | `TEXT DEFAULT 'sha256'`; new rows get `'xxh128'` |
| 1.4 | Update duplicate detection to match within same algorithm | ⬜ | `WHERE hash_algorithm = ?` in relevant queries |
| 1.5 | Update all 66 expected hash values in `test_hasher.py` | ⬜ | Regenerate from fixture images |
| 1.6 | Add xxhash determinism test | ⬜ | Hash same fixture 1000x, verify identical |
| 1.7 | Add `test_db.py` tests for `hash_algorithm` column | ⬜ | Insert/query with both algorithms |
| 1.8 | Run unit tests | ⬜ | `python -m pytest tests/unit/ --no-cov -q` |

### Stage 2: Memory Optimization

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Add numpy zero-copy hashing to `hasher.py` | ⬜ | `np.asarray(img)` → `xxh128_hexdigest(arr.data)` with tobytes fallback |
| 2.2 | Add equivalence test (zero-copy vs tobytes) | ⬜ | Verify identical hash output for all fixture images |
| 2.3 | Add memory-aware worker calculation to `scanner.py` | ⬜ | `ctypes.windll.kernel32.GlobalMemoryStatusEx` with fallback |
| 2.4 | Unit test worker calculation formula | ⬜ | Mock memory values, verify capping |
| 2.5 | Run unit tests | ⬜ | `python -m pytest tests/unit/ --no-cov -q` |

### Stage 3: User Control & HDD Optimization

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Add `max_scan_workers` to `app_config` in `db.py` | ⬜ | `INTEGER DEFAULT 0` (0 = auto) |
| 3.2 | Read `max_scan_workers` in `scanner.py` | ⬜ | Use as upper bound in worker calculation |
| 3.3 | Add locality-aware submission to sliding window | ⬜ | Cap inflight directories at `workers // 2` |
| 3.4 | Expose setting in Settings dialog UI | ⬜ | Tooltip: "0 = auto. Lower for HDD. Higher for NVMe + lots of RAM." |
| 3.5 | Run full test suite | ⬜ | `python -m pytest tests/unit/ tests/integration/ --no-cov` |
| 3.6 | Manual large-library verification | ⬜ | See Verification section |

## Verification

```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q           # fast unit tests
python -m pytest tests/unit/ tests/integration/ --no-cov  # full suite
```

Manual test:
1. Scan a large folder (1000+ images) on internal SSD
2. Verify hash values are 32-char hex (XXH128) not 64-char (SHA-256)
3. Task Manager: memory usage should be lower than before (fewer tobytes copies)
4. Pause/resume works — resumed scan uses same hash algorithm
5. Existing sessions with SHA-256 hashes: duplicates still detected within session
6. New session: duplicates detected with XXH128 hashes
7. If `max_scan_workers` set to 2: verify only 2 workers active (CPU usage low)
8. If `max_scan_workers` set to 0: verify auto-detection caps by RAM
9. Scan from USB/HDD: verify locality-aware submission (directories complete in order)
