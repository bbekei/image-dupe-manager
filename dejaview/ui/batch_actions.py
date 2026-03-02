"""
ui/batch_actions.py — Batch selection toolbar for Advanced Cleanup.

Provides "Smart Select" (preset picker) and "Select by Pattern" (glob dialog)
actions for bulk-marking files across duplicate clusters.

UX Redesign Phase 5 — Advanced Cleanup.
"""

import fnmatch
import os
from datetime import datetime, timezone
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QWidget,
)

from core.selection import SelectionPreset, apply_preset
from data.db import Database


class BatchActions(QWidget):
    """Toolbar with Smart Select and Select by Pattern buttons."""

    # Emitted after a preset or pattern is applied: (keep_count, delete_count)
    preset_applied = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db: Optional[Database] = None
        self._session_id: Optional[int] = None
        self._filter_hashes: Optional[list[str]] = None  # scope from current filter
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        self.setStyleSheet("BatchActions { border-bottom: 1px solid #e5e7eb; }")

        self._smart_btn = QPushButton(self.tr("\u2728 Smart Select"))
        self._smart_btn.setToolTip(
            self.tr("Apply a selection preset to all duplicate groups")
        )
        self._smart_btn.clicked.connect(self._on_smart_select)
        layout.addWidget(self._smart_btn)

        self._pattern_btn = QPushButton(self.tr("\u2731 Select by Pattern"))
        self._pattern_btn.setToolTip(
            self.tr("Mark files matching a pattern for deletion")
        )
        self._pattern_btn.clicked.connect(self._on_select_by_pattern)
        layout.addWidget(self._pattern_btn)

        layout.addStretch()

        self.setEnabled(False)

    # ── Public setters ────────────────────────────────────────────────

    def set_context(
        self,
        db: Database,
        session_id: int,
        filter_hashes: Optional[list[str]] = None,
    ) -> None:
        """Set the database context for batch operations."""
        self._db = db
        self._session_id = session_id
        self._filter_hashes = filter_hashes
        self.setEnabled(db is not None and session_id is not None)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_smart_select(self) -> None:
        if not self._db or self._session_id is None:
            return

        presets = [
            (self.tr("Keep Largest File"), SelectionPreset.KEEP_LARGEST_FILE),
            (self.tr("Keep Newest"), SelectionPreset.KEEP_NEWEST),
            (self.tr("Keep Deepest Path"), SelectionPreset.KEEP_DEEPEST_PATH),
            (self.tr("Keep Shortest Path"), SelectionPreset.KEEP_SHORTEST_PATH),
        ]

        labels = [p[0] for p in presets]
        choice, ok = QInputDialog.getItem(
            self,
            self.tr("Smart Select"),
            self.tr("Choose a selection rule:"),
            labels,
            0,
            False,
        )
        if not ok:
            return

        idx = labels.index(choice)
        preset = presets[idx][1]

        # Confirmation
        reply = QMessageBox.question(
            self,
            self.tr("Confirm Smart Select"),
            self.tr(
                "Apply \"{0}\" to all duplicate groups?\n\n"
                "This will mark files for keep/delete.\n"
                "Existing decisions will be overwritten."
            ).format(choice),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        keep, delete = apply_preset(
            self._db,
            self._session_id,
            preset,
            pixel_hashes=self._filter_hashes,
        )
        self.preset_applied.emit(keep, delete)

    def _on_select_by_pattern(self) -> None:
        if not self._db or self._session_id is None:
            return

        pattern, ok = QInputDialog.getText(
            self,
            self.tr("Select by Pattern"),
            self.tr(
                "Enter a filename pattern (e.g. *_copy*, *(1)*):\n"
                "Files matching this pattern will be marked for deletion."
            ),
        )
        if not ok or not pattern.strip():
            return

        pattern = pattern.strip()

        # Get all duplicate files
        groups = self._db.get_all_duplicate_file_ids(self._session_id)
        now = datetime.now(timezone.utc).isoformat()
        batch: list[tuple[int, int, str, str, str | None]] = []
        delete_count = 0

        for pixel_hash, file_ids in groups.items():
            if len(file_ids) < 2:
                continue
            # Get file paths
            files = self._db.get_cluster_files(self._session_id, pixel_hash)
            file_dicts = [dict(f) for f in files]

            for f in file_dicts:
                filename = os.path.basename(f["path"])
                if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                    # Safety: never delete the last copy
                    other_non_delete = sum(
                        1 for o in file_dicts
                        if o["id"] != f["id"]
                    )
                    if other_non_delete > 0:
                        batch.append((
                            self._session_id, f["id"], "delete", "file", now
                        ))
                        delete_count += 1

        if batch:
            self._db.set_file_actions_batch(batch)
            self.preset_applied.emit(0, delete_count)
        else:
            QMessageBox.information(
                self,
                self.tr("No Matches"),
                self.tr("No duplicate files matched the pattern \"{0}\".").format(
                    pattern
                ),
            )
