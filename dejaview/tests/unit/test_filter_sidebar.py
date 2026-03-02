"""
Tests for ui/filter_sidebar.py — FilterCriteria dataclass and FilterSidebar widget.

UX Redesign Phase 5 — Advanced Cleanup.
"""

import pytest

from ui.filter_sidebar import FilterCriteria, FilterSidebar


# ---------------------------------------------------------------------------
# FilterCriteria dataclass
# ---------------------------------------------------------------------------

class TestFilterCriteria:
    """Tests for the FilterCriteria dataclass defaults and construction."""

    def test_default_values(self):
        fc = FilterCriteria()
        assert fc.date_from is None
        assert fc.date_to is None
        assert fc.extensions is None
        assert fc.min_copies == 2
        assert fc.full_dupe_folders_only is False
        assert fc.search_text is None
        assert fc.sort_by == "waste"
        assert fc.sort_descending is True

    def test_custom_values(self):
        fc = FilterCriteria(
            date_from="2024-01-01",
            date_to="2024-12-31",
            extensions=[".jpg", ".jpeg"],
            min_copies=3,
            full_dupe_folders_only=True,
            search_text="vacation",
            sort_by="copies",
            sort_descending=False,
        )
        assert fc.date_from == "2024-01-01"
        assert fc.date_to == "2024-12-31"
        assert fc.extensions == [".jpg", ".jpeg"]
        assert fc.min_copies == 3
        assert fc.full_dupe_folders_only is True
        assert fc.search_text == "vacation"
        assert fc.sort_by == "copies"
        assert fc.sort_descending is False

    def test_equality(self):
        fc1 = FilterCriteria(min_copies=3, sort_by="copies")
        fc2 = FilterCriteria(min_copies=3, sort_by="copies")
        assert fc1 == fc2

    def test_inequality(self):
        fc1 = FilterCriteria(min_copies=2)
        fc2 = FilterCriteria(min_copies=3)
        assert fc1 != fc2


# ---------------------------------------------------------------------------
# _expand_extensions static helper
# ---------------------------------------------------------------------------

class TestExpandExtensions:
    """Tests for FilterSidebar._expand_extensions()."""

    def test_expand_jpg(self):
        result = FilterSidebar._expand_extensions([".jpg"])
        assert result == [".jpg", ".jpeg"]

    def test_expand_heic(self):
        result = FilterSidebar._expand_extensions([".heic"])
        assert result == [".heic", ".heif"]

    def test_expand_both(self):
        result = FilterSidebar._expand_extensions([".jpg", ".heic"])
        assert result == [".jpg", ".jpeg", ".heic", ".heif"]

    def test_expand_unknown_passthrough(self):
        result = FilterSidebar._expand_extensions([".png"])
        assert result == [".png"]

    def test_expand_empty(self):
        result = FilterSidebar._expand_extensions([])
        assert result == []


# ---------------------------------------------------------------------------
# FilterSidebar widget (requires QApplication / qtbot)
# ---------------------------------------------------------------------------

class TestFilterSidebarWidget:
    """Tests for the FilterSidebar widget behaviour."""

    def test_initial_criteria_defaults(self, qtbot):
        """Widget starts with default criteria (no date filter, all types, min 2)."""
        sidebar = FilterSidebar()
        qtbot.addWidget(sidebar)

        criteria = sidebar.current_criteria()
        assert criteria.date_from is None  # date filter disabled by default
        assert criteria.date_to is None
        assert criteria.extensions is None  # all types checked = None
        assert criteria.min_copies == 2
        assert criteria.full_dupe_folders_only is False
        assert criteria.sort_by == "waste"

    def test_apply_emits_signal(self, qtbot):
        """Clicking Apply emits filters_changed with the current criteria."""
        sidebar = FilterSidebar()
        qtbot.addWidget(sidebar)

        received = []
        sidebar.filters_changed.connect(lambda c: received.append(c))

        sidebar._apply_btn.click()

        assert len(received) == 1
        assert isinstance(received[0], FilterCriteria)

    def test_reset_restores_defaults(self, qtbot):
        """Clicking Reset restores all controls to their default state."""
        sidebar = FilterSidebar()
        qtbot.addWidget(sidebar)

        # Change some values
        sidebar._min_copies.setValue(5)
        sidebar._full_dupe_only.setChecked(True)
        sidebar._sort_combo.setCurrentIndex(1)
        for _, cb in sidebar._type_checks:
            cb.setChecked(False)

        # Capture the signal from reset
        received = []
        sidebar.filters_changed.connect(lambda c: received.append(c))

        sidebar._reset_btn.click()

        # Verify values are back to defaults
        assert sidebar._min_copies.value() == 2
        assert sidebar._full_dupe_only.isChecked() is False
        assert sidebar._sort_combo.currentIndex() == 0

        # Reset emits the signal too
        assert len(received) == 1
        criteria = received[0]
        assert criteria.min_copies == 2
        assert criteria.extensions is None  # all types re-checked
        assert criteria.sort_by == "waste"

    def test_min_copies_range(self, qtbot):
        """Spin box enforces min=2, max=100."""
        sidebar = FilterSidebar()
        qtbot.addWidget(sidebar)

        assert sidebar._min_copies.minimum() == 2
        assert sidebar._min_copies.maximum() == 100

    def test_unchecked_type_produces_extensions(self, qtbot):
        """Unchecking one file type should produce a list of extensions."""
        sidebar = FilterSidebar()
        qtbot.addWidget(sidebar)

        # Uncheck HEIC, keep JPG
        for ext, cb in sidebar._type_checks:
            if ext == ".heic":
                cb.setChecked(False)

        criteria = sidebar.current_criteria()
        assert criteria.extensions is not None
        assert ".jpg" in criteria.extensions
        assert ".jpeg" in criteria.extensions
        assert ".heic" not in criteria.extensions
