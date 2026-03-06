"""
core/sort_chain.py — Composable sort-chain evaluator for selection presets.

Pure logic module, no DB dependency.

Each SortCriterion specifies a field and direction. A chain of criteria is
evaluated left-to-right: the first criterion is the primary sort key, the
second breaks ties, etc. pick_keeper() returns the index of the winning file.

Quick-preset buttons map to predefined chains via PRESET_CHAINS.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SortCriterion:
    """A single sort criterion in a composable chain.

    Attributes:
        field: One of "size", "resolution", "modified_at", "path_depth",
               "filename_length".
        ascending: True = keep smallest/oldest, False = keep largest/newest.
    """

    field: str
    ascending: bool

    def __post_init__(self):
        if self.field not in FIELD_EXTRACTORS:
            raise ValueError(
                f"Unknown field {self.field!r}. "
                f"Valid fields: {sorted(FIELD_EXTRACTORS)}"
            )


def _extract_size(f: dict) -> int | float:
    return f.get("size") or 0


def _extract_resolution(f: dict) -> int | float:
    return (f.get("width") or 0) * (f.get("height") or 0)


def _extract_modified_at(f: dict) -> str:
    return f.get("modified_at") or ""


def _extract_path_depth(f: dict) -> int | float:
    path = f.get("path") or ""
    return path.count("/") + path.count("\\")


def _extract_filename_length(f: dict) -> int | float:
    path = f.get("path") or ""
    return len(os.path.basename(path))


FIELD_EXTRACTORS: dict[str, callable] = {
    "size": _extract_size,
    "resolution": _extract_resolution,
    "modified_at": _extract_modified_at,
    "path_depth": _extract_path_depth,
    "filename_length": _extract_filename_length,
}

VALID_FIELDS = sorted(FIELD_EXTRACTORS)


def build_sort_key(criteria: list[SortCriterion], f: dict) -> tuple:
    """Build a comparable sort-key tuple for a file dict.

    For ascending criteria the raw value is used; for descending criteria
    the value is negated (numeric) or inverted (string) so that a single
    min() call over all files yields the winner.

    Returns:
        Tuple of comparable values, one per criterion.
    """
    key_parts: list = []
    for c in criteria:
        extractor = FIELD_EXTRACTORS[c.field]
        value = extractor(f)
        if c.ascending:
            # Keep smallest → raw value, min() picks it
            key_parts.append(value)
        else:
            # Keep largest → negate so min() picks the largest
            if isinstance(value, str):
                # For strings: invert by negating each char ordinal.
                # This preserves ordering: "2024" < "2025" → negated "2024" > negated "2025"
                key_parts.append(tuple(-ord(ch) for ch in value) if value else ())
            else:
                key_parts.append(-value)
    return tuple(key_parts)


def pick_keeper(files: list[dict], criteria: list[SortCriterion]) -> int:
    """Pick the file_id of the best file according to the criteria chain.

    Args:
        files: List of file dicts (must have len >= 1). Each must have "id".
        criteria: Ordered list of sort criteria.

    Returns:
        file_id of the winning file.

    Raises:
        ValueError: if files is empty or criteria is empty.
    """
    if not files:
        raise ValueError("Cannot pick keeper from empty file list")
    if not criteria:
        raise ValueError("Cannot pick keeper with empty criteria chain")

    best = min(files, key=lambda f: build_sort_key(criteria, f))
    return best["id"]


# ---------------------------------------------------------------------------
# Quick-preset -> chain mappings
# ---------------------------------------------------------------------------

PRESET_CHAINS: dict[str, list[SortCriterion]] = {
    "KEEP_LARGEST_FILE": [
        SortCriterion("size", ascending=False),
        SortCriterion("modified_at", ascending=False),
        SortCriterion("path_depth", ascending=True),
    ],
    "KEEP_HIGHEST_RESOLUTION": [
        SortCriterion("resolution", ascending=False),
        SortCriterion("size", ascending=False),
        SortCriterion("modified_at", ascending=False),
    ],
    "KEEP_NEWEST": [
        SortCriterion("modified_at", ascending=False),
        SortCriterion("size", ascending=False),
        SortCriterion("path_depth", ascending=True),
    ],
    "KEEP_OLDEST": [
        SortCriterion("modified_at", ascending=True),
        SortCriterion("size", ascending=False),
        SortCriterion("path_depth", ascending=True),
    ],
    "KEEP_SHORTEST_PATH": [
        SortCriterion("path_depth", ascending=True),
        SortCriterion("size", ascending=False),
        SortCriterion("modified_at", ascending=False),
    ],
    "KEEP_DEEPEST_PATH": [
        SortCriterion("path_depth", ascending=False),
        SortCriterion("size", ascending=False),
        SortCriterion("modified_at", ascending=False),
    ],
}
