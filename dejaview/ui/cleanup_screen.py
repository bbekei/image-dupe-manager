"""
ui/cleanup_screen.py — Self-contained cleanup workflow screen.

Absorbs the FolderPanel + ResultsPanel + scan flow that previously
lived directly inside MainWindow.  Owns the internal QSplitter and
all panel-swap logic (scan progress, compare view, planning panel).

This widget is registered as the "cleanup" screen in the
NavigationController and is shown when the user clicks the
"Local Duplicates" card on the Dashboard or starts a new scan.

Signals bubble up to MainWindow for status bar and menu updates.
"""

import logging
import os

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QMessageBox, QSplitter, QVBoxLayout, QWidget

from data.db import Database
from ui.batch_actions import BatchActions
from ui.compare_view import CompareView, FolderCompareView
from ui.filter_sidebar import FilterSidebar
from ui.folder_panel import FolderPanel
from ui.planning_panel import PlanningPanel
from ui.results_model import ResultsTreeModel
from ui.results_panel import ResultsPanel
from ui.scan_progress import ScanProgressWidget
from ui.workflow import WorkflowPhase

log = logging.getLogger(__name__)


class CleanupScreen(QWidget):
    """Container for the local-cleanup workflow (scan → results → plan).

    Signals:
        status_message(str):        request to show text in the status bar
        workflow_phase_changed(int): emitted when the internal phase changes
        plan_action_availability(bool): whether Plan Actions should be enabled
        review_requested():         user clicked "Review Plan" in planning panel
    """

    status_message = pyqtSignal(str)
    workflow_phase_changed = pyqtSignal(int)
    plan_action_availability = pyqtSignal(bool)
    review_requested = pyqtSignal()

    def __init__(
        self,
        db: Database,
        tree_model: ResultsTreeModel,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._tree_model = tree_model
        self._session_id: int | None = None
        self._perf_monitor = None

        # Swappable sub-panels (only one at a time in the right pane)
        self._compare_view: CompareView | None = None
        self._scan_progress: ScanProgressWidget | None = None
        self._planning_panel: PlanningPanel | None = None
        self._filter_sidebar: FilterSidebar | None = None
        self._batch_actions: BatchActions | None = None
        self._workflow_phase = WorkflowPhase.DISCOVERY

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top: folder panel as compact horizontal bar (full width).
        self._folder_panel = FolderPanel(db=self._db, parent=self)
        layout.addWidget(self._folder_panel)

        # Main area: splitter with FilterSidebar + right_container.
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left in splitter: Filter sidebar (collapsible, initially hidden).
        self._filter_sidebar = FilterSidebar(parent=self)
        self._filter_sidebar.filters_changed.connect(self._on_filters_changed)
        self._filter_sidebar.setVisible(False)
        self._splitter.addWidget(self._filter_sidebar)

        # Right in splitter: container with BatchActions toolbar + ResultsPanel.
        self._right_container = QWidget(self)
        right_layout = QVBoxLayout(self._right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._batch_actions = BatchActions(parent=self._right_container)
        self._batch_actions.preset_applied.connect(self._on_preset_applied)
        right_layout.addWidget(self._batch_actions)

        self._results_panel = ResultsPanel(
            db=self._db, parent=self._right_container, tree_model=self._tree_model
        )
        self._results_panel.setObjectName("results_panel")
        right_layout.addWidget(self._results_panel)

        self._splitter.addWidget(self._right_container)

        self._splitter.setStretchFactor(0, 0)  # sidebar: fixed width
        self._splitter.setStretchFactor(1, 1)  # right_container: stretch
        self._splitter.setStyleSheet(
            "QSplitter::handle { background: #d1d5db; width: 1px; }"
        )

        layout.addWidget(self._splitter)

        # Wire ResultsPanel signals
        self._results_panel.compare_view_requested.connect(
            self._on_compare_requested
        )
        self._results_panel.compare_folder_requested.connect(
            self._on_compare_folder_requested
        )

    # ── Public API (used by MainWindow) ───────────────────────────────

    @property
    def folder_panel(self) -> FolderPanel:
        return self._folder_panel

    @property
    def results_panel(self) -> ResultsPanel:
        return self._results_panel

    @property
    def workflow_phase(self) -> WorkflowPhase:
        return self._workflow_phase

    def set_session_id(self, session_id: int | None) -> None:
        self._session_id = session_id
        self._folder_panel.set_session_id(session_id)
        self._results_panel.set_session_id(session_id)
        if self._batch_actions and session_id is not None:
            self._batch_actions.set_context(self._db, session_id)

    def set_perf_monitor(self, perf_monitor) -> None:
        self._perf_monitor = perf_monitor
        self._results_panel._perf = perf_monitor

    # ── Scan progress panel swap ──────────────────────────────────────

    def show_scan_progress(self) -> None:
        """Hide results tree, show centered progress widget in right container."""
        if self._scan_progress is None:
            self._scan_progress = ScanProgressWidget(parent=self._right_container)
        self._results_panel.hide()
        self._right_container.layout().addWidget(self._scan_progress)
        self._scan_progress.show()

    def hide_scan_progress(self) -> None:
        """Hide progress widget, restore results tree."""
        if self._scan_progress is not None:
            self._scan_progress.hide()
            self._scan_progress.deleteLater()
            self._scan_progress = None
        self._results_panel.show()

    @property
    def scan_progress_widget(self) -> ScanProgressWidget | None:
        return self._scan_progress

    # ── Compare view lifecycle ────────────────────────────────────────

    @pyqtSlot(str)
    def _on_compare_requested(self, pixel_hash: str) -> None:
        """Open the CompareView for a duplicate group."""
        if self._session_id is None:
            return
        session_folders = self._db.get_session_folders(self._session_id)
        self._compare_view = CompareView(
            db=self._db,
            session_id=self._session_id,
            pixel_hash=pixel_hash,
            session_folders=session_folders,
            parent=self._right_container,
        )
        self._compare_view.setObjectName("compare_view")
        self._compare_view.closed.connect(self._close_compare_view)
        # Swap: hide current right pane content, show compare view
        self._get_active_right_pane().hide()
        self._right_container.layout().addWidget(self._compare_view)
        self.status_message.emit(
            self.tr("Comparing duplicate group (SHA: {0}\u2026)").format(
                pixel_hash[:8]
            )
        )

    @pyqtSlot(str)
    def _on_compare_folder_requested(self, folder_path: str) -> None:
        """Open the FolderCompareView for a fully-duplicated folder."""
        if self._session_id is None:
            return
        self._compare_view = FolderCompareView(
            db=self._db,
            session_id=self._session_id,
            folder_path=folder_path,
            parent=self._right_container,
        )
        self._compare_view.setObjectName("compare_view")
        self._compare_view.closed.connect(self._close_compare_view)
        self._get_active_right_pane().hide()
        self._right_container.layout().addWidget(self._compare_view)
        self.status_message.emit(
            self.tr("Comparing duplicated folder: {0}").format(
                os.path.basename(folder_path)
            )
        )

    @pyqtSlot()
    def _close_compare_view(self) -> None:
        """Close the CompareView and restore the previous right pane."""
        if self._compare_view is not None:
            self._compare_view.hide()
            self._compare_view.deleteLater()
            self._compare_view = None
        self._get_active_right_pane().show()
        self._results_panel.reload()
        self.status_message.emit(self.tr("Ready."))

    # ── Planning panel lifecycle ──────────────────────────────────────

    def show_planning_panel(self) -> None:
        """Hide results tree, show planning panel in the right container."""
        if self._planning_panel is not None:
            return
        self._planning_panel = PlanningPanel(
            db=self._db,
            session_id=self._session_id,
            tree_model=self._tree_model,
            parent=self._right_container,
        )
        self._planning_panel.setObjectName("planning_panel")
        self._planning_panel.closed.connect(self._hide_planning_panel)
        self._planning_panel.compare_view_requested.connect(
            self._on_compare_requested
        )
        self._planning_panel.review_requested.connect(
            self.review_requested
        )
        self._results_panel.hide()
        self._right_container.layout().addWidget(self._planning_panel)
        self._planning_panel.show()
        self._workflow_phase = WorkflowPhase.PLANNING
        self.workflow_phase_changed.emit(self._workflow_phase.value)
        self.status_message.emit(
            self.tr("Planning mode \u2014 mark duplicates with actions.")
        )

    @pyqtSlot()
    def _hide_planning_panel(self) -> None:
        """Hide planning panel, restore results tree."""
        if self._planning_panel is not None:
            self._planning_panel.hide()
            self._planning_panel.deleteLater()
            self._planning_panel = None
        self._results_panel.show()
        self._results_panel.reload()
        self._workflow_phase = WorkflowPhase.DISCOVERY
        self.workflow_phase_changed.emit(self._workflow_phase.value)
        self.status_message.emit(self.tr("Ready."))

    # ── Phase 5: Filter sidebar + Batch actions ─────────────────────────

    @property
    def filter_sidebar(self) -> FilterSidebar | None:
        return self._filter_sidebar

    @property
    def batch_actions(self) -> BatchActions | None:
        return self._batch_actions

    def toggle_filter_sidebar(self) -> None:
        """Show/hide the filter sidebar panel."""
        if self._filter_sidebar is not None:
            visible = not self._filter_sidebar.isVisible()
            self._filter_sidebar.setVisible(visible)

    @pyqtSlot(object)
    def _on_filters_changed(self, criteria) -> None:
        """Apply filter criteria from the sidebar to the results panel."""
        self._results_panel.apply_filter_criteria(criteria)

    @pyqtSlot(int, int)
    def _on_preset_applied(self, keep_count: int, delete_count: int) -> None:
        """After smart select or pattern match, refresh views and offer plan review."""
        self.status_message.emit(
            self.tr("Smart select: {0} kept, {1} marked for deletion").format(
                keep_count, delete_count
            )
        )
        self._results_panel.reload()

        if delete_count > 0:
            reply = QMessageBox.question(
                self,
                self.tr("Smart Select Complete"),
                self.tr(
                    "{0} files kept, {1} marked for deletion.\n\n"
                    "Would you like to review the plan?"
                ).format(keep_count, delete_count),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.review_requested.emit()

    # ── Helpers ────────────────────────────────────────────────────────

    def _get_active_right_pane(self) -> QWidget:
        """Return whichever right-pane widget is currently visible."""
        if self._planning_panel is not None and self._planning_panel.isVisible():
            return self._planning_panel
        return self._results_panel

