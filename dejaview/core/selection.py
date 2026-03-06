"""
core/selection.py — Smart selection presets and Master Copy logic for DejaView.

Module ownership rules:
- Pure logic: no UI, no Qt dependency.
- Reads from DB via passed-in Database instance; writes file_actions in bulk.
- Master Copy protection: NEVER marks the last remaining copy for deletion.

UX Redesign Phase 5 — Advanced Cleanup.
"""

from datetime import datetime, timezone
from enum import Enum, auto
from typing import Callable, Optional, Union

from core.sort_chain import PRESET_CHAINS, SortCriterion, pick_keeper


class SelectionPreset(Enum):
    """Selection strategies for choosing which copy to keep."""

    KEEP_LARGEST_FILE = auto()  # best quality proxy (largest file size)
    KEEP_NEWEST = auto()  # most recent modified_at
    KEEP_OLDEST = auto()  # earliest modified_at — the "original"
    KEEP_DEEPEST_PATH = auto()  # most organized folder (deepest path)
    KEEP_SHORTEST_PATH = auto()  # simplest location (shortest path)
    KEEP_HIGHEST_RESOLUTION = auto()  # max(width * height)


def identify_master_copy(files: list[dict]) -> Optional[int]:
    """Return file_id of the best copy in a duplicate group.

    Selection criteria: largest file size, with newest modified_at as tiebreak.
    For equal-quality files, the first by sorted path is chosen (stable).

    Args:
        files: List of dicts with keys: id, size, modified_at, path.

    Returns:
        file_id of the master copy, or None if files is empty.
    """
    if not files:
        return None

    def _sort_key(f: dict) -> tuple:
        return (
            f.get("size") or 0,
            f.get("modified_at") or "",
            # Negate path for reverse alphabetical (shorter paths first)
            # so ties are broken stably
        )

    best = max(files, key=_sort_key)
    # If there are ties on size+date, pick by shortest path for stability
    tied = [f for f in files if _sort_key(f) == _sort_key(best)]
    if len(tied) > 1:
        tied.sort(key=lambda f: f.get("path", ""))
        best = tied[0]
    return best["id"]


def get_master_copies(db, session_id: int) -> dict[str, int]:
    """Return {pixel_hash: master_file_id} for all duplicate groups.

    Args:
        db: Database instance.
        session_id: Active session.

    Returns:
        Dict mapping each duplicate pixel_hash to its master file_id.
    """
    groups = db.get_duplicate_groups(session_id)
    masters: dict[str, int] = {}
    for g in groups:
        pixel_hash = g["pixel_hash"]
        files = db.get_cluster_files(session_id, pixel_hash)
        file_dicts = [dict(f) for f in files]
        master_id = identify_master_copy(file_dicts)
        if master_id is not None:
            masters[pixel_hash] = master_id
    return masters


def _resolve_criteria(
    preset_or_chain: Union[SelectionPreset, list[SortCriterion]],
) -> list[SortCriterion]:
    """Convert a SelectionPreset or raw chain to a list[SortCriterion]."""
    if isinstance(preset_or_chain, list):
        return preset_or_chain
    return PRESET_CHAINS[preset_or_chain.name]


def _fetch_groups(
    db, session_id: int, pixel_hashes: Optional[list[str]],
) -> tuple[list[str], Optional[dict[str, list[dict]]]]:
    """Return (hash_list, bulk_data_or_None) for apply_preset."""
    if pixel_hashes is not None:
        return pixel_hashes, None
    bulk_data = db.get_all_duplicate_files_bulk(session_id)
    return list(bulk_data.keys()), bulk_data


def _get_group_files(
    db, session_id: int, pixel_hash: str,
    bulk_data: Optional[dict[str, list[dict]]],
) -> list[dict]:
    """Return file dicts for a single group, from bulk cache or per-group query."""
    if bulk_data is not None:
        return bulk_data[pixel_hash]
    return [dict(f) for f in db.get_cluster_files(session_id, pixel_hash)]


def _apply_to_group(
    file_dicts: list[dict],
    criteria: list[SortCriterion],
    session_id: int,
    now: str,
    batch: list[tuple[int, int, str, str, str]],
) -> tuple[int, int]:
    """Pick keeper for one group and append actions to batch. Returns (keep, delete) counts."""
    if len(file_dicts) < 2:
        return 0, 0
    keeper_id = pick_keeper(file_dicts, criteria)
    keep = 0
    delete = 0
    for f in file_dicts:
        fid = f["id"]
        action = "keep" if fid == keeper_id else "delete"
        batch.append((session_id, fid, action, "file", now))
        if fid == keeper_id:
            keep += 1
        else:
            delete += 1
    return keep, delete


def apply_preset(
    db,
    session_id: int,
    preset: Union[SelectionPreset, list[SortCriterion]],
    pixel_hashes: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[int, int]:
    """Apply a selection preset to duplicate groups, creating file_actions.

    For each group, the "best" file per the preset is marked 'keep' and all
    others are marked 'delete'.  Groups with only 1 file are skipped.
    Master Copy protection: the last copy is NEVER marked for deletion.

    Args:
        db: Database instance.
        session_id: Active session.
        preset: Which selection strategy to use — either a SelectionPreset
            enum or a custom list[SortCriterion] chain.
        pixel_hashes: Optional subset of hashes to process.  If None,
            processes all duplicate groups in the session.
        progress_callback: Optional callback(current, total) for progress.

    Returns:
        (keep_count, delete_count) — number of files marked.
    """
    criteria = _resolve_criteria(preset)
    hash_list, bulk_data = _fetch_groups(db, session_id, pixel_hashes)

    total = len(hash_list)
    now = datetime.now(timezone.utc).isoformat()
    keep_count = 0
    delete_count = 0
    batch: list[tuple[int, int, str, str, str]] = []

    for i, pixel_hash in enumerate(hash_list):
        file_dicts = _get_group_files(db, session_id, pixel_hash, bulk_data)
        k, d = _apply_to_group(file_dicts, criteria, session_id, now, batch)
        keep_count += k
        delete_count += d
        if progress_callback:
            progress_callback(i + 1, total)

    if batch:
        db.set_file_actions_batch(batch)

    return keep_count, delete_count
