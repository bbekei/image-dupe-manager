"""
Tests for core/sort_chain.py — Composable sort-chain evaluator.
"""

import pytest

from core.sort_chain import (
    FIELD_EXTRACTORS,
    PRESET_CHAINS,
    VALID_FIELDS,
    SortCriterion,
    build_sort_key,
    pick_keeper,
)


# ---------------------------------------------------------------------------
# SortCriterion validation
# ---------------------------------------------------------------------------

class TestSortCriterion:

    def test_valid_fields(self):
        for field in VALID_FIELDS:
            c = SortCriterion(field, ascending=True)
            assert c.field == field

    def test_invalid_field_raises(self):
        with pytest.raises(ValueError, match="Unknown field"):
            SortCriterion("nonexistent", ascending=True)

    def test_frozen(self):
        c = SortCriterion("size", ascending=False)
        with pytest.raises(AttributeError):
            c.field = "resolution"


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

class TestFieldExtractors:

    def test_size(self):
        assert FIELD_EXTRACTORS["size"]({"size": 1024}) == 1024
        assert FIELD_EXTRACTORS["size"]({}) == 0
        assert FIELD_EXTRACTORS["size"]({"size": None}) == 0

    def test_resolution(self):
        assert FIELD_EXTRACTORS["resolution"]({"width": 1920, "height": 1080}) == 1920 * 1080
        assert FIELD_EXTRACTORS["resolution"]({}) == 0
        assert FIELD_EXTRACTORS["resolution"]({"width": None, "height": 1080}) == 0

    def test_modified_at(self):
        assert FIELD_EXTRACTORS["modified_at"]({"modified_at": "2024-06-15"}) == "2024-06-15"
        assert FIELD_EXTRACTORS["modified_at"]({}) == ""

    def test_path_depth(self):
        assert FIELD_EXTRACTORS["path_depth"]({"path": "/a/b/c.jpg"}) == 3
        assert FIELD_EXTRACTORS["path_depth"]({"path": "C:\\Users\\photos\\img.jpg"}) == 3
        assert FIELD_EXTRACTORS["path_depth"]({"path": "/a/b\\c/d.jpg"}) == 4
        assert FIELD_EXTRACTORS["path_depth"]({}) == 0

    def test_filename_length(self):
        assert FIELD_EXTRACTORS["filename_length"]({"path": "/photos/vacation.jpg"}) == len("vacation.jpg")
        assert FIELD_EXTRACTORS["filename_length"]({"path": "C:\\pics\\a.jpg"}) == len("a.jpg")
        assert FIELD_EXTRACTORS["filename_length"]({}) == 0


# ---------------------------------------------------------------------------
# build_sort_key
# ---------------------------------------------------------------------------

class TestBuildSortKey:

    def test_ascending_size(self):
        criteria = [SortCriterion("size", ascending=True)]
        small = {"id": 1, "size": 100}
        large = {"id": 2, "size": 1000}
        assert build_sort_key(criteria, small) < build_sort_key(criteria, large)

    def test_descending_size(self):
        criteria = [SortCriterion("size", ascending=False)]
        small = {"id": 1, "size": 100}
        large = {"id": 2, "size": 1000}
        # Descending: large should have smaller key (negated)
        assert build_sort_key(criteria, large) < build_sort_key(criteria, small)

    def test_descending_string(self):
        criteria = [SortCriterion("modified_at", ascending=False)]
        old = {"id": 1, "modified_at": "2020-01-01"}
        new = {"id": 2, "modified_at": "2024-06-15"}
        # Descending: newer should have smaller key
        assert build_sort_key(criteria, new) < build_sort_key(criteria, old)

    def test_multi_criteria_tiebreak(self):
        criteria = [
            SortCriterion("size", ascending=False),
            SortCriterion("modified_at", ascending=False),
        ]
        # Same size, different date
        a = {"id": 1, "size": 1000, "modified_at": "2020-01-01"}
        b = {"id": 2, "size": 1000, "modified_at": "2024-06-15"}
        # b is newer, so b should win (smaller key)
        assert build_sort_key(criteria, b) < build_sort_key(criteria, a)


# ---------------------------------------------------------------------------
# pick_keeper
# ---------------------------------------------------------------------------

class TestPickKeeper:

    def test_empty_files_raises(self):
        with pytest.raises(ValueError, match="empty file list"):
            pick_keeper([], [SortCriterion("size", ascending=False)])

    def test_empty_criteria_raises(self):
        with pytest.raises(ValueError, match="empty criteria chain"):
            pick_keeper([{"id": 1, "size": 100}], [])

    def test_single_file(self):
        files = [{"id": 42, "size": 100}]
        result = pick_keeper(files, [SortCriterion("size", ascending=False)])
        assert result == 42

    def test_keep_largest(self):
        files = [
            {"id": 1, "size": 500, "modified_at": "2024-01-01", "path": "/a.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-01-01", "path": "/b.jpg"},
            {"id": 3, "size": 750, "modified_at": "2024-01-01", "path": "/c.jpg"},
        ]
        result = pick_keeper(files, PRESET_CHAINS["KEEP_LARGEST_FILE"])
        assert result == 2

    def test_keep_newest(self):
        files = [
            {"id": 1, "size": 1000, "modified_at": "2020-01-01", "path": "/a.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-06-15", "path": "/b.jpg"},
        ]
        result = pick_keeper(files, PRESET_CHAINS["KEEP_NEWEST"])
        assert result == 2

    def test_keep_oldest(self):
        files = [
            {"id": 1, "size": 1000, "modified_at": "2020-01-01", "path": "/a.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-06-15", "path": "/b.jpg"},
        ]
        result = pick_keeper(files, PRESET_CHAINS["KEEP_OLDEST"])
        assert result == 1

    def test_keep_highest_resolution(self):
        files = [
            {"id": 1, "size": 500, "width": 1920, "height": 1080, "modified_at": "2024-01-01", "path": "/a.jpg"},
            {"id": 2, "size": 800, "width": 3840, "height": 2160, "modified_at": "2024-01-01", "path": "/b.jpg"},
        ]
        result = pick_keeper(files, PRESET_CHAINS["KEEP_HIGHEST_RESOLUTION"])
        assert result == 2

    def test_keep_shortest_path(self):
        files = [
            {"id": 1, "size": 1000, "modified_at": "2024-01-01", "path": "/a/b/c/d/img.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-01-01", "path": "/a/img.jpg"},
        ]
        result = pick_keeper(files, PRESET_CHAINS["KEEP_SHORTEST_PATH"])
        assert result == 2

    def test_tiebreak_falls_through(self):
        """When primary criterion ties, secondary decides."""
        files = [
            {"id": 1, "size": 1000, "modified_at": "2020-01-01", "path": "/a.jpg"},
            {"id": 2, "size": 1000, "modified_at": "2024-06-15", "path": "/b.jpg"},
        ]
        # KEEP_LARGEST_FILE: size ties, then modified_at desc breaks it
        result = pick_keeper(files, PRESET_CHAINS["KEEP_LARGEST_FILE"])
        assert result == 2

    def test_custom_chain(self):
        """User-defined chain: shortest filename, then largest size."""
        chain = [
            SortCriterion("filename_length", ascending=True),
            SortCriterion("size", ascending=False),
        ]
        files = [
            {"id": 1, "size": 500, "path": "/photos/a.jpg"},
            {"id": 2, "size": 1000, "path": "/photos/vacation_photo_2024.jpg"},
        ]
        # a.jpg has shorter filename → wins
        result = pick_keeper(files, chain)
        assert result == 1

    def test_missing_fields_handled(self):
        """Files with missing fields don't crash — default to 0/empty."""
        chain = [SortCriterion("resolution", ascending=False)]
        files = [
            {"id": 1},
            {"id": 2, "width": 1920, "height": 1080},
        ]
        result = pick_keeper(files, chain)
        assert result == 2


# ---------------------------------------------------------------------------
# PRESET_CHAINS completeness
# ---------------------------------------------------------------------------

class TestPresetChains:

    def test_all_presets_defined(self):
        expected = {
            "KEEP_LARGEST_FILE",
            "KEEP_HIGHEST_RESOLUTION",
            "KEEP_NEWEST",
            "KEEP_OLDEST",
            "KEEP_SHORTEST_PATH",
            "KEEP_DEEPEST_PATH",
        }
        assert set(PRESET_CHAINS) == expected

    def test_all_criteria_valid(self):
        for name, chain in PRESET_CHAINS.items():
            assert len(chain) >= 1, f"{name} has empty chain"
            for c in chain:
                assert c.field in FIELD_EXTRACTORS, f"{name}: invalid field {c.field}"
