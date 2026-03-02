"""
ui/filter_sidebar.py — Collapsible filtering sidebar for Advanced Cleanup.

Provides date range, file type, redundancy level, and sort controls.
Emits ``filters_changed(FilterCriteria)`` when the user clicks Apply.

UX Redesign Phase 5 — Advanced Cleanup.
"""

from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import QDate, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Filter criteria dataclass
# ---------------------------------------------------------------------------

@dataclass
class FilterCriteria:
    """Describes the active filter state.  Passed to DB queries and models."""

    date_from: str | None = None  # ISO8601 (inclusive)
    date_to: str | None = None  # ISO8601 (inclusive)
    extensions: list[str] | None = None  # ['.jpg', '.heic'] or None for all
    min_copies: int = 2
    full_dupe_folders_only: bool = False
    search_text: str | None = None  # set by the search bar, not the sidebar
    sort_by: str = "waste"  # 'waste' | 'copies' | 'path_length'
    sort_descending: bool = True


# ---------------------------------------------------------------------------
# Sidebar widget
# ---------------------------------------------------------------------------

# File types to offer (matches scanner._IMAGE_EXTENSIONS).
_FILE_TYPES = [
    (".jpg", "JPEG (.jpg/.jpeg)"),
    (".heic", "HEIC (.heic/.heif)"),
]


class FilterSidebar(QWidget):
    """Collapsible filter panel for the cleanup screen."""

    filters_changed = pyqtSignal(object)  # FilterCriteria

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()

    # ── Build ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Title
        title = QLabel(self.tr("\u2699 Filters"))
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # ── Date Range ────────────────────────────────────────────────
        date_group = QGroupBox(self.tr("Date Range"))
        date_layout = QVBoxLayout(date_group)

        from_row = QHBoxLayout()
        from_row.addWidget(QLabel(self.tr("From:")))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setSpecialValueText(self.tr("Any"))
        self._date_from.setDate(QDate(2000, 1, 1))
        self._date_from.setMinimumDate(QDate(2000, 1, 1))
        from_row.addWidget(self._date_from)
        date_layout.addLayout(from_row)

        to_row = QHBoxLayout()
        to_row.addWidget(QLabel(self.tr("To:")))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setSpecialValueText(self.tr("Any"))
        self._date_to.setDate(QDate.currentDate())
        to_row.addWidget(self._date_to)
        date_layout.addLayout(to_row)

        self._date_enabled = QCheckBox(self.tr("Enable date filter"))
        date_layout.addWidget(self._date_enabled)
        layout.addWidget(date_group)

        # ── File Type ─────────────────────────────────────────────────
        type_group = QGroupBox(self.tr("File Type"))
        type_layout = QVBoxLayout(type_group)
        self._type_checks: list[tuple[str, QCheckBox]] = []
        for ext, label in _FILE_TYPES:
            cb = QCheckBox(label)
            cb.setChecked(True)
            type_layout.addWidget(cb)
            self._type_checks.append((ext, cb))
        layout.addWidget(type_group)

        # ── Redundancy Level ──────────────────────────────────────────
        copies_group = QGroupBox(self.tr("Redundancy"))
        copies_layout = QHBoxLayout(copies_group)
        copies_layout.addWidget(QLabel(self.tr("Min copies:")))
        self._min_copies = QSpinBox()
        self._min_copies.setMinimum(2)
        self._min_copies.setMaximum(100)
        self._min_copies.setValue(2)
        copies_layout.addWidget(self._min_copies)
        layout.addWidget(copies_group)

        # ── Full Dupe Folders Only ────────────────────────────────────
        self._full_dupe_only = QCheckBox(self.tr("Full duplicate folders only"))
        self._full_dupe_only.setToolTip(
            self.tr("Show only folders where every file is a duplicate")
        )
        layout.addWidget(self._full_dupe_only)

        # ── Sort ──────────────────────────────────────────────────────
        sort_group = QGroupBox(self.tr("Sort By"))
        sort_layout = QVBoxLayout(sort_group)
        self._sort_combo = QComboBox()
        self._sort_combo.addItem(self.tr("Waste (total size)"), "waste")
        self._sort_combo.addItem(self.tr("Number of copies"), "copies")
        self._sort_combo.addItem(self.tr("Path length"), "path_length")
        sort_layout.addWidget(self._sort_combo)
        layout.addWidget(sort_group)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton(self.tr("Apply"))
        self._apply_btn.setDefault(True)
        self._reset_btn = QPushButton(self.tr("Reset"))
        btn_row.addWidget(self._apply_btn)
        btn_row.addWidget(self._reset_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

        self.setMinimumWidth(180)
        self.setMaximumWidth(260)
        self.setStyleSheet("FilterSidebar { border-right: 1px solid #d1d5db; }")

    def _connect_signals(self) -> None:
        self._apply_btn.clicked.connect(self._on_apply)
        self._reset_btn.clicked.connect(self._on_reset)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_apply(self) -> None:
        criteria = self.current_criteria()
        self.filters_changed.emit(criteria)

    def _on_reset(self) -> None:
        self._date_enabled.setChecked(False)
        self._date_from.setDate(QDate(2000, 1, 1))
        self._date_to.setDate(QDate.currentDate())
        for _, cb in self._type_checks:
            cb.setChecked(True)
        self._min_copies.setValue(2)
        self._full_dupe_only.setChecked(False)
        self._sort_combo.setCurrentIndex(0)

        criteria = self.current_criteria()
        self.filters_changed.emit(criteria)

    # ── Public ────────────────────────────────────────────────────────

    def current_criteria(self) -> FilterCriteria:
        """Build a FilterCriteria from the current widget state."""
        date_from = None
        date_to = None
        if self._date_enabled.isChecked():
            date_from = self._date_from.date().toString(Qt.DateFormat.ISODate)
            date_to = self._date_to.date().toString(Qt.DateFormat.ISODate)

        # Extensions: only include checked types.  None = all types.
        checked_exts = [ext for ext, cb in self._type_checks if cb.isChecked()]
        all_checked = all(cb.isChecked() for _, cb in self._type_checks)
        extensions = None if all_checked else self._expand_extensions(checked_exts)

        return FilterCriteria(
            date_from=date_from,
            date_to=date_to,
            extensions=extensions,
            min_copies=self._min_copies.value(),
            full_dupe_folders_only=self._full_dupe_only.isChecked(),
            sort_by=self._sort_combo.currentData() or "waste",
            sort_descending=True,
        )

    @staticmethod
    def _expand_extensions(exts: list[str]) -> list[str]:
        """Expand shorthand extensions into all variants (e.g. .jpg → [.jpg, .jpeg])."""
        mapping = {
            ".jpg": [".jpg", ".jpeg"],
            ".heic": [".heic", ".heif"],
        }
        result = []
        for ext in exts:
            result.extend(mapping.get(ext, [ext]))
        return result
