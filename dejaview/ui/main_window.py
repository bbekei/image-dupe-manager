"""
ui/main_window.py — DejaView application shell.

Layout (after UX Redesign Phases 1-3):
  Menu bar   : File | Scan | Share | Help
  Central    : QStackedWidget managed by NavigationController
               - "dashboard":  Dashboard (home view with status cards)
               - "cleanup":    CleanupScreen (folder panel + results + planning)
               - "plan_review": PlanReviewScreen (safety gate)
               - "execution":  ExecutionScreen (progress + log)
  Bottom bar : ScanControl (visible only on cleanup screen)
  Status bar : one-line status messages

The scan lifecycle, export/import, sync, settings and help logic remain
in MainWindow.  Panel-swap logic (scan progress, compare view, planning)
is delegated to CleanupScreen.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.executor import PlanExecutor
from core.scanner import Scanner
from data.db import Database
from data.export import build_export_payload, import_payload, validate_username
from data.sync import DriveSync
from ui.cleanup_screen import CleanupScreen
from ui.dashboard import Dashboard
from ui.execution_screen import ExecutionScreen
from ui.family_discovery import FamilyDiscoveryScreen
from ui.help_dialog import HelpDialog
from ui.navigation import NavigationController
from ui.plan_review import PlanReviewScreen
from ui.results_model import ResultsTreeModel
from ui.results_panel import FILTER_DUPLICATES_ONLY
from ui.scan_control import ScanControl
from ui.share_dialog import ShareDialog
from ui.tray import TrayIcon
from ui.workflow import WorkflowPhase

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Top-level window.  Owns the session lifecycle: create / restore sessions,
    wire FolderPanel to ScanControl via the Scanner QThread.

    Navigation is managed by a NavigationController wrapping a QStackedWidget.
    The Dashboard is the default home screen; the cleanup workflow is a
    separate screen reached via the "Local Duplicates" card or "Start Scan".
    """

    def __init__(
        self,
        db: Database,
        thumb_dir: Path,
        drive_sync: DriveSync | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._thumb_dir = thumb_dir
        self._drive_sync = drive_sync
        self._perf_monitor = None
        self._scanner: Scanner | None = None
        self._executor: PlanExecutor | None = None
        self._session_id: int | None = None
        self._sync_worker: _SyncWorker | None = None
        self._auth_worker: "_AuthWorker | None" = None
        self._share_dialog: ShareDialog | None = None
        self._tree_model = ResultsTreeModel()
        self._trash_root = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        ) / "DejaView" / ".dejaview_trash"

        self.setWindowTitle(self.tr("DejaView"))
        self.setMinimumSize(900, 600)

        self._build_menu()
        self._build_central()
        self._build_status_bar()
        self._restore_session()

    def set_perf_monitor(self, perf_monitor) -> None:
        """Attach a PerformanceMonitor for scan telemetry (None = disabled)."""
        self._perf_monitor = perf_monitor
        self._cleanup_screen.set_perf_monitor(perf_monitor)

    # ── Convenience properties (delegate to CleanupScreen) ────────────

    @property
    def _folder_panel(self):
        return self._cleanup_screen.folder_panel

    @property
    def _results_panel(self):
        return self._cleanup_screen.results_panel

    # ── UI construction ──────────────────────────────────────────────────

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu(self.tr("File"))
        file_menu.addAction(self.tr("Add Folder\u2026"), self._on_add_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.tr("Settings\u2026"), self._on_settings)
        file_menu.addSeparator()
        file_menu.addAction(self.tr("Exit"), self.close)

        # Scan
        scan_menu = mb.addMenu(self.tr("Scan"))
        scan_menu.addAction(self.tr("Start Scan"), self._on_start)
        scan_menu.addAction(self.tr("Pause"), self._on_pause)
        scan_menu.addAction(self.tr("Stop"), self._on_stop)
        scan_menu.addSeparator()
        self._plan_action = scan_menu.addAction(
            self.tr("Plan Actions\u2026"), self._on_plan_actions
        )
        self._plan_action.setEnabled(False)

        # Share (plan §Workflow 6 — manual export/import)
        share_menu = mb.addMenu(self.tr("Share"))
        share_menu.addAction(
            self.tr("Export Scan Results\u2026"), self._on_export
        )
        share_menu.addAction(
            self.tr("Import Scan Results\u2026"), self._on_import
        )
        share_menu.addSeparator()
        share_menu.addAction(
            self.tr("Configure Sync\u2026"), self._on_configure_sync
        )
        share_menu.addAction(
            self.tr("Manage Synced Libraries\u2026"), self._on_manage_peers
        )

        # Help (Feature Request 1 — Help Menu)
        help_menu = mb.addMenu(self.tr("Help"))
        help_menu.addAction(self.tr("User Guide\u2026"), self._on_user_guide)

    def _build_central(self) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget holds all screens
        self._stacked = QStackedWidget(container)
        layout.addWidget(self._stacked, stretch=1)

        # Navigation controller
        self._nav = NavigationController(self._stacked, parent=self)
        self._nav.screen_changed.connect(self._on_screen_changed)

        # Dashboard screen
        self._dashboard = Dashboard(db=self._db, parent=self)
        self._dashboard.duplicate_card_clicked.connect(self._navigate_to_cleanup)
        self._dashboard.family_card_clicked.connect(self._on_family_card_clicked)
        self._dashboard.request_card_clicked.connect(self._on_request_card_clicked)
        self._dashboard.scan_requested.connect(self._on_dashboard_scan)
        self._dashboard.sync_requested.connect(self._on_sync_now)
        self._nav.register_screen("dashboard", self._dashboard)

        # Cleanup screen (absorbs old FolderPanel + ResultsPanel + panel swaps)
        self._cleanup_screen = CleanupScreen(
            db=self._db, tree_model=self._tree_model, parent=self
        )
        self._cleanup_screen.status_message.connect(self._status_bar_message)
        self._cleanup_screen.review_requested.connect(self._on_review_requested)
        self._nav.register_screen("cleanup", self._cleanup_screen)

        # Plan Review screen (Phase 2 — safety gate before file operations)
        self._plan_review = PlanReviewScreen(db=self._db, parent=self)
        self._plan_review.back_requested.connect(self._on_review_back)
        self._plan_review.commit_requested.connect(self._on_commit_requested)
        self._plan_review.clear_requested.connect(self._on_plan_cleared)
        self._nav.register_screen("plan_review", self._plan_review)

        # Execution screen (Phase 3 — progress + log during file operations)
        self._execution_screen = ExecutionScreen(parent=self)
        self._execution_screen.done_requested.connect(self._on_execution_done)
        self._execution_screen.minimize_requested.connect(self._on_minimize_to_tray)
        self._nav.register_screen("execution", self._execution_screen)

        # Family Discovery screen (Phase 4 — browse & request family photos)
        self._family_discovery = FamilyDiscoveryScreen(
            db=self._db, parent=self
        )
        self._family_discovery.back_requested.connect(
            self._on_family_discovery_back
        )
        self._family_discovery.requests_changed.connect(
            self._on_requests_changed
        )
        self._nav.register_screen("family_discovery", self._family_discovery)

        # System tray icon (Phase 3 — minimized execution)
        self._tray = TrayIcon(parent=self)
        self._tray.activated.connect(self._on_tray_activated)

        # Scan control (bottom bar) — visible only on cleanup screen
        self._scan_control = ScanControl(parent=self)
        layout.addWidget(self._scan_control, stretch=0)

        self.setCentralWidget(container)

        # Wire scan control buttons
        self._scan_control.start_requested.connect(self._on_start)
        self._scan_control.pause_requested.connect(self._on_pause)
        self._scan_control.stop_requested.connect(self._on_stop)

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(self.tr("Welcome to DejaView."))

    # ── Navigation ─────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _on_screen_changed(self, screen_name: str) -> None:
        """Adapt the UI when the active screen changes."""
        self._scan_control.setVisible(screen_name == "cleanup")

    @pyqtSlot()
    def _navigate_to_cleanup(self) -> None:
        """Navigate from Dashboard to the cleanup screen."""
        self._nav.navigate_to("cleanup")

    @pyqtSlot()
    def _on_family_card_clicked(self) -> None:
        """Navigate to the Family Discovery screen (Phase 4)."""
        self._nav.navigate_to("family_discovery")

    @pyqtSlot()
    def _on_family_discovery_back(self) -> None:
        """Family Discovery > Back — return to dashboard."""
        self._nav.go_back()

    @pyqtSlot()
    def _on_requests_changed(self) -> None:
        """Refresh dashboard and plan review when requests change."""
        self._dashboard.refresh()

    @pyqtSlot()
    def _on_request_card_clicked(self) -> None:
        """Placeholder for Phase 6 — Request Approval screen."""
        self._status_bar.showMessage(
            self.tr("Request Approval — coming soon.")
        )

    @pyqtSlot()
    def _on_dashboard_scan(self) -> None:
        """Dashboard 'Start New Scan' — navigate to cleanup, then start."""
        self._nav.navigate_to("cleanup")
        # Small delay is not needed — _on_start checks folders itself.
        self._on_start()

    @pyqtSlot(str)
    def _status_bar_message(self, message: str) -> None:
        """Relay status messages from child screens to the status bar."""
        self._status_bar.showMessage(message)

    # ── Session management ───────────────────────────────────────────────

    def _restore_session(self) -> None:
        """
        On startup, restore the most recent session if it has useful state.
        Handles in_progress, paused, complete, and stopped sessions.
        """
        session = self._db.get_latest_session()
        if not session:
            # No previous session — start on dashboard
            self._nav.navigate_to("dashboard", push_back=False)
            return

        status = session["status"]
        if status not in ("in_progress", "paused", "complete", "stopped"):
            self._nav.navigate_to("dashboard", push_back=False)
            return

        self._session_id = session["id"]
        self._cleanup_screen.set_session_id(self._session_id)
        self._dashboard.set_session_id(self._session_id)
        self._plan_review.set_session_id(self._session_id)
        self._family_discovery.set_session_id(self._session_id)
        for folder in self._db.get_session_folders(self._session_id):
            self._folder_panel.add_folder(folder, persist=False)

        # Enable Plan Actions if the session has duplicate groups.
        dup_groups = self._db.get_duplicate_groups(self._session_id)
        self._plan_action.setEnabled(len(dup_groups) > 0)

        if status == "paused":
            # Resume directly on cleanup screen
            self._nav.navigate_to("cleanup", push_back=False)
            self._scan_control.set_state_paused()
            self._status_bar.showMessage(
                self.tr("Scan paused. Click Resume to continue.")
            )
        elif status == "complete":
            # Start on dashboard — user can navigate to cleanup if they want
            self._nav.navigate_to("dashboard", push_back=False)
            self._scan_control.set_state_complete()
            files = self._db.get_files_for_session(self._session_id)
            total_files = sum(1 for f in files if f["status"] == "active")
            if len(dup_groups) > 0:
                self._results_panel.set_filter(FILTER_DUPLICATES_ONLY)
                dup_file_count = sum(g["file_count"] for g in dup_groups)
                self._status_bar.showMessage(
                    self.tr(
                        "Last scan: {0} files, {1} duplicates in {2} groups."
                    ).format(total_files, dup_file_count, len(dup_groups))
                )
            else:
                self._status_bar.showMessage(
                    self.tr(
                        "Last scan: {0} files scanned. No duplicates found."
                    ).format(total_files)
                )
        else:
            # in_progress or stopped — go to dashboard
            self._nav.navigate_to("dashboard", push_back=False)

    def _get_or_create_session(self) -> int:
        """
        Return the current session_id, creating a new one if none exists.
        Persists all folders currently shown in the panel to the new session.
        """
        if self._session_id is None:
            now = datetime.now(timezone.utc).isoformat()
            self._session_id = self._db.create_session(
                name=self.tr("Scan {0}").format(now[:10]),
                created_at=now,
            )
            self._cleanup_screen.set_session_id(self._session_id)
            self._dashboard.set_session_id(self._session_id)
            self._plan_review.set_session_id(self._session_id)
            self._family_discovery.set_session_id(self._session_id)
            for folder in self._folder_panel.folders():
                self._db.add_session_folder(self._session_id, folder)
        return self._session_id

    # ── Scan control slots ───────────────────────────────────────────────

    @pyqtSlot()
    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Select Folder to Scan")
        )
        if folder:
            # Make sure we're on the cleanup screen
            if self._nav.current_screen() != "cleanup":
                self._nav.navigate_to("cleanup")
            self._folder_panel.add_folder(folder)

    @pyqtSlot()
    def _on_start(self) -> None:
        if self._scanner and self._scanner.isRunning():
            return

        # Ensure we're on the cleanup screen
        if self._nav.current_screen() != "cleanup":
            self._nav.navigate_to("cleanup")

        if not self._folder_panel.folders():
            self._status_bar.showMessage(self.tr("Add folders to get started."))
            return

        # Detect whether this is a resume of a paused session.
        session = self._db.get_latest_session()
        is_resume = (
            self._session_id is not None
            and session is not None
            and session["id"] == self._session_id
            and session["status"] == "paused"
        )

        session_id = self._get_or_create_session()

        # Create a fresh PerformanceMonitor per scan if enabled.
        perf = self._perf_monitor
        if perf is None and self._db.get_perf_logging():
            from core.perf_monitor import PerformanceMonitor
            app_dir = Path(os.environ.get(
                "APPDATA", Path.home() / "AppData" / "Roaming"
            )) / "DejaView"
            perf = PerformanceMonitor(output_dir=app_dir, enabled=True)
            self._perf_monitor = perf
            self._cleanup_screen.set_perf_monitor(perf)
            log.info("Performance telemetry enabled via settings")

        self._scanner = Scanner(
            db=self._db,
            session_id=session_id,
            thumb_dir=self._thumb_dir,
            parent=self,
            perf_monitor=perf,
        )
        if is_resume:
            self._scanner.set_resuming(True)
        # Show progress view, hide results tree.
        self._cleanup_screen.show_scan_progress()
        self._wire_scanner(self._scanner)
        self._scanner.start()

    @pyqtSlot()
    def _on_pause(self) -> None:
        if self._scanner and self._scanner.isRunning():
            self._scanner.pause()

    @pyqtSlot()
    def _on_stop(self) -> None:
        if self._scanner and self._scanner.isRunning():
            self._scanner.stop()
            self._scanner.wait(5000)

    def _wire_scanner(self, scanner: Scanner) -> None:
        # ScanControl (bottom bar): buttons + progress bar + ETA.
        scanner.scan_started.connect(self._scan_control.on_scan_started)
        scanner.scan_paused.connect(self._scan_control.on_scan_paused)
        scanner.scan_resumed.connect(self._scan_control.on_scan_resumed)
        scanner.scan_stopped.connect(self._scan_control.on_scan_stopped)
        scanner.scan_complete.connect(self._scan_control.on_scan_complete)
        scanner.progress_updated.connect(self._scan_control.on_progress_updated)
        scanner.status_message.connect(self._status_bar.showMessage)
        scanner.scan_error.connect(self._on_scan_error)
        # MainWindow lifecycle hooks.
        scanner.scan_complete.connect(self._on_scan_complete)
        scanner.scan_paused.connect(self._on_scan_paused)
        scanner.scan_stopped.connect(self._on_scan_stopped)
        # ScanProgressWidget (centered progress display in splitter).
        sp = self._cleanup_screen.scan_progress_widget
        if sp:
            scanner.scan_started.connect(sp.on_scan_started)
            scanner.progress_updated.connect(sp.on_progress_updated)
            scanner.status_message.connect(sp.on_status_message)
            scanner.file_discovered.connect(sp.on_file_discovered)
            scanner.scan_complete.connect(sp.on_scan_complete)
            scanner.scan_paused.connect(sp.on_scan_paused)
            scanner.scan_stopped.connect(sp.on_scan_stopped)
        # FolderPanel: throttled count updates during scan.
        scanner.directories_hashed.connect(self._folder_panel.on_directories_hashed)
        scanner.scan_started.connect(self._folder_panel.update_all_counts)
        scanner.scan_complete.connect(self._folder_panel.reset_display_text)
        scanner.scan_stopped.connect(self._folder_panel.reset_display_text)

    @pyqtSlot()
    def _on_scan_complete(self) -> None:
        if self._session_id is None:
            return

        # Swap back to results tree and populate from DB.
        self._cleanup_screen.hide_scan_progress()
        self._results_panel.reload()

        # Compute scan summary.
        files = self._db.get_files_for_session(self._session_id)
        total_files = sum(1 for f in files if f["status"] == "active")
        dup_groups = self._db.get_duplicate_groups(self._session_id)
        group_count = len(dup_groups)
        dup_file_count = sum(g["file_count"] for g in dup_groups)

        self._plan_action.setEnabled(group_count > 0)

        if group_count > 0:
            self._results_panel.set_filter(FILTER_DUPLICATES_ONLY)
            self._status_bar.showMessage(
                self.tr("Scan complete: {0} files scanned, {1} duplicates in {2} groups.").format(
                    total_files, dup_file_count, group_count
                )
            )
        else:
            self._status_bar.showMessage(
                self.tr("Scan complete: {0} files scanned. No duplicates found.").format(
                    total_files
                )
            )

        # Plan §Workflow 5 — after scan complete: upload export.
        self._run_sync(session_id=self._session_id)

    @pyqtSlot()
    def _on_scan_paused(self) -> None:
        """Swap back to results tree so user can browse partial results."""
        self._cleanup_screen.hide_scan_progress()
        self._results_panel.reload()

    @pyqtSlot()
    def _on_scan_stopped(self) -> None:
        """Swap back to results tree showing partial results."""
        self._cleanup_screen.hide_scan_progress()
        self._results_panel.reload()

    @pyqtSlot(str, str)
    def _on_scan_error(self, path: str, message: str) -> None:
        log.warning("Scan error on %s: %s", path, message)
        self._status_bar.showMessage(
            self.tr("Error: {0}").format(message)
        )

    # ── Planning panel lifecycle (Pluggable Views) ─────────────────────

    @pyqtSlot()
    def _on_plan_actions(self) -> None:
        """Scan > Plan Actions — open the planning view."""
        if self._session_id is None:
            return
        # Ensure we're on cleanup screen
        if self._nav.current_screen() != "cleanup":
            self._nav.navigate_to("cleanup")
        self._cleanup_screen.show_planning_panel()

    # ── Plan Review navigation (UX Redesign Phase 2) ───────────────────

    @pyqtSlot()
    def _on_review_requested(self) -> None:
        """PlanningPanel > Review Plan — navigate to Plan Review screen."""
        self._nav.navigate_to("plan_review")

    @pyqtSlot()
    def _on_review_back(self) -> None:
        """Plan Review > Back — return to cleanup screen (planning panel)."""
        self._nav.go_back()

    @pyqtSlot()
    def _on_commit_requested(self) -> None:
        """Plan Review > Apply Changes — confirm and start execution."""
        if self._session_id is None:
            return

        summary = self._db.get_plan_summary(self._session_id)
        count = summary["delete_count"]
        if count == 0:
            return

        reply = QMessageBox.question(
            self,
            self.tr("Confirm Deletion"),
            self.tr(
                "Move {0} files to .dejaview_trash?\n"
                "Files are recoverable for 30 days."
            ).format(count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_execution()

    def _start_execution(self) -> None:
        """Create the executor, wire signals, navigate to execution screen."""
        self._executor = PlanExecutor(
            db=self._db,
            session_id=self._session_id,
            trash_root=self._trash_root,
            drive_sync=self._drive_sync,
            parent=self,
        )

        # Wire executor → execution screen
        es = self._execution_screen
        self._executor.execution_started.connect(es.on_execution_started)
        self._executor.progress_updated.connect(es.on_progress_updated)
        self._executor.log_message.connect(es.on_log_message)
        self._executor.stage_changed.connect(es.on_stage_changed)
        self._executor.execution_complete.connect(es.on_execution_complete)
        self._executor.execution_error.connect(es.on_execution_error)

        # Wire executor → main window
        self._executor.execution_complete.connect(self._on_execution_complete)
        self._executor.log_message.connect(
            lambda msg: self._status_bar.showMessage(msg)
        )

        self._nav.navigate_to("execution")
        self._executor.start()

    @pyqtSlot(int, int)
    def _on_execution_complete(self, success: int, errors: int) -> None:
        """Handle execution completion."""
        if errors > 0:
            msg = self.tr(
                "Execution complete: {0} files deleted, {1} errors."
            ).format(success, errors)
        else:
            msg = self.tr(
                "Execution complete: {0} files deleted."
            ).format(success)
        self._status_bar.showMessage(msg)

        # Tray notification if minimized
        if not self.isVisible() and self._tray.isVisible():
            self._tray.notify_complete(msg)

    @pyqtSlot()
    def _on_execution_done(self) -> None:
        """Execution screen > Done — return to dashboard."""
        self._tray.hide()
        # Clear back-stack and go to dashboard
        self._nav.navigate_to("dashboard", push_back=False)
        self._dashboard.refresh()

    @pyqtSlot()
    def _on_minimize_to_tray(self) -> None:
        """Execution screen > Minimize to Tray."""
        self._tray.show_progress(self.tr("Executing plan\u2026"))
        self.hide()

    @pyqtSlot("QSystemTrayIcon::ActivationReason")
    def _on_tray_activated(self, reason) -> None:
        """Restore window when tray icon is clicked."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()
            self._tray.hide()

    @pyqtSlot()
    def _on_plan_cleared(self) -> None:
        """Plan Review > Clear Plan — go back to cleanup."""
        self._nav.go_back()
        self._status_bar.showMessage(self.tr("Plan cleared."))

    # ── Export / Import (plan §Workflow 6 — manual sharing, Phase 5) ────

    @pyqtSlot()
    def _on_export(self) -> None:
        """Share > Export Scan Results — save current session as JSON."""
        if self._session_id is None:
            self._status_bar.showMessage(
                self.tr("No scan session to export.")
            )
            return

        config = self._db.get_sync_config()
        default_name = config["local_username"] if config else ""
        username, ok = QInputDialog.getText(
            self,
            self.tr("Export Scan Results"),
            self.tr("Display name (used as filename):"),
            text=default_name,
        )
        if not ok or not username:
            return
        if not validate_username(username):
            QMessageBox.warning(
                self,
                self.tr("Invalid Name"),
                self.tr(
                    "Display name must be 1\u201364 characters, "
                    "letters, digits, dash, or underscore only."
                ),
            )
            return

        privacy = config["export_privacy"] if config else "filename"

        try:
            payload = build_export_payload(
                self._db, self._session_id, username, privacy
            )
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Export Error"), str(exc))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Export File"),
            f"{username}.json",
            self.tr("JSON files (*.json)"),
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.critical(
                self, self.tr("Export Error"),
                self.tr("Could not write file: {0}").format(exc),
            )
            return

        self._status_bar.showMessage(
            self.tr("Exported {0} files to {1}.").format(
                len(payload["files"]), path
            )
        )

    @pyqtSlot()
    def _on_import(self) -> None:
        """Share > Import Scan Results — load a peer's JSON export."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Scan Results"),
            "",
            self.tr("JSON files (*.json)"),
        )
        if not path:
            return

        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as exc:
            QMessageBox.critical(
                self, self.tr("Import Error"),
                self.tr("Could not read file: {0}").format(exc),
            )
            return

        try:
            username = import_payload(self._db, raw)
        except ImportError as exc:
            QMessageBox.warning(
                self, self.tr("Import Error"), str(exc),
            )
            return

        self._results_panel.update_cross_library_data()
        self._status_bar.showMessage(
            self.tr("Imported scan results from '{0}'.").format(username)
        )

    # ── Configure Sync / Manage Peers (plan §Phase 6) ───────────────────

    @pyqtSlot()
    def _on_configure_sync(self) -> None:
        """Share > Configure Sync — open the ShareDialog."""
        self._share_dialog = ShareDialog(
            db=self._db,
            drive_sync=self._drive_sync,
            parent=self,
        )
        self._share_dialog.sign_in_requested.connect(self._on_sign_in_requested)
        self._share_dialog.sync_requested.connect(self._on_sync_now)
        self._share_dialog.peer_removed.connect(self._on_peer_removed)
        self._share_dialog.settings_saved.connect(self._on_sync_settings_saved)
        self._share_dialog.exec()
        self._share_dialog = None

    @pyqtSlot()
    def _on_manage_peers(self) -> None:
        """Share > Manage Synced Libraries — open the same dialog."""
        self._on_configure_sync()

    @pyqtSlot()
    def _on_sign_in_requested(self) -> None:
        """Start the OAuth2 sign-in flow in a background thread."""
        if self._drive_sync is None:
            self._status_bar.showMessage(self.tr("Sync not configured."))
            return
        if self._auth_worker is not None and self._auth_worker.isRunning():
            return
        self._status_bar.showMessage(self.tr("Signing in with Google\u2026"))
        if self._share_dialog is not None:
            self._share_dialog.set_signing_in(True)
        self._auth_worker = _AuthWorker(self._drive_sync, parent=self)
        self._auth_worker.auth_finished.connect(self._on_auth_finished)
        self._auth_worker.start()

    @pyqtSlot(bool, str)
    def _on_auth_finished(self, ok: bool, message: str) -> None:
        """Handle OAuth2 authentication result from the background thread."""
        if ok:
            self._status_bar.showMessage(self.tr("Signed in to Google Drive."))
        else:
            reason = message if message else self.tr("Unknown error")
            self._status_bar.showMessage(
                self.tr("Google sign-in failed: {0}").format(reason)
            )
            log.error("Google sign-in failed: %s", reason)
        if self._share_dialog is not None:
            self._share_dialog.set_signing_in(False)
            self._share_dialog.update_auth_status(message if not ok else "")

    @pyqtSlot()
    def _on_sync_now(self) -> None:
        """Trigger an immediate sync cycle."""
        self._run_sync(session_id=self._session_id)

    @pyqtSlot(str)
    def _on_peer_removed(self, username: str) -> None:
        """Remove a peer via DriveSync or directly from DB."""
        if self._drive_sync:
            self._drive_sync.remove_peer(username)
        else:
            self._db.delete_remote_peer(username)
        self._results_panel.update_cross_library_data()
        self._status_bar.showMessage(
            self.tr("Removed peer '{0}'.").format(username)
        )

    @pyqtSlot()
    def _on_sync_settings_saved(self) -> None:
        """After sync settings saved, refresh cross-library data."""
        self._results_panel.update_cross_library_data()
        self._status_bar.showMessage(self.tr("Sync settings saved."))

    # ── Settings (Feature Request 2 — Settings Dialog) ─────────────────

    @pyqtSlot()
    def _on_settings(self) -> None:
        """File > Settings — open the Settings dialog."""
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(db=self._db, parent=self)
        dlg.settings_saved.connect(
            lambda: self._status_bar.showMessage(self.tr("Settings saved."))
        )
        dlg.exec()

    # ── Help (Feature Request 1 — Help Menu) ─────────────────────────────

    @pyqtSlot()
    def _on_user_guide(self) -> None:
        """Help > User Guide — open the localised user guide dialog."""
        guide_dir = Path(__file__).resolve().parent.parent / "resources" / "help"
        dlg = HelpDialog(guide_dir=guide_dir, parent=self)
        dlg.exec()

    # ── Sync execution (plan §Workflow 5 — Ongoing sync) ─────────────────

    def sync_on_start(self) -> None:
        """Download peer exports silently in the background on app start."""
        self._run_sync(session_id=None)

    def _run_sync(self, session_id: int | None = None) -> None:
        """Run a sync cycle in a background thread (non-blocking)."""
        if self._drive_sync is None:
            return
        config = self._db.get_sync_config()
        if not config or not config["sync_enabled"]:
            return
        if not self._drive_sync.is_authenticated():
            return
        if self._sync_worker is not None and self._sync_worker.isRunning():
            return

        self._status_bar.showMessage(self.tr("\u2195 Syncing\u2026"))
        self._sync_worker = _SyncWorker(self._drive_sync, session_id)
        self._sync_worker.finished_status.connect(self._on_sync_finished)
        self._sync_worker.start()

    def _run_sync_blocking(self, session_id: int | None = None) -> None:
        """Run a sync cycle synchronously (for closeEvent)."""
        if self._drive_sync is None:
            return
        config = self._db.get_sync_config()
        if not config or not config["sync_enabled"]:
            return
        if not self._drive_sync.is_authenticated():
            return
        try:
            self._drive_sync.sync(session_id=session_id)
        except Exception as exc:
            log.warning("Final sync on close failed: %s", exc)

    @pyqtSlot(str)
    def _on_sync_finished(self, status: str) -> None:
        """Update status bar after background sync completes."""
        if status == "synced":
            self._status_bar.showMessage(self.tr("\u2713 Synced."))
        elif status == "unavailable":
            self._status_bar.showMessage(
                self.tr("\u26a0 Sync unavailable \u2014 showing last known data")
            )
        else:
            self._status_bar.showMessage(self.tr("\u2713 Sync complete."))
        self._results_panel.update_cross_library_data()

    # ── Window close ─────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._scanner and self._scanner.isRunning():
            self._scanner.stop()
            self._scanner.wait(5000)
        if self._executor and self._executor.isRunning():
            self._executor.stop()
            self._executor.wait(5000)
        if self._auth_worker is not None and self._auth_worker.isRunning():
            self._auth_worker.wait(5000)
        if self._sync_worker is not None and self._sync_worker.isRunning():
            self._sync_worker.wait(5000)
        self._tray.hide()
        self._run_sync_blocking(session_id=self._session_id)
        event.accept()


# ── Background auth worker (non-blocking OAuth2 desktop flow) ────────────

class _AuthWorker(QThread):
    """Runs DriveSync.authenticate() in a background thread."""

    auth_finished = pyqtSignal(bool, str)

    def __init__(self, drive_sync: DriveSync, parent=None):
        super().__init__(parent)
        self._drive_sync = drive_sync

    def run(self) -> None:
        try:
            ok, msg = self._drive_sync.authenticate()
        except Exception as exc:
            log.warning("Auth worker exception: %s", exc)
            ok, msg = False, str(exc)
        self.auth_finished.emit(ok, msg)


# ── Background sync worker (plan §Workflow 5 — non-blocking sync) ────────

class _SyncWorker(QThread):
    """Runs DriveSync.sync() in a background thread."""

    finished_status = pyqtSignal(str)

    def __init__(self, drive_sync: DriveSync, session_id: int | None = None, parent=None):
        super().__init__(parent)
        self._drive_sync = drive_sync
        self._session_id = session_id

    def run(self) -> None:
        try:
            status = self._drive_sync.sync(session_id=self._session_id)
        except Exception as exc:
            log.warning("Background sync failed: %s", exc)
            status = "unavailable"
        self.finished_status.emit(status)
