"""
data/compression.py — JSON data compression and decompression for DejaView.

Module ownership (FEATURE_REQUEST_UX_JSON_COMPRESSION):
- Streaming GZip compression via BytesIO + json.dump() (R-COMP-03).
- Field shortening for compact JSON schema (§3 Data Optimization).
- Path tokenization to replace common root paths with short tokens.
- Hash-centric grouping to eliminate per-file hash repetition.
- SHA-256 integrity checksums (R-COMP-04).
- No Google Drive API calls (that's sync.py).
- No direct UI interaction.
"""

import gzip
import hashlib
import io
import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field shortening maps (§3 — Field Shortening)
# ---------------------------------------------------------------------------

# Full key -> short key (used during compression)
_FIELD_TO_SHORT = {
    "pixel_hash": "h",
    "path": "p",
    "size": "s",
    "modified_at": "m",
    "filename": "f",
    "remote_id": "r",
    "perceptual_hash": "ph",
}

# Short key -> full key (used during decompression)
_SHORT_TO_FIELD = {v: k for k, v in _FIELD_TO_SHORT.items()}


# ---------------------------------------------------------------------------
# Path tokenization (§3 — Path Tokenization)
# ---------------------------------------------------------------------------

def _detect_common_roots(paths: list[str], threshold: float = 0.3) -> list[str]:
    """Detect common root paths that appear in at least `threshold` fraction of paths.

    Returns roots sorted longest-first so replacement is greedy.
    """
    if not paths:
        return []

    # Count directory prefixes
    prefix_counts: dict[str, int] = {}
    for p in paths:
        # Normalize to forward slashes for consistent processing
        normalized = p.replace("\\", "/")
        parts = normalized.split("/")
        # Build increasing prefixes (skip the filename)
        for depth in range(1, len(parts)):
            prefix = "/".join(parts[:depth])
            if len(prefix) > 3:  # Skip trivially short prefixes like "C:"
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    min_count = max(2, int(len(paths) * threshold))
    # Filter to prefixes meeting the threshold and long enough to save space
    candidates = [
        (prefix, count)
        for prefix, count in prefix_counts.items()
        if count >= min_count and len(prefix) >= 10
    ]

    if not candidates:
        return []

    # Sort by length descending (longest first) then by count descending
    candidates.sort(key=lambda x: (-len(x[0]), -x[1]))

    # Deduplicate: remove prefixes that are substrings of already-selected ones
    selected: list[str] = []
    for prefix, _ in candidates:
        if not any(prefix.startswith(s + "/") for s in selected):
            selected.append(prefix)
        if len(selected) >= 8:  # Cap at 8 tokens
            break

    return selected


def tokenize_paths(
    entries: list[dict], path_key: str = "p"
) -> tuple[list[dict], dict[str, str]]:
    """Replace common root paths with short tokens.

    Returns (modified entries, token_map: {token: original_root}).
    """
    paths = [e[path_key] for e in entries if path_key in e and e[path_key]]
    roots = _detect_common_roots(paths)

    if not roots:
        return entries, {}

    token_map: dict[str, str] = {}
    root_to_token: dict[str, str] = {}
    for i, root in enumerate(roots):
        token = f"<R{i}>"
        token_map[token] = root
        root_to_token[root] = token

    result = []
    for entry in entries:
        e = dict(entry)
        if path_key in e and e[path_key]:
            normalized = e[path_key].replace("\\", "/")
            for root, token in root_to_token.items():
                if normalized.startswith(root + "/") or normalized == root:
                    e[path_key] = normalized.replace(root, token, 1)
                    break
        result.append(e)

    return result, token_map


def detokenize_paths(
    entries: list[dict], token_map: dict[str, str], path_key: str = "p"
) -> list[dict]:
    """Restore tokenized paths to their original form."""
    if not token_map:
        return entries

    result = []
    for entry in entries:
        e = dict(entry)
        if path_key in e and e[path_key]:
            for token, root in token_map.items():
                if e[path_key].startswith(token):
                    e[path_key] = e[path_key].replace(token, root, 1)
                    break
        result.append(e)

    return result


# ---------------------------------------------------------------------------
# Field shortening (§3 — Field Shortening)
# ---------------------------------------------------------------------------

def shorten_fields(entry: dict) -> dict:
    """Replace long field names with short keys."""
    return {_FIELD_TO_SHORT.get(k, k): v for k, v in entry.items()}


def expand_fields(entry: dict) -> dict:
    """Restore short keys to their full field names."""
    return {_SHORT_TO_FIELD.get(k, k): v for k, v in entry.items()}


# ---------------------------------------------------------------------------
# Hash-centric grouping (§3 — Redundancy Removal)
# ---------------------------------------------------------------------------

def group_by_hash(entries: list[dict], hash_key: str = "h") -> list[dict]:
    """Group file entries by hash, storing the hash once per group.

    Input: flat list of file entries, each with a hash_key field.
    Output: list of {hash_key: ..., "files": [entries_without_hash]}.
    """
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        h = entry.get(hash_key)
        if h is None:
            continue
        file_entry = {k: v for k, v in entry.items() if k != hash_key}
        groups.setdefault(h, []).append(file_entry)

    return [
        {hash_key: h, "files": file_list}
        for h, file_list in groups.items()
    ]


def ungroup_by_hash(groups: list[dict], hash_key: str = "h") -> list[dict]:
    """Flatten hash-centric groups back to a flat file list."""
    entries = []
    for group in groups:
        h = group[hash_key]
        for file_entry in group.get("files", []):
            entry = dict(file_entry)
            entry[hash_key] = h
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Streaming compression (R-COMP-03)
# ---------------------------------------------------------------------------

def compress_payload(payload: dict) -> bytes:
    """Compress a JSON-serializable dict to a gzip blob using streaming.

    Writes JSON directly into a GzipFile wrapping a BytesIO, avoiding
    building the full uncompressed JSON string in memory (R-COMP-03).

    Returns the compressed bytes.
    """
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
        # Wrap the gzip binary stream with a text wrapper for json.dump
        text_wrapper = io.TextIOWrapper(gz, encoding='utf-8')
        json.dump(payload, text_wrapper, ensure_ascii=False, separators=(',', ':'))
        text_wrapper.flush()
        # Do NOT close text_wrapper — it would close gz prematurely
        text_wrapper.detach()
    return buf.getvalue()


def decompress_payload(data: bytes) -> dict:
    """Decompress a gzip blob to a JSON dict in-memory (R-COMP-03).

    Raises ValueError if the data cannot be decompressed or parsed.
    """
    try:
        buf = io.BytesIO(data)
        with gzip.GzipFile(fileobj=buf, mode='rb') as gz:
            raw = gz.read()
    except (gzip.BadGzipFile, OSError) as exc:
        raise ValueError(f"Decompression failed: {exc}") from exc

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"JSON parse failed after decompression: {exc}") from exc


# ---------------------------------------------------------------------------
# SHA-256 integrity (R-COMP-04)
# ---------------------------------------------------------------------------

def compute_sha256(data: bytes) -> str:
    """Compute hex SHA-256 digest of a bytes blob."""
    return hashlib.sha256(data).hexdigest()


def verify_checksum(data: bytes, expected_sha256: str) -> bool:
    """Verify SHA-256 checksum of data against expected value (R-COMP-04)."""
    return compute_sha256(data) == expected_sha256


# ---------------------------------------------------------------------------
# Compression ratio reporting (§5.1)
# ---------------------------------------------------------------------------

def format_compression_ratio(
    uncompressed_size: int, compressed_size: int
) -> str:
    """Format compression savings for display.

    Returns e.g. "Compressed 47 MB → 3.2 MB (93% reduction)".
    """
    if uncompressed_size <= 0:
        return ""

    reduction = (1 - compressed_size / uncompressed_size) * 100

    def _fmt_size(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f} MB"
        if n >= 1_000:
            return f"{n / 1_000:.1f} KB"
        return f"{n} B"

    return (
        f"Compressed {_fmt_size(uncompressed_size)} → "
        f"{_fmt_size(compressed_size)} ({reduction:.0f}% reduction)"
    )


# ---------------------------------------------------------------------------
# Full pipeline: optimize + compress (combines all §3 strategies + R-COMP-03)
# ---------------------------------------------------------------------------

def build_optimized_compressed(payload: dict) -> tuple[bytes, int]:
    """Apply all optimization strategies then compress.

    Steps:
    1. Shorten field names in each file entry
    2. Tokenize common path roots
    3. Group entries by hash (redundancy removal)
    4. Stream-compress with gzip

    Args:
        payload: Standard export payload with "files" list.

    Returns:
        (compressed_bytes, uncompressed_json_size) for ratio reporting.
    """
    # Work on a copy
    optimized = dict(payload)

    files = optimized.get("files", [])
    if files:
        # Step 1: Field shortening
        shortened = [shorten_fields(entry) for entry in files]

        # Step 2: Path tokenization
        shortened, token_map = tokenize_paths(shortened, path_key="p")

        # Step 3: Hash-centric grouping
        grouped = group_by_hash(shortened, hash_key="h")

        optimized["files"] = grouped
        if token_map:
            optimized["_path_tokens"] = token_map
        optimized["_format"] = "optimized_v1"

    # Measure uncompressed size (approximate — using compact separators)
    uncompressed_json = json.dumps(
        optimized, ensure_ascii=False, separators=(',', ':')
    )
    uncompressed_size = len(uncompressed_json.encode('utf-8'))

    # Step 4: Compress
    compressed = compress_payload(optimized)

    return compressed, uncompressed_size


def decompress_and_expand(data: bytes) -> dict:
    """Decompress and reverse all optimization strategies.

    Detects the "_format" field to determine if optimizations were applied.
    """
    payload = decompress_payload(data)

    # If not an optimized payload, return as-is
    if payload.get("_format") != "optimized_v1":
        return payload

    # Reverse Step 3: Ungroup by hash
    grouped_files = payload.get("files", [])
    flat_files = ungroup_by_hash(grouped_files, hash_key="h")

    # Reverse Step 2: Detokenize paths
    token_map = payload.get("_path_tokens", {})
    if token_map:
        flat_files = detokenize_paths(flat_files, token_map, path_key="p")

    # Reverse Step 1: Expand field names
    expanded = [expand_fields(entry) for entry in flat_files]

    # Clean up internal fields
    result = {k: v for k, v in payload.items()
              if k not in ("files", "_path_tokens", "_format")}
    result["files"] = expanded

    return result
