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
from typing import Optional


class SimilarityPreset(Enum):
    """Selection strategies for choosing which copy to keep in similarity groups."""

    KEEP_HIGHEST_RESOLUTION = auto()  # max(width * height)
    KEEP_LARGEST_FILE = auto()        # max(size)
    KEEP_NEWEST = auto()              # max(modified_at)
    KEEP_OLDEST = auto()              # min(modified_at) — the "original"
    KEEP_SHORTEST_PATH = auto()       # simplest location


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
        # Negate path length for tiebreak (shorter = better, so negate)
        path_len = len(f.get("path") or "")
        return (resolution, size, modified, -path_len)

    best = max(files, key=_sort_key)
    best_key = _sort_key(best)

    # Determine reason.
    w = best.get("width") or 0
    h = best.get("height") or 0
    resolution = w * h

    # Check if resolution alone distinguishes the winner.
    other_resolutions = [
        (f.get("width") or 0) * (f.get("height") or 0)
        for f in files if f["id"] != best["id"]
    ]
    if resolution > 0 and all(resolution > r for r in other_resolutions):
        reason = "highest resolution"
    elif (best.get("size") or 0) > max(
        (f.get("size") or 0) for f in files if f["id"] != best["id"]
    ):
        reason = "largest file"
    else:
        reason = "best overall"

    return best["id"], reason


def apply_similarity_preset(
    db,
    session_id: int,
    preset: SimilarityPreset,
    group_ids: Optional[list[int]] = None,
) -> tuple[int, int]:
    """Apply a preset to similarity groups, creating file_actions.

    For each group, the "best" file per the preset is marked 'keep' and all
    others are marked 'delete'.

    Master Copy protection: the last remaining copy of any pixel_hash is
    NEVER marked for deletion (even if the preset says to delete it).

    Args:
        db: Database instance.
        session_id: Active session.
        preset: Which selection strategy to use.
        group_ids: Optional subset of group IDs to process. If None,
            processes all similarity groups in the session.

    Returns:
        (keep_count, delete_count) — number of files marked.
    """
    if group_ids is not None:
        groups = [{"id": gid} for gid in group_ids]
    else:
        groups = db.get_similarity_groups(session_id)

    now = datetime.now(timezone.utc).isoformat()
    keep_count = 0
    delete_count = 0
    batch: list[tuple[int, int, str, str, str]] = []

    # Build pixel_hash → count of active files across the session for
    # Master Copy protection.
    all_files = db.get_files_for_session(session_id)
    pixel_hash_counts: dict[str, int] = {}
    for f in all_files:
        ph = f["pixel_hash"]
        if ph:
            pixel_hash_counts[ph] = pixel_hash_counts.get(ph, 0) + 1

    # Track which pixel_hashes have been marked for deletion in this batch,
    # so we don't delete the last copy.
    pixel_hash_deletes: dict[str, int] = {}

    for g in groups:
        group_id = g["id"]
        members = db.get_similarity_group_members(group_id)
        file_dicts = [dict(m) for m in members]

        if len(file_dicts) < 2:
            continue

        keeper_id = _pick_similarity_keeper(file_dicts, preset)

        for f in file_dicts:
            fid = f["id"]
            ph = f.get("pixel_hash")

            if fid == keeper_id:
                batch.append((session_id, fid, "keep", "file", now))
                keep_count += 1
            else:
                # Master Copy protection: if this pixel_hash has multiple exact
                # copies (count > 1), don't delete ALL of them.  If it's the
                # only file with this pixel_hash, deletion is fine — the user
                # is keeping a similar (different pixel_hash) image instead.
                total = pixel_hash_counts.get(ph, 1)
                already_deleted = pixel_hash_deletes.get(ph, 0)
                if total > 1 and total - already_deleted <= 1:
                    # This is the last copy of an exact-dupe set — force keep.
                    batch.append((session_id, fid, "keep", "file", now))
                    keep_count += 1
                else:
                    batch.append((session_id, fid, "delete", "file", now))
                    delete_count += 1
                    if ph:
                        pixel_hash_deletes[ph] = already_deleted + 1

    if batch:
        db.set_file_actions_batch(batch)

    return keep_count, delete_count


def _pick_similarity_keeper(files: list[dict], preset: SimilarityPreset) -> int:
    """Pick the file_id to keep based on the similarity preset.

    Args:
        files: List of file dicts (must have len >= 2).
        preset: Selection strategy.

    Returns:
        file_id of the file to keep.
    """
    if preset == SimilarityPreset.KEEP_HIGHEST_RESOLUTION:
        key = lambda f: (
            (f.get("width") or 0) * (f.get("height") or 0),
            f.get("size") or 0,
            f.get("modified_at") or "",
        )
        best = max(files, key=key)
    elif preset == SimilarityPreset.KEEP_LARGEST_FILE:
        key = lambda f: (f.get("size") or 0, f.get("modified_at") or "")
        best = max(files, key=key)
    elif preset == SimilarityPreset.KEEP_NEWEST:
        key = lambda f: (f.get("modified_at") or "", f.get("size") or 0)
        best = max(files, key=key)
    elif preset == SimilarityPreset.KEEP_OLDEST:
        key = lambda f: (f.get("modified_at") or "", f.get("size") or 0)
        best = min(files, key=key)
    elif preset == SimilarityPreset.KEEP_SHORTEST_PATH:
        key = lambda f: (
            -(f.get("path", "").count("/") + f.get("path", "").count("\\")),
            f.get("size") or 0,
        )
        best = max(files, key=key)
    else:
        # Fallback: highest resolution
        key = lambda f: (f.get("width") or 0) * (f.get("height") or 0)
        best = max(files, key=key)

    return best["id"]
