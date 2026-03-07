# DejaView — Feature Request Plan: Composable Sort Chain for Selection Presets

## Overview

Replace single-criterion selection presets with a composable criteria chain that lets users define multi-level "keep the best file" rules. Quick-preset buttons remain as one-click shortcuts; an advanced panel lets users build custom chains. Includes progress feedback for large libraries and scoped plan clearing so duplicate and similarity decisions don't overwrite each other.

## Problem

- Quick presets use hardcoded tiebreakers the user can't see or customize.
- When 40k+ images have many ties (same size, same resolution), invisible tiebreakers silently decide which files survive.
- No visual indication of which preset is currently active.
- No progress feedback — large libraries freeze the UI for seconds.
- `clear_all_actions()` wipes both duplicate and similarity decisions, but users build their plan incrementally across both views.

## User Experience

### Quick Presets (unchanged)

```
[ Keep Largest ] [ Keep Newest ] [ Keep Oldest ] [ Keep Shortest Path ] [ Keep Hi-Res ]
                                                              [ Advanced v ]
```

Active button gets a highlight ring. Clicking a different one replaces the previous.

### Advanced Panel (new, collapsed by default)

```
[ Advanced ^ ]
  +---------------------------------------------------------+
  | 1. Keep Highest Resolution  [v]  [^] [v] [x]           |
  | 2. Keep Oldest              [v]  [^] [v] [x]           |
  | 3. Keep Shortest Path       [v]  [^] [v] [x]           |
  |                                                         |
  |              [+ Add criterion]                          |
  |                                                         |
  | [ Apply Custom Chain ]           Applying... [====>  ]  |
  +---------------------------------------------------------+
```

### Behavior

- Applying any preset/chain **clears only the current view's actions** (duplicate OR similarity), then applies.
- Active-preset indicator clears if the user manually changes a single file's action.
- Progress bar appears for sessions with many groups; buttons disabled while running.

## Solution

### 1. Shared chain evaluator: `core/sort_chain.py` (new)

Pure logic module, no DB dependency.

```python
@dataclass(frozen=True)
class SortCriterion:
    field: str       # "size", "resolution", "modified_at", "path_depth", "filename_length"
    ascending: bool  # True = keep smallest/oldest, False = keep largest/newest

def build_sort_key(criteria: list[SortCriterion], file: dict) -> tuple
def pick_keeper(files: list[dict], criteria: list[SortCriterion]) -> int
```

Field extractors:
- `size` -> `f.get("size") or 0`
- `resolution` -> `(f.get("width") or 0) * (f.get("height") or 0)`
- `modified_at` -> `f.get("modified_at") or ""`
- `path_depth` -> count of `/` and `\` in path
- `filename_length` -> `len(os.path.basename(path))`

Each criterion's value is negated when descending so a single `min()` call resolves the entire chain.

Quick-preset -> chain mapping (constants in same module):

| Preset | Chain |
|--------|-------|
| Keep Largest File | `[size desc, modified_at desc, path_depth asc]` |
| Keep Highest Resolution | `[resolution desc, size desc, modified_at desc]` |
| Keep Newest | `[modified_at desc, size desc, path_depth asc]` |
| Keep Oldest | `[modified_at asc, size desc, path_depth asc]` |
| Keep Shortest Path | `[path_depth asc, size desc, modified_at desc]` |

### 2. Scoped plan clearing: `data/db.py`

Two new methods that surgically clear only the relevant view's actions:

- `clear_duplicate_actions(session_id)` — deletes file_actions for files whose pixel_hash has 2+ entries in the session (i.e., duplicate group members only).
- `clear_similarity_actions(session_id)` — deletes file_actions for files that are members of similarity_group_members.

Overlap case (file in both): last view to set wins, which is correct since the user is consciously working in that view.

### 3. Bulk fetch: `data/db.py`

- `get_all_duplicate_files_bulk(session_id)` — single query returning all files in multi-file duplicate groups. Caller groups by `pixel_hash`. Eliminates the N+1 per-group query pattern (15k groups -> 1 query instead of 15k).

### 4. Refactor `core/selection.py`

- `apply_preset()` accepts either a `SelectionPreset` or a `list[SortCriterion]`
- Uses bulk fetch instead of per-group queries
- Accepts optional `progress_callback(current, total)` for large sessions
- Delegates to `sort_chain.pick_keeper()` for each group
- Existing `_PRESET_KEYS` dict replaced by `PRESET_CHAINS` mapping from sort_chain

### 5. Refactor `core/similarity_selection.py`

- Same changes: share `sort_chain` evaluator, accept progress callback
- Uses `clear_similarity_actions()` before applying

### 6. Async API endpoints: `backend/api.py`

- `apply_selection_preset()` — quick presets, calls `clear_duplicate_actions` first
- `apply_custom_selection(session_id, criteria)` — custom chains
- Both run in worker thread for large sessions
- Emit `selection:progress` events: `{current, total}`
- Emit `selection:complete` on finish: `{keep_count, delete_count, active_preset}`
- Mirror for similarity: `apply_custom_similarity_selection()`

### 7. Frontend types: `src/types/api.ts`

```typescript
export interface SortCriterion {
  field: 'size' | 'resolution' | 'modified_at' | 'path_depth' | 'filename_length'
  ascending: boolean
}
```

### 8. Frontend component: `src/components/CriteriaBuilder.tsx` (new)

- Ordered list of criteria with dropdown selectors
- Up/down reorder buttons + remove per criterion
- "Add criterion" (filters out already-used fields)
- "Apply" button triggers async API call
- Collapsible panel, hidden by default

### 9. Screen updates: `BrowseResults.tsx` + `SimilarityReview.tsx`

- `activePreset` state: `SelectionPreset | 'custom' | null`
- Highlighted button styling for active preset
- "Advanced" toggle to show/hide CriteriaBuilder
- Progress bar during async application (listens to `selection:progress`)
- Buttons disabled while running
- Clear active indicator on manual single-file action change

### 10. i18n: `en.json` + `hu.json`

- Criteria labels: "File Size (Largest)", "File Size (Smallest)", "Resolution", "Date (Newest)", "Date (Oldest)", "Path (Shortest)", "Path (Longest)", "Filename (Longest)", "Filename (Shortest)"
- UI labels: "Advanced Selection", "Add Criterion", "Apply Custom Chain", "Custom", "Applying selection..."

## Files to Modify

| File | Change |
|------|--------|
| `core/sort_chain.py` | **New** — SortCriterion, build_sort_key, pick_keeper, PRESET_CHAINS |
| `core/selection.py` | Refactor apply_preset to use sort_chain, add progress callback, remove _PRESET_KEYS |
| `core/similarity_selection.py` | Same refactor, share sort_chain evaluator |
| `data/db.py` | Add clear_duplicate_actions, clear_similarity_actions, get_all_duplicate_files_bulk |
| `backend/api.py` | Add apply_custom_selection, async worker + progress events, scoped clearing |
| `frontend/src/types/api.ts` | Add SortCriterion interface |
| `frontend/src/components/CriteriaBuilder.tsx` | **New** — criteria builder component |
| `frontend/src/screens/BrowseResults.tsx` | Active preset state, Advanced toggle, progress bar |
| `frontend/src/screens/SimilarityReview.tsx` | Same as BrowseResults |
| `frontend/src/i18n/en.json` | Criteria + UI labels |
| `frontend/src/i18n/hu.json` | Criteria + UI labels |
| `tests/unit/test_sort_chain.py` | **New** — chain evaluator tests |
| `tests/unit/test_selection.py` | Chain-mode tests, scoped clearing |
| `tests/unit/test_similarity_selection.py` | Chain-mode tests |
| `tests/unit/test_api_bridge.py` | New endpoint contracts |
| `tests/unit/test_db.py` | Bulk fetch, scoped clear methods |

## Task Log

### Stage 1: Core Logic

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Create `core/sort_chain.py` with SortCriterion, field extractors, pick_keeper | ✅ | Also added KEEP_DEEPEST_PATH |
| 1.2 | Define PRESET_CHAINS mapping (quick presets -> criterion lists) | ✅ | 6 presets defined |
| 1.3 | Write `tests/unit/test_sort_chain.py` | ✅ | 25 tests |

### Stage 2: Database Layer

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Add `clear_duplicate_actions(session_id)` to db.py | ✅ | |
| 2.2 | Add `clear_similarity_actions(session_id)` to db.py | ✅ | |
| 2.3 | Add `get_all_duplicate_files_bulk(session_id)` to db.py | ✅ | |
| 2.4 | Write DB layer tests | ✅ | 8 tests in TestScopedClearing |

### Stage 3: Selection Logic Refactor

| # | Task | Status | Details |
|---|------|--------|---------|
| 3.1 | Refactor `core/selection.py` to use sort_chain + bulk fetch + progress callback | ✅ | Removed _PRESET_KEYS, _pick_keeper |
| 3.2 | Refactor `core/similarity_selection.py` to use sort_chain + progress callback | ✅ | Removed _pick_similarity_keeper |
| 3.3 | Update existing tests, add chain-mode tests | ✅ | Updated imports, 60 tests pass |

### Stage 4: API Layer

| # | Task | Status | Details |
|---|------|--------|---------|
| 4.1 | Add `apply_custom_selection` endpoint with async worker + progress events | ✅ | |
| 4.2 | Add `apply_custom_similarity_selection` endpoint | ✅ | |
| 4.3 | Update existing preset endpoints to use scoped clearing | ✅ | |
| 4.4 | API contract tests | ✅ | 10 new tests, 78 total |

### Stage 5: Frontend

| # | Task | Status | Details |
|---|------|--------|---------|
| 5.1 | Add SortCriterion type to api.ts | ✅ | SortField, SortCriterion, SelectionResult, events |
| 5.2 | Create CriteriaBuilder.tsx component | ✅ | |
| 5.3 | Update BrowseResults.tsx — active state, advanced toggle, progress | ✅ | |
| 5.4 | Update SimilarityReview.tsx — same | ✅ | |
| 5.5 | Add i18n labels (EN + HU) | ✅ | selection.* keys in both |
| 5.6 | TypeScript type-check pass | ✅ | `npx tsc --noEmit` clean |

## Verification

```bash
# Unit tests (all stages)
cd dejaview && python -m pytest tests/unit/ -m "not e2e" --no-cov -q

# API contract + headless integration
cd dejaview && python -m pytest tests/unit/test_api_bridge.py tests/e2e/test_e2e_headless_api.py -m "not e2e or headless_e2e" --no-cov -q

# TypeScript type-check
cd dejaview/frontend && npx tsc --noEmit

# Manual: open app, scan a folder with many duplicates, verify:
# - Quick preset buttons highlight when active
# - Advanced panel opens/closes, criteria can be reordered
# - Applying a chain shows progress bar for large sessions
# - Switching views preserves the other view's plan
# - Manually changing a file action clears the active indicator
```
