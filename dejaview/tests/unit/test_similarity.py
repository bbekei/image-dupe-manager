"""
tests/unit/test_similarity.py — Unit tests for core/similarity.py.

Plan reference: §S2.8 — Grouping algorithm tests.
"""

import pytest

from core.similarity import build_similarity_groups, hamming_distance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file(
    fid: int,
    pixel_hash: str,
    perceptual_hash: str,
    path: str = "",
    size: int = 1000,
) -> dict:
    """Create a minimal file dict for grouping tests."""
    return {
        "id": fid,
        "pixel_hash": pixel_hash,
        "perceptual_hash": perceptual_hash,
        "path": path or f"/img_{fid}.jpg",
        "size": size,
    }


def _phash_with_bits_set(*bit_positions: int) -> str:
    """Return a 16-char hex pHash (64-bit) with specified bit positions set.

    Bit 0 is the least significant bit.
    """
    val = 0
    for b in bit_positions:
        val |= 1 << b
    return f"{val:016x}"


# ---------------------------------------------------------------------------
# hamming_distance tests
# ---------------------------------------------------------------------------

class TestHammingDistance:

    def test_identical_hashes(self):
        assert hamming_distance("abcdef01", "abcdef01") == 0

    def test_single_bit_diff(self):
        # 0x0 vs 0x1 = 1 bit different
        assert hamming_distance("0000000000000000", "0000000000000001") == 1

    def test_all_bits_different(self):
        # 0x0000 vs 0xffff for 16-hex-char (64-bit) hashes
        assert hamming_distance("0000000000000000", "ffffffffffffffff") == 64

    def test_known_distance(self):
        # 0xff = 11111111 vs 0x00 = 00000000 => 8 bits different
        assert hamming_distance("00000000000000ff", "0000000000000000") == 8

    def test_symmetric(self):
        a = "abcdef0123456789"
        b = "0000000000000000"
        assert hamming_distance(a, b) == hamming_distance(b, a)


# ---------------------------------------------------------------------------
# build_similarity_groups tests
# ---------------------------------------------------------------------------

class TestBuildSimilarityGroups:

    def test_empty_input(self):
        assert build_similarity_groups([]) == []

    def test_single_file_no_group(self):
        """A single file cannot form a group."""
        files = [_file(1, "a" * 32, _phash_with_bits_set(0))]
        assert build_similarity_groups(files) == []

    def test_two_identical_pixel_hashes_excluded(self):
        """Exact duplicates (same pixel_hash) must NOT form similarity groups."""
        ph = "a" * 32
        files = [
            _file(1, ph, _phash_with_bits_set(0)),
            _file(2, ph, _phash_with_bits_set(0)),
        ]
        result = build_similarity_groups(files)
        assert result == []

    def test_two_similar_files_grouped(self):
        """Two files with different pixel_hash but close pHash form a group."""
        p1 = _phash_with_bits_set()       # 0x0000000000000000
        p2 = _phash_with_bits_set(0, 1)   # 2 bits set -> distance 2
        files = [
            _file(1, "a" * 32, p1),
            _file(2, "b" * 32, p2),
        ]
        result = build_similarity_groups(files, threshold=8)
        assert len(result) == 1
        ids = {f["id"] for f in result[0]}
        assert ids == {1, 2}

    def test_threshold_exclusion(self):
        """Files with distance > threshold must NOT be grouped."""
        p1 = _phash_with_bits_set()
        # Set 10 bits => distance 10
        p2 = _phash_with_bits_set(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
        files = [
            _file(1, "a" * 32, p1),
            _file(2, "b" * 32, p2),
        ]
        result = build_similarity_groups(files, threshold=8)
        assert result == []

    def test_threshold_boundary_included(self):
        """Files with distance == threshold must be included."""
        p1 = _phash_with_bits_set()
        p2 = _phash_with_bits_set(0, 1, 2, 3, 4, 5, 6, 7)  # 8 bits
        files = [
            _file(1, "a" * 32, p1),
            _file(2, "b" * 32, p2),
        ]
        result = build_similarity_groups(files, threshold=8)
        assert len(result) == 1

    def test_transitive_closure(self):
        """A~B and B~C must produce {A, B, C} via Union-Find."""
        p_a = _phash_with_bits_set()                 # 0 bits
        p_b = _phash_with_bits_set(0, 1, 2)          # dist(A,B) = 3
        p_c = _phash_with_bits_set(0, 1, 2, 3, 4, 5) # dist(B,C) = 3, dist(A,C) = 6
        files = [
            _file(1, "a" * 32, p_a),
            _file(2, "b" * 32, p_b),
            _file(3, "c" * 32, p_c),
        ]
        result = build_similarity_groups(files, threshold=4)
        assert len(result) == 1
        ids = {f["id"] for f in result[0]}
        assert ids == {1, 2, 3}

    def test_two_separate_groups(self):
        """Distant files form separate groups with tight threshold."""
        # Group 1: bits 0-1 (close to each other, far from group 2)
        p_a = _phash_with_bits_set(0)
        p_b = _phash_with_bits_set(0, 1)  # dist(A,B) = 1

        # Group 2: bits 60-63 (far from group 1)
        p_c = _phash_with_bits_set(60, 61, 62, 63)
        p_d = _phash_with_bits_set(60, 61, 62)  # dist(C,D) = 1

        files = [
            _file(1, "a" * 32, p_a),
            _file(2, "b" * 32, p_b),
            _file(3, "c" * 32, p_c),
            _file(4, "d" * 32, p_d),
        ]
        # threshold=2: intra-group distance <=2 but inter-group distance >= 4
        result = build_similarity_groups(files, threshold=2)
        assert len(result) == 2
        group_ids = [frozenset(f["id"] for f in g) for g in result]
        assert frozenset({1, 2}) in group_ids
        assert frozenset({3, 4}) in group_ids

    def test_exact_dupes_expanded_into_group(self):
        """Exact duplicates of a representative are included in the group.

        If A1, A2 share pixel_hash "a" and B1 shares pixel_hash "b",
        and pHash(a) ~ pHash(b), the group should contain {A1, A2, B1}.
        """
        p_a = _phash_with_bits_set(0)
        p_b = _phash_with_bits_set(0, 1)  # dist 1

        files = [
            _file(1, "a" * 32, p_a),
            _file(2, "a" * 32, p_a),  # exact dupe of file 1
            _file(3, "b" * 32, p_b),
        ]
        result = build_similarity_groups(files, threshold=8)
        assert len(result) == 1
        ids = {f["id"] for f in result[0]}
        assert ids == {1, 2, 3}

    def test_files_without_pixel_hash_skipped(self):
        """Files with pixel_hash=None are skipped gracefully."""
        files = [
            _file(1, None, _phash_with_bits_set(0)),
            _file(2, "b" * 32, _phash_with_bits_set(0)),
        ]
        # Should not crash; file 1 has no pixel_hash
        result = build_similarity_groups(files, threshold=8)
        assert result == []

    def test_files_without_perceptual_hash_skipped(self):
        """Files with perceptual_hash=None are not matched pairwise."""
        files = [
            _file(1, "a" * 32, None),
            _file(2, "b" * 32, None),
        ]
        result = build_similarity_groups(files, threshold=8)
        assert result == []

    def test_custom_threshold(self):
        """Threshold=0 means only identical pHashes group together."""
        same_ph = _phash_with_bits_set(5, 10)
        files = [
            _file(1, "a" * 32, same_ph),
            _file(2, "b" * 32, same_ph),
        ]
        result = build_similarity_groups(files, threshold=0)
        assert len(result) == 1

        # But distance=1 should be excluded at threshold=0
        p2 = _phash_with_bits_set(5, 10, 11)
        files2 = [
            _file(1, "a" * 32, same_ph),
            _file(2, "b" * 32, p2),
        ]
        result2 = build_similarity_groups(files2, threshold=0)
        assert result2 == []

    def test_mixed_exact_and_similar(self):
        """Exact dupes within a similarity group don't inflate group count.

        Group must have >=2 distinct pixel_hashes.
        """
        ph = _phash_with_bits_set(0)
        # 3 files with same pixel_hash — no group (only 1 distinct pixel_hash)
        files = [
            _file(1, "a" * 32, ph),
            _file(2, "a" * 32, ph),
            _file(3, "a" * 32, ph),
        ]
        assert build_similarity_groups(files) == []
