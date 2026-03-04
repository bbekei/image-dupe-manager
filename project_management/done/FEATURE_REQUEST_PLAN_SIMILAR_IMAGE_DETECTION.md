# DejaView — Feature Request Plan: Similar Image Detection

## Context

DejaView currently detects only **exact pixel-identical duplicates** via xxHash-128 of decoded RGB bytes. Users' photo libraries contain a large category of near-duplicates that this misses: rescaled copies shared via email/messaging, lightly edited variants, burst shots taken seconds apart, and re-encoded copies at different JPEG quality. This feature adds opt-in perceptual similarity detection with a dedicated review flow, keeping it fully separate from the existing exact-duplicate workflow.

## Problem

Typical photo libraries accumulate near-duplicate images that waste significant storage but differ just enough to defeat pixel-hash matching:

| Category | Example | Why pixel-hash misses it |
|---|---|---|
| **Rescaled copies** | Photo shared via WhatsApp (resized to 1600px) alongside 4032px original | Different dimensions = different pixel bytes |
| **Re-encoded copies** | Same photo saved at JPEG q=95 vs q=75 | JPEG artifacts differ |
| **Lightly edited variants** | Cropped, brightness-adjusted, or Instagram-filtered copy | Pixels altered by edit |
| **Burst/series shots** | 5 photos of same scene taken over 3 seconds | Slightly different content |
| **Cross-device copies** | Photo AirDropped then re-synced through iCloud | Re-encoding during transfer |

## User Benefits per Category

1. **Rescaled copies** — User keeps the highest-resolution original, deletes the smaller "shared" copies. Recommendation: *keep highest resolution*.
2. **Re-encoded copies** — User keeps the best-quality version (largest file). Recommendation: *keep largest file*.
3. **Edited variants** — User sees original and edited side-by-side and decides which to keep. Recommendation: *keep highest resolution* (if same dimensions, *keep largest file*).
4. **Burst shots** — User picks the best shot from a burst sequence, deletes the rest. Recommendation: *show all side-by-side*, let user pick manually.
5. **Cross-device copies** — Same as re-encoded; user keeps the best quality. Recommendation: *keep largest file*.

## Solution

### Algorithm: Perceptual Hashing (pHash)

**Library:** `imagehash` (PyPI) — actively maintained, works with Pillow directly.

**How pHash works:**
1. Resize image to 32x32 (ignoring aspect ratio)
2. Apply DCT (discrete cosine transform)
3. Keep top-left 8x8 DCT coefficients (low frequencies = structure)
4. Threshold against median → 64-bit hash

**Comparison:** Hamming distance (XOR bit count) between two 64-bit hashes. Range 0–64.

**Threshold recommendations:**
| Distance | Meaning | Use case |
|---|---|---|
| 0 | Identical perceptual structure | Same image, different encoding |
| 1–4 | Nearly identical | Rescaled, re-encoded, minor crop |
| 5–8 | Similar | Moderate edits, same scene |
| 9–12 | Possibly similar | Significant edits, may be false positive |
| 13+ | Different images | Not related |

**Default threshold: 8** (catches rescaled + re-encoded + light edits, low false-positive rate).

**Performance:** ~2–5ms per image on top of existing Pillow decode. For 10k images, Pass 3 adds ~20–50 seconds. Grouping via O(n²) on unique pixel_hash representatives takes <2s for 30k unique hashes.

### Architecture: Pass 3 (dual-hash) + Separate UI Flow

```
Scanner Pipeline (modified):
  Pass 1: Discovery — walks all folders, inserts ALL files (unchanged)
  Pass 2: Pixel hashing — size-duplicate candidates only (unchanged)
  Pass 3: Dual hashing — ALL remaining files (opt-in, new)
           Computes BOTH pixel_hash AND perceptual_hash for every file
           that still lacks either hash. For files already pixel-hashed
           in Pass 2, only adds pHash. For files skipped by the size
           pre-filter, computes pixel_hash + thumbnail + pHash.
       3b: Post-hash duplicate refresh — re-runs exact-duplicate detection
           on newly pixel-hashed files (may discover additional exact
           duplicates that the size pre-filter missed)
       3c: Similarity grouping — Union-Find transitive closure on pHash

UI Flow (new, parallel to existing):
  Dashboard ──► "Similar Images" card ──► SimilarityScreen
                                              ├── Group tree (left)
                                              ├── Compare panel (right)
                                              ├── Recommendations
                                              └── Keep/Delete/Ignore per file
                                                        │
                                                        v
                                                  Plan Review (shared)
                                                        │
                                                        v
                                                  Execution (shared)
```

**Pass 3 dual-hash rationale:** When similarity is enabled, Pass 3 opens ALL files anyway. Computing pixel_hash alongside pHash costs zero extra I/O. This fills in pixel_hashes for files the size pre-filter skipped (different byte sizes but potentially identical pixels — e.g., same photo with stripped EXIF metadata). After Pass 3, a duplicate refresh pass (3b) checks the newly-hashed files for exact duplicates, enriching the existing exact-duplicate flow.

**Discovery (Pass 1) is unchanged.** It already discovers ALL files regardless of mode. The change is entirely in what Pass 3 computes.

**Key design principle:** Exact duplicates (same `pixel_hash`) are NEVER shown in similarity groups. Similarity groups require ≥2 distinct pixel hashes. The two flows are completely independent.

---

## Implementation Phases

### Phase S1: Perceptual Hash Infrastructure

#### S1.1 New dependency

Add `imagehash` to `requirements.txt`.

#### S1.2 Extend `core/hasher.py`

Modify `hash_file()` to optionally compute pHash and capture dimensions:

```python
def hash_file(
    path: str | Path,
    thumb_dir: str | Path,
    compute_phash: bool = False,
) -> tuple[str, str, str | None, int | None, int | None]:
    """Returns (pixel_hash, thumbnail_path, perceptual_hash, width, height).

    perceptual_hash/width/height are None when compute_phash=False.
    """
```

The image is already open and EXIF-transposed in the pipeline — computing pHash at that point costs only 2–5ms extra CPU, zero extra I/O.

Add helper:
```python
def compute_perceptual_hash(img: Image.Image) -> str:
    """Compute pHash of an already-opened, EXIF-transposed RGB image."""
    import imagehash
    return str(imagehash.phash(img))
```

#### S1.3 Database schema changes (`data/db.py`)

New columns on `files`:
```sql
ALTER TABLE files ADD COLUMN perceptual_hash TEXT;
ALTER TABLE files ADD COLUMN width  INTEGER;
ALTER TABLE files ADD COLUMN height INTEGER;
CREATE INDEX IF NOT EXISTS idx_files_phash ON files(perceptual_hash);
```

New tables:
```sql
CREATE TABLE IF NOT EXISTS similarity_groups (
    id                     INTEGER PRIMARY KEY,
    session_id             INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    created_at             TEXT NOT NULL,
    status                 TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewed', 'actioned')),
    member_count           INTEGER NOT NULL DEFAULT 0,
    representative_file_id INTEGER REFERENCES files(id)
);

CREATE TABLE IF NOT EXISTS similarity_group_members (
    id        INTEGER PRIMARY KEY,
    group_id  INTEGER NOT NULL REFERENCES similarity_groups(id) ON DELETE CASCADE,
    file_id   INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    distance  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (group_id, file_id)
);
```

Session-level opt-in:
```sql
ALTER TABLE sessions ADD COLUMN similarity_enabled INTEGER NOT NULL DEFAULT 0;
```

#### S1.4 DB methods

```python
# Perceptual hash storage
def update_perceptual_hashes_batch(self, updates: list[tuple[int, str, int, int]]) -> None: ...
def get_unhashed_phash_files(self, session_id: int) -> list[Row]: ...
def get_files_with_phash(self, session_id: int) -> list[Row]: ...

# Similarity group CRUD
def create_similarity_group(self, session_id, created_at, representative_file_id) -> int: ...
def add_similarity_group_members_batch(self, rows: list[tuple[int, int, int]]) -> None: ...
def clear_similarity_groups(self, session_id) -> None: ...
def get_similarity_groups(self, session_id) -> list[Row]: ...
def get_similarity_group_count(self, session_id) -> int: ...
def get_similarity_group_members(self, group_id) -> list[Row]: ...
def get_similarity_group_file_count(self, session_id) -> int: ...
def update_similarity_group_status(self, group_id, status) -> None: ...
```

---

### Phase S2: Scanner Extension

#### S2.1 Pass 3 in `core/scanner.py`

Add `similarity_enabled` parameter to `Scanner.__init__`. When enabled, after Pass 2:

**Pass 3 — Dual hashing (ALL files):**
- Query `get_files_needing_hashes(session_id)` — returns files where `perceptual_hash IS NULL` (this includes files skipped by Pass 2's size pre-filter AND files that were pixel-hashed but lack pHash)
- For each file, call `hash_file(path, thumb_dir, compute_phash=True)`
- If the file already has a `pixel_hash` (from Pass 2): only store `perceptual_hash`, `width`, `height`
- If the file lacks `pixel_hash` (skipped by size filter): store ALL five values (`pixel_hash`, `thumbnail_path`, `perceptual_hash`, `width`, `height`)
- Same ThreadPoolExecutor sliding-window pipeline as Pass 2

**Pass 3b — Post-hash duplicate refresh:**
- After Pass 3 completes, run a SQL query to find newly-created exact-duplicate groups among files that were pixel-hashed in Pass 3 (not Pass 2)
- Emit `duplicate_found` signals for any new groups discovered
- This enriches the exact-duplicate card on the Dashboard without requiring a separate user action

**Pass 3c — Similarity grouping:**
- Call `build_similarity_groups()` on all files with pHash
- Persist groups to DB, emit `similarity_grouping_complete(count)`

New signals:
```python
similarity_progress = pyqtSignal(int, int)         # current, total
similarity_grouping_complete = pyqtSignal(int)      # group_count
```

New DB method needed:
```python
def get_files_needing_hashes(self, session_id: int) -> list[Row]:
    """Files where perceptual_hash IS NULL — candidates for Pass 3.
    Includes files skipped by the size pre-filter (pixel_hash IS NULL)
    AND files already pixel-hashed (pixel_hash IS NOT NULL) that lack pHash."""
```

#### S2.2 New module: `core/similarity.py`

Pure-function grouping algorithm (no DB, no Qt):

```python
def hamming_distance(hash_hex_a: str, hash_hex_b: str) -> int: ...

def build_similarity_groups(
    files: list[dict],
    threshold: int = 8,
) -> list[list[dict]]:
    """Group files by perceptual hash similarity using Union-Find.

    1. Deduplicate by pixel_hash (one representative per exact-duplicate set)
    2. O(n²) pairwise Hamming distance on representatives
    3. Union-Find for transitive closure (A~B, B~C → {A,B,C})
    4. Expand representatives back to all files
    5. Filter: groups must have ≥2 distinct pixel_hashes
    """
```

#### S2.3 Grouping call after Pass 3

After Pass 3 completes, scanner calls `build_similarity_groups()`, persists results via DB CRUD, emits `similarity_grouping_complete(count)`.

---

### Phase S3: Recommendation Engine

#### S3.1 New module: `core/similarity_selection.py`

Follows the pattern of existing `core/selection.py`:

```python
class SimilarityPreset(Enum):
    KEEP_HIGHEST_RESOLUTION = auto()   # max(width * height)
    KEEP_LARGEST_FILE = auto()         # max(size)
    KEEP_NEWEST = auto()               # max(modified_at)
    KEEP_OLDEST = auto()               # min(modified_at) — the "original"
    KEEP_SHORTEST_PATH = auto()        # simplest location

def recommend_keeper(files: list[dict]) -> tuple[int, str]:
    """Return (file_id, reason) for the recommended keeper.

    Primary: highest resolution (width * height).
    Tiebreak 1: largest file size.
    Tiebreak 2: newest modification date.
    Tiebreak 3: shortest path (stable).
    """

def apply_similarity_preset(
    db, session_id: int, preset: SimilarityPreset,
    group_ids: list[int] | None = None,
) -> tuple[int, int]:
    """Apply preset to similarity groups → file_actions.
    Master Copy protection: last copy of any pixel_hash NEVER deleted."""
```

---

### Phase S4: Similarity UI Screen

#### S4.1 Dashboard: "Similar Images" card

Add 4th card to `ui/dashboard.py` (amber `#f59e0b`):
```python
similarity_card_clicked = pyqtSignal()
```

In `refresh()`: query `get_similarity_group_count` / `get_similarity_group_file_count`. Show "0" with subtitle "Enable similarity scan to detect" when no groups exist.

#### S4.2 Scan control: opt-in checkbox

Add to `ui/scan_control.py`:
```
[x] Detect exact duplicates
[ ] Also detect similar images (slower)
```

Pass the checkbox state to `Scanner` constructor via the existing scan start wiring.

#### S4.3 `ui/similarity_model.py` (new)

Two-level QAbstractItemModel following `ui/cluster_model.py` pattern:
- Level 0: Similarity group rows (member count, total size, max distance, recommended keeper)
- Level 1: Individual files (resolution, size, date, path, distance from representative, recommendation badge)

#### S4.4 `ui/similarity_compare.py` (new)

Side-by-side thumbnail comparison widget:
```
┌──────────┬──────────┬──────────┐
│ [thumb]  │ [thumb]  │ [thumb]  │
│ ★ KEEP   │          │          │
│4032x3024 │ 800x600  │4032x3024 │
│ 12.1 MB  │ 0.3 MB   │ 8.7 MB   │
│2024-01-15│2024-02-03│2024-01-15│
│ dist: 0  │ dist: 5  │ dist: 7  │
│[Keep][Del]│[Keep][Del]│[Keep][Del]│
└──────────┴──────────┴──────────┘
Recommendation: Keep IMG_1234.jpg (highest resolution)
```

#### S4.5 `ui/similarity_screen.py` (new)

Full-screen widget registered in NavigationController:
- **Top bar:** Back button, title, Smart Select button
- **Left panel:** QTreeView with SimilarityModel (groups + files)
- **Right panel:** SimilarityComparePanel (detail for selected group)
- **Bottom bar:** Stats + "Review Plan >>" button

Signals: `back_requested`, `review_requested`, `status_message(str)`

#### S4.6 Navigation wiring (`ui/main_window.py`)

Register `SimilarityScreen` in NavigationController. Wire:
- Dashboard `similarity_card_clicked` → navigate to similarity screen
- Similarity screen `review_requested` → navigate to Plan Review (shared)

Similarity file_actions flow into the existing Plan Review / Execution screens unchanged.

#### S4.7 Scan progress enhancement

Show Pass 3 progress in ScanControl:
```
Hashing 423 candidates...           [====================] 100%  ✓
Similarity hashing 2,105 files...   [=========           ]  47%
```

---

### Phase S5: Integration & Polish

- **FilterSidebar:** Add similarity threshold slider (visible only on similarity screen)
- **Export:** Include `perceptual_hash` in JSON export payload (backward-compatible)
- **PyInstaller:** Add `imagehash` to hidden imports in `.spec`
- **i18n:** Add ~40–50 new `tr()` strings to `app.ts` (EN) and `app_hu.ts` (HU), recompile with `lrelease`

---

## Files to Modify

### New Files

| File | Phase | Purpose |
|---|---|---|
| `core/similarity.py` | S2 | Pure grouping algorithm (Union-Find, Hamming distance) |
| `core/similarity_selection.py` | S3 | Recommendation engine (presets, keeper selection) |
| `ui/similarity_model.py` | S4 | QAbstractItemModel for similarity group tree |
| `ui/similarity_screen.py` | S4 | Full review screen: tree + compare + actions |
| `ui/similarity_compare.py` | S4 | Side-by-side thumbnail comparison widget |
| `tests/unit/test_similarity.py` | S2 | Grouping algorithm tests |
| `tests/unit/test_similarity_selection.py` | S3 | Recommendation logic tests |

### Modified Files

| File | Phase | Change |
|---|---|---|
| `requirements.txt` | S1 | Add `imagehash` |
| `core/hasher.py` | S1 | Add `compute_perceptual_hash()`, extend `hash_file()` return type + `compute_phash` param |
| `core/scanner.py` | S2 | Add `similarity_enabled`, Pass 3, grouping call, new signals |
| `data/db.py` | S1 | Schema migration, new columns/tables, CRUD methods |
| `ui/dashboard.py` | S4 | 4th "Similar Images" card (amber) |
| `ui/main_window.py` | S4 | Register similarity screen, wire navigation |
| `ui/scan_control.py` | S4 | Similarity opt-in checkbox |
| `ui/filter_sidebar.py` | S5 | Similarity threshold slider |
| `data/export.py` | S5 | Include `perceptual_hash` in export |
| `dejaview.spec` or `dejaview/*.spec` | S5 | PyInstaller hidden imports |
| `resources/i18n/app.ts` | S5 | EN translations |
| `resources/i18n/app_hu.ts` | S5 | HU translations |
| `tests/unit/test_hasher.py` | S1 | pHash computation tests |
| `tests/unit/test_db.py` | S1 | New schema/CRUD tests |

## Task Log

### Phase S1: Perceptual Hash Infrastructure

| # | Task | Status | Details |
|---|------|--------|---------|
| S1.1 | Add `imagehash` to requirements.txt | ✅ | Added to requirements.txt |
| S1.2 | Add `compute_perceptual_hash()` to hasher.py | ✅ | Pure function, takes open PIL Image |
| S1.3 | Extend `hash_file()` return type and add `compute_phash` param | ✅ | Returns `(hash, thumb, phash, w, h)` |
| S1.4 | Update all `hash_file()` callers for new return type | ✅ | scanner.py Pass 2: `*_` splat |
| S1.5 | Add `perceptual_hash`, `width`, `height` columns to `files` | ✅ | Migration in `_migrate()` |
| S1.6 | Add `similarity_groups` + `similarity_group_members` tables | ✅ | DDL + migration + indexes |
| S1.7 | Add `similarity_enabled` column to `sessions` table | ✅ | Default 0, persist across pause/resume |
| S1.8 | Add DB CRUD methods for perceptual hash + similarity groups | ✅ | 12 methods added |
| S1.9 | Write tests for pHash computation in test_hasher.py | ✅ | 9 tests (TestPerceptualHash) |
| S1.10 | Write tests for DB schema + CRUD in test_db.py | ✅ | 23 tests (TestSimilaritySchema + TestSimilarityCRUD) |

### Phase S2: Scanner Extension

| # | Task | Status | Details |
|---|------|--------|---------|
| S2.1 | Add `similarity_enabled` param to Scanner.__init__ | ✅ | Default False, stored in `_similarity_enabled` |
| S2.2 | Implement `_run_pass3()` — dual-hash pass | ✅ | Sliding-window pipeline, dual/phash-only batch updates |
| S2.3 | Implement `_run_pass3b()` — post-hash duplicate refresh | ✅ | SQL GROUP BY + HAVING, emits `duplicate_found` |
| S2.4 | Create `core/similarity.py` | ✅ | `hamming_distance()`, `build_similarity_groups()` with Union-Find |
| S2.5 | Implement `_run_pass3c()` — similarity grouping | ✅ | Calls `build_similarity_groups`, persists to DB, emits signal |
| S2.6 | Add scanner signals: `similarity_progress`, `similarity_grouping_complete` | ✅ | Two new pyqtSignal declarations |
| S2.7 | Add `get_files_needing_hashes()` DB method | ✅ | Done in S1.8 |
| S2.8 | Write tests for `build_similarity_groups()` | ✅ | 18 tests: hamming distance, grouping, transitive closure, threshold, exclusion |
| S2.9 | Write tests for Pass 3 dual-hash behavior | ✅ | 8 integration tests: dual-hash, size-filter bypass, 3b duplicate refresh, 3c grouping |
| S2.10 | Write tests for Pass 3 resume safety | ✅ | Resume skips already-hashed files (0 candidates on re-scan) |

### Phase S3: Recommendation Engine

| # | Task | Status | Details |
|---|------|--------|---------|
| S3.1 | Create `core/similarity_selection.py` | ✅ | `SimilarityPreset`, `recommend_keeper()`, `apply_similarity_preset()` |
| S3.2 | Write tests for recommendation logic | ✅ | 18 tests: keeper selection, presets, MC protection, unique pixel_hash deletion |

### Phase S4: Similarity UI Screen

| # | Task | Status | Details |
|---|------|--------|---------|
| S4.1 | Create `ui/similarity_model.py` | ✅ | Two-level QAbstractItemModel with custom roles |
| S4.2 | Create `ui/similarity_compare.py` | ✅ | Side-by-side _FileCard thumbnails + metadata |
| S4.3 | Create `ui/similarity_screen.py` | ✅ | Full screen: tree + compare + stats + Smart Select |
| S4.4 | Add "Similar Images" card to Dashboard | ✅ | Amber #f59e0b card, group/file counts |
| S4.5 | Add similarity checkbox to ScanControl | ✅ | "Similar" checkbox with tooltip |
| S4.6 | Register similarity screen + wire navigation | ✅ | main_window.py: register, nav signals, session_id |
| S4.7 | Wire similarity review → Plan Review | ✅ | review_requested → shared Plan Review flow |
| S4.8 | Show Pass 3 progress in ScanControl | ✅ | similarity_progress → on_progress_updated |
| S4.9 | Add Smart Select for similarity groups | ✅ | QInputDialog preset chooser with 5 presets |

### Phase S5: Integration & Polish

| # | Task | Status | Details |
|---|------|--------|---------|
| S5.1 | Add similarity threshold slider to FilterSidebar | ✅ | QSlider 0–16, hidden by default, `set_similarity_visible()` |
| S5.2 | Include `perceptual_hash` in export JSON | ✅ | Backward-compatible field in `build_export_payload()` |
| S5.3 | Add `imagehash` to PyInstaller spec | ✅ | Hidden import + removed numpy/scipy from excludes |
| S5.4 | Add all i18n strings (EN + HU) | ✅ | 3 new contexts + additions to 3 existing contexts |
| S5.5 | Recompile .qm files with lrelease | ✅ | 324 HU translations compiled |
| S5.6 | End-to-end smoke test | ✅ | 453 passed, 10 skipped |

## Verification

### Unit tests
```bash
cd dejaview
python -m pytest tests/unit/ --no-cov -q
```

### New test modules
```bash
python -m pytest tests/unit/test_similarity.py --no-cov -v
python -m pytest tests/unit/test_similarity_selection.py --no-cov -v
```

### End-to-end smoke test
1. **Without similarity:** Scan with checkbox unchecked → no Pass 3, no similarity card
2. **With similarity:** Enable checkbox, scan → Pass 3 runs, Dashboard shows "Similar Images" card
3. **Similarity screen:** Click card → groups displayed, expandable, thumbnails load
4. **Comparison:** Expand group → side-by-side view, resolutions, recommendation badge
5. **Smart Select:** Apply "Keep Highest Resolution" → correct files marked
6. **Plan Review:** Similarity delete-actions appear alongside exact-duplicate actions
7. **Execution:** Apply → files moved to soft-delete trash
8. **Resume:** Pause/resume similarity scan → already-hashed files skipped

### Key invariants
- Exact duplicates (same pixel_hash) NEVER appear in similarity groups
- Similarity groups always have ≥2 members with distinct pixel_hashes
- Master Copy protection: last copy of a pixel_hash never marked for deletion
- `similarity_enabled=False` → no Pass 3, no perceptual hashes computed
- Existing exact-duplicate flow completely unaffected
