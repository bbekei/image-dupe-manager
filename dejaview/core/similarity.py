"""
core/similarity.py — Perceptual-hash similarity grouping (plan §S2.4).

Pure-function module: no DB, no Qt.  Takes file dicts with perceptual_hash
and pixel_hash keys, returns similarity groups.

Algorithm:
  1. Deduplicate by pixel_hash (one representative per exact-duplicate set)
  2. O(n^2) pairwise Hamming distance on representatives
  3. Union-Find for transitive closure (A~B, B~C => {A,B,C})
  4. Expand representatives back to all files
  5. Filter: groups must have >=2 distinct pixel_hashes
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Hamming distance
# ---------------------------------------------------------------------------

def hamming_distance(hash_hex_a: str, hash_hex_b: str) -> int:
    """Return Hamming distance (bit-level) between two hex-encoded hashes.

    Both hashes must be the same length hex string (e.g. 16 hex chars = 64 bits).
    """
    val_a = int(hash_hex_a, 16)
    val_b = int(hash_hex_b, 16)
    return bin(val_a ^ val_b).count("1")


# ---------------------------------------------------------------------------
# Union-Find (disjoint-set) for transitive closure
# ---------------------------------------------------------------------------

class _UnionFind:
    """Weighted quick-union with path compression."""

    __slots__ = ("_parent", "_rank")

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1


# ---------------------------------------------------------------------------
# Similarity grouping
# ---------------------------------------------------------------------------

def build_similarity_groups(
    files: list[dict],
    threshold: int = 8,
) -> list[list[dict]]:
    """Group files by perceptual hash similarity using Union-Find.

    Args:
        files: List of dicts with at least keys:
               'id', 'pixel_hash', 'perceptual_hash', 'path', 'size'.
        threshold: Maximum Hamming distance to consider two images similar.

    Returns:
        List of groups, where each group is a list of file dicts.
        Only groups with >=2 distinct pixel_hashes are included
        (exact duplicates are excluded from similarity grouping).

    Algorithm:
      1. Deduplicate by pixel_hash — pick one representative per exact-dup set
      2. O(n^2) pairwise Hamming distance on representatives
      3. Union-Find for transitive closure (A~B, B~C => {A,B,C})
      4. Expand representatives back to all files in each group
      5. Filter: groups must have >=2 distinct pixel_hashes
    """
    if not files:
        return []

    # Step 1: Deduplicate by pixel_hash — one representative per exact set.
    # Map pixel_hash -> list of file dicts sharing that hash.
    by_pixel: dict[str, list[dict]] = {}
    for f in files:
        ph = f.get("pixel_hash")
        if ph is None:
            continue
        by_pixel.setdefault(ph, []).append(f)

    # Build list of representatives (first file per pixel_hash).
    representatives: list[dict] = []
    pixel_hash_to_idx: dict[str, int] = {}
    for pixel_hash, group in by_pixel.items():
        idx = len(representatives)
        pixel_hash_to_idx[pixel_hash] = idx
        representatives.append(group[0])

    n = len(representatives)
    if n < 2:
        return []

    # Step 2-3: Pairwise Hamming + Union-Find.
    uf = _UnionFind(n)
    phashes = [r["perceptual_hash"] for r in representatives]

    for i in range(n):
        if phashes[i] is None:
            continue
        for j in range(i + 1, n):
            if phashes[j] is None:
                continue
            dist = hamming_distance(phashes[i], phashes[j])
            if dist <= threshold:
                uf.union(i, j)

    # Step 4: Collect connected components, expand to all files.
    components: dict[int, list[int]] = {}
    for i in range(n):
        root = uf.find(i)
        components.setdefault(root, []).append(i)

    # Step 5: Filter — only groups with >=2 distinct pixel_hashes.
    result: list[list[dict]] = []
    for member_indices in components.values():
        if len(member_indices) < 2:
            continue
        # Expand: include all files from each pixel_hash group.
        group_files: list[dict] = []
        for idx in member_indices:
            rep = representatives[idx]
            pixel_hash = rep["pixel_hash"]
            group_files.extend(by_pixel[pixel_hash])
        result.append(group_files)

    return result
