"""
tests/unit/test_property.py — Property-based tests using Hypothesis.

Phase 3: sort_chain stability, similarity triangle inequality.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from core.sort_chain import SortCriterion, build_sort_key, pick_keeper, PRESET_CHAINS
from core.similarity import hamming_distance


# ── sort_chain properties ────────────────────────────────────────────────────

# Strategy for file-like dicts (matches what pick_keeper expects)
file_st = st.fixed_dictionaries({
    "id": st.integers(min_value=1, max_value=10000),
    "size": st.integers(min_value=0, max_value=10**9),
    "width": st.one_of(st.none(), st.integers(min_value=1, max_value=8000)),
    "height": st.one_of(st.none(), st.integers(min_value=1, max_value=8000)),
    "modified_at": st.text(
        alphabet="0123456789-T:Z",
        min_size=10, max_size=25,
    ),
    "path": st.from_regex(r"/[a-z]{1,5}(/[a-z]{1,10}){0,5}/[a-z]{1,8}\.(jpg|png)", fullmatch=True),
})

criteria_st = st.sampled_from(list(PRESET_CHAINS.values()))


class TestSortChainProperties:

    @given(files=st.lists(file_st, min_size=2, max_size=10), criteria=criteria_st)
    @settings(max_examples=100, deadline=1000)
    def test_pick_keeper_always_returns_valid_id(self, files, criteria):
        """pick_keeper must return an id that exists in the input files."""
        all_ids = {f["id"] for f in files}
        assume(len(all_ids) == len(files))  # unique IDs
        winner = pick_keeper(files, criteria)
        assert winner in all_ids

    @given(files=st.lists(file_st, min_size=2, max_size=10), criteria=criteria_st)
    @settings(max_examples=100, deadline=1000)
    def test_pick_keeper_is_deterministic(self, files, criteria):
        """Same input must always produce the same winner."""
        assume(len({f["id"] for f in files}) == len(files))
        result1 = pick_keeper(files, criteria)
        result2 = pick_keeper(files, criteria)
        assert result1 == result2

    @given(files=st.lists(file_st, min_size=3, max_size=8), criteria=criteria_st)
    @settings(max_examples=50, deadline=1000)
    def test_pick_keeper_stable_under_reorder(self, files, criteria):
        """Reordering input files must not change the winner."""
        assume(len({f["id"] for f in files}) == len(files))
        import random
        result1 = pick_keeper(files, criteria)
        shuffled = files.copy()
        random.shuffle(shuffled)
        result2 = pick_keeper(shuffled, criteria)
        assert result1 == result2

    @given(file=file_st, criteria=criteria_st)
    @settings(max_examples=50, deadline=1000)
    def test_build_sort_key_returns_tuple(self, file, criteria):
        """build_sort_key must return a tuple with one element per criterion."""
        key = build_sort_key(criteria, file)
        assert isinstance(key, tuple)
        assert len(key) == len(criteria)


# ── similarity triangle inequality ───────────────────────────────────────────

# Strategy for hex hash strings (same length as pHash output: 16 hex chars = 64 bits)
hex_hash_st = st.from_regex(r"[0-9a-f]{16}", fullmatch=True)


class TestSimilarityProperties:

    @given(a=hex_hash_st)
    @settings(max_examples=50)
    def test_hamming_distance_self_is_zero(self, a):
        """Distance from a hash to itself must be 0."""
        assert hamming_distance(a, a) == 0

    @given(a=hex_hash_st, b=hex_hash_st)
    @settings(max_examples=100)
    def test_hamming_distance_symmetric(self, a, b):
        """d(a, b) == d(b, a)."""
        assert hamming_distance(a, b) == hamming_distance(b, a)

    @given(a=hex_hash_st, b=hex_hash_st)
    @settings(max_examples=100)
    def test_hamming_distance_non_negative(self, a, b):
        """Distance must be >= 0."""
        assert hamming_distance(a, b) >= 0

    @given(a=hex_hash_st, b=hex_hash_st, c=hex_hash_st)
    @settings(max_examples=100)
    def test_hamming_triangle_inequality(self, a, b, c):
        """d(a, c) <= d(a, b) + d(b, c) — triangle inequality."""
        d_ac = hamming_distance(a, c)
        d_ab = hamming_distance(a, b)
        d_bc = hamming_distance(b, c)
        assert d_ac <= d_ab + d_bc, (
            f"Triangle inequality violated: d({a},{c})={d_ac} > "
            f"d({a},{b})={d_ab} + d({b},{c})={d_bc}"
        )

    @given(a=hex_hash_st, b=hex_hash_st)
    @settings(max_examples=50)
    def test_hamming_distance_bounded_by_bit_length(self, a, b):
        """Distance cannot exceed the number of bits (64 for 16-char hex)."""
        d = hamming_distance(a, b)
        assert d <= len(a) * 4  # each hex char = 4 bits
