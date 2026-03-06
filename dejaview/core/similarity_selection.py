"""
core/similarity_selection.py — Recommendation engine for similarity groups.

Module ownership rules (follows core/selection.py):
- Pure logic: no UI, no Qt dependency.
- Reads from DB via passed-in Database instance; writes file_actions in bulk.
- Master Copy protection: last copy of any pixel_hash NEVER marked for deletion.

Plan reference: §S3.1 — Recommendation Engine.
"""

from datetime import datetime, timezone
from enum import Enum, auto
from typing import Callable, Optional, Union

from core.sort_chain import PRESET_CHAINS, SortCriterion, pick_keeper


class SimilarityPreset(Enum):
    """Selection strategies for choosing which copy to keep in similarity groups."""

    KEEP_HIGHEST_RESOLUTION = auto()  # max(width * height)
    KEEP_LARGEST_FILE = auto()        # max(size)
    KEEP_NEWEST = auto()              # max(modified_at)
    KEEP_OLDEST = auto()              # min(modified_at) — the "original"
    KEEP_SHORTEST_PATH = auto()       # simplest location


def _determine_reason(best: dict, others: list[dict]) -> str:
    """Return a human-readable reason why *best* was chosen over *others*."""
    resolution = (best.get("width") or 0) * (best.get("height") or 0)
    other_resolutions = [
        (f.get("width") or 0) * (f.get("height") or 0) for f in others
    ]
    if resolution > 0 and all(resolution > r for r in other_resolutions):
        return "highest resolution"
    other_sizes = [(f.get("size") or 0) for f in others]
    if (best.get("size") or 0) > max(other_sizes):
        return "largest file"
    return "best overall"


def recommend_keeper(files: list[dict]) -> tuple[int, str]:
    """Return (file_id, reason) for the recommended keeper in a similarity group.

    Selection criteria (priority order):
      1. Highest resolution (width * height)
      2. Largest file size (tiebreak 1)
      3. Newest modification date (tiebreak 2)
      4. Shortest path (tiebreak 3, stable)

    Args:
        files: List of dicts with keys: id, width, height, size, modified_at, path.

    Returns:
        (file_id, reason_string) — the recommended file and why.

    Raises:
        ValueError: if files is empty.
    """
    if not files:
        raise ValueError("Cannot recommend keeper from empty file list")

    def _sort_key(f: dict) -> tuple:
        w = f.get("width") or 0
        h = f.get("height") or 0
        resolution = w * h
        size = f.get("size") or 0
        modified = f.get("modified_at") or ""
        path_len = len(f.get("path") or "")
        return (resolution, size, modified, -path_len)

    best = max(files, key=_sort_key)
    others = [f for f in files if f["id"] != best["id"]]
    return best["id"], _determine_reason(best, others)


def _resolve_similarity_criteria(
    preset_or_chain: Union[SimilarityPreset, list[SortCriterion]],
) -> list[SortCriterion]:
    """Convert a SimilarityPreset or raw chain to a list[SortCriterion]."""
    if isinstance(preset_or_chain, list):
        return preset_or_chain
    return PRESET_CHAINS[preset_or_chain.name]


def _build_pixel_hash_counts(all_files) -> dict[str, int]:
    """Build pixel_hash → count map for Master Copy protection."""
    counts: dict[str, int] = {}
    for f in all_files:
        ph = f["pixel_hash"]
        if ph:
            counts[ph] = counts.get(ph, 0) + 1
    return counts


def _apply_to_similarity_group(
    file_dicts: list[dict],
    criteria: list[SortCriterion],
    session_id: int,
    now: str,
    batch: list[tuple[int, int, str, str, str]],
    pixel_hash_counts: dict[str, int],
    pixel_hash_deletes: dict[str, int],
) -> tuple[int, int]:
    """Pick keeper for one similarity group, append actions. Returns (keep, delete)."""
    if len(file_dicts) < 2:
        return 0, 0

    keeper_id = pick_keeper(file_dicts, criteria)
    keep = 0
    delete = 0

    for f in file_dicts:
        fid = f["id"]
        ph = f.get("pixel_hash")

        if fid == keeper_id:
            batch.append((session_id, fid, "keep", "file", now))
            keep += 1
            continue

        # Master Copy protection
        total = pixel_hash_counts.get(ph, 1)
        already_deleted = pixel_hash_deletes.get(ph, 0)
        if total > 1 and total - already_deleted <= 1:
            batch.append((session_id, fid, "keep", "file", now))
            keep += 1
        else:
            batch.append((session_id, fid, "delete", "file", now))
            delete += 1
            if ph:
                pixel_hash_deletes[ph] = already_deleted + 1

    return keep, delete


def apply_similarity_preset(
    db,
    session_id: int,
    preset: Union[SimilarityPreset, list[SortCriterion]],
    group_ids: Optional[list[int]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[int, int]:
    """Apply a preset to similarity groups, creating file_actions.

    For each group, the "best" file per the preset is marked 'keep' and all
    others are marked 'delete'.

    Master Copy protection: the last remaining copy of any pixel_hash is
    NEVER marked for deletion (even if the preset says to delete it).

    Args:
        db: Database instance.
        session_id: Active session.
        preset: Which selection strategy to use — either a SimilarityPreset
            enum or a custom list[SortCriterion] chain.
        group_ids: Optional subset of group IDs to process. If None,
            processes all similarity groups in the session.
        progress_callback: Optional callback(current, total) for progress.

    Returns:
        (keep_count, delete_count) — number of files marked.
    """
    criteria = _resolve_similarity_criteria(preset)

    if group_ids is not None:
        groups = [{"id": gid} for gid in group_ids]
    else:
        groups = db.get_similarity_groups(session_id)

    all_files = db.get_files_for_session(session_id)
    pixel_hash_counts = _build_pixel_hash_counts(all_files)
    pixel_hash_deletes: dict[str, int] = {}

    total = len(groups)
    now = datetime.now(timezone.utc).isoformat()
    keep_count = 0
    delete_count = 0
    batch: list[tuple[int, int, str, str, str]] = []

    for i, g in enumerate(groups):
        members = db.get_similarity_group_members(g["id"])
        file_dicts = [dict(m) for m in members]
        k, d = _apply_to_similarity_group(
            file_dicts, criteria, session_id, now, batch,
            pixel_hash_counts, pixel_hash_deletes,
        )
        keep_count += k
        delete_count += d
        if progress_callback:
            progress_callback(i + 1, total)

    if batch:
        db.set_file_actions_batch(batch)

    return keep_count, delete_count
