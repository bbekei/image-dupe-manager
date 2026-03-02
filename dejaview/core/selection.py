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
from typing import Optional


class SelectionPreset(Enum):
    """Selection strategies for choosing which copy to keep."""

    KEEP_LARGEST_FILE = auto()  # best quality proxy (largest file size)
    KEEP_NEWEST = auto()  # most recent modified_at
    KEEP_DEEPEST_PATH = auto()  # most organized folder (deepest path)
    KEEP_SHORTEST_PATH = auto()  # simplest location (shortest path)


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


def apply_preset(
    db,
    session_id: int,
    preset: SelectionPreset,
    pixel_hashes: Optional[list[str]] = None,
) -> tuple[int, int]:
    """Apply a selection preset to duplicate groups, creating file_actions.

    For each group, the "best" file per the preset is marked 'keep' and all
    others are marked 'delete'.  Groups with only 1 file are skipped.
    Master Copy protection: the last copy is NEVER marked for deletion.

    Args:
        db: Database instance.
        session_id: Active session.
        preset: Which selection strategy to use.
        pixel_hashes: Optional subset of hashes to process.  If None,
            processes all duplicate groups in the session.

    Returns:
        (keep_count, delete_count) — number of files marked.
    """
    if pixel_hashes is not None:
        groups = [
            {"pixel_hash": h}
            for h in pixel_hashes
        ]
    else:
        groups = db.get_duplicate_groups(session_id)

    now = datetime.now(timezone.utc).isoformat()
    keep_count = 0
    delete_count = 0
    batch: list[tuple[int, int, str, str, str]] = []

    for g in groups:
        pixel_hash = g["pixel_hash"]
        files = db.get_cluster_files(session_id, pixel_hash)
        file_dicts = [dict(f) for f in files]

        if len(file_dicts) < 2:
            continue

        keeper_id = _pick_keeper(file_dicts, preset)

        for f in file_dicts:
            fid = f["id"]
            if fid == keeper_id:
                batch.append((session_id, fid, "keep", "file", now))
                keep_count += 1
            else:
                batch.append((session_id, fid, "delete", "file", now))
                delete_count += 1

    if batch:
        db.set_file_actions_batch(batch)

    return keep_count, delete_count


def _pick_keeper(files: list[dict], preset: SelectionPreset) -> int:
    """Pick the file_id to keep based on the preset.

    Args:
        files: List of file dicts (must have len >= 2).
        preset: Selection strategy.

    Returns:
        file_id of the file to keep.
    """
    if preset == SelectionPreset.KEEP_LARGEST_FILE:
        key = lambda f: (f.get("size") or 0, f.get("modified_at") or "")
        best = max(files, key=key)
    elif preset == SelectionPreset.KEEP_NEWEST:
        key = lambda f: (f.get("modified_at") or "", f.get("size") or 0)
        best = max(files, key=key)
    elif preset == SelectionPreset.KEEP_DEEPEST_PATH:
        key = lambda f: (f.get("path", "").count("/") + f.get("path", "").count("\\"), f.get("size") or 0)
        best = max(files, key=key)
    elif preset == SelectionPreset.KEEP_SHORTEST_PATH:
        # Shortest path = fewest separators; tiebreak by largest size
        key = lambda f: (
            -(f.get("path", "").count("/") + f.get("path", "").count("\\")),
            f.get("size") or 0,
        )
        best = max(files, key=key)
    else:
        # Fallback to largest file
        best = max(files, key=lambda f: f.get("size") or 0)

    return best["id"]
