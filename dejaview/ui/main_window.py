"""
ui/main_window.py — DejaView application shell (plan §UI Layout — Main Window).

Layout:
  Menu bar  : File | View | Scan | Share | Help
  Left pane : FolderPanel (180–300 px wide)
  Right pane: ResultsPanel (Phase 3) or CompareView (Phase 4)
  Bottom bar: ScanControl (buttons + progress)
  Status bar: one-line status messages

Sync lifecycle hooks (plan §Workflow 5 — Ongoing sync):
  - sync_on_start(): download peers silently in background
  - _on_scan_complete(): upload export after scan finishes
  - closeEvent(): final export upload before exit
  - Configure Sync menu → ShareDialog (Phase 6.3)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.scanner import Scanner
from data.db import Database
from data.export import build_export_payload, import_payload, validate_username
from data.sync import DriveSync
from ui.compare_view import CompareView
from ui.folder_panel import FolderPanel
from ui.help_dialog import HelpDialog
from ui.results_panel import ResultsPanel
from ui.scan_control import ScanControl
from ui.share_dialog import ShareDialog

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Top-level window.  Owns the session lifecycle: create / restore sessions,
    wire FolderPanel to ScanControl via the Scanner QThread.
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
        self._scanner: Scanner | None = None
        self._session_id: int | None = None
        self._compare_view: CompareView | None = None
        self._sync_worker: _SyncWorker | None = None
        self._auth_worker: "_AuthWorker | None" = None
        self._share_dialog: ShareDialog | None = None

        self.setWindowTitle(self.tr("DejaView"))
        self.setMinimumSize(900, 600)

        self._build_menu()
        self._build_central()
        self._build_status_bar()
        self._restore_session()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu(self.tr("File"))
        file_menu.addAction(self.tr("Add Folder\u2026"), self._on_add_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.tr("Settings\u2026"))   # Phase 7 placeholder
        file_menu.addSeparator()
        file_menu.addAction(self.tr("Exit"), self.close)

        # View — populated in Phase 3
        mb.addMenu(self.tr("View"))

        # Scan
        scan_menu = mb.addMenu(self.tr("Scan"))
        scan_menu.addAction(self.tr("Start Scan"), self._on_start)
        scan_menu.addAction(self.tr("Pause"), self._on_pause)
        scan_menu.addAction(self.tr("Stop"), self._on_stop)

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
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: folder panel (no session_id yet; set in _restore_session or on start)
        self._folder_panel = FolderPanel(db=self._db, parent=self)
        self._folder_panel.setMinimumWidth(180)
        self._folder_panel.setMaximumWidth(300)
        self._splitter.addWidget(self._folder_panel)

        # Right: results tree view (plan §Dev Phases Phase 3).
        self._results_panel = ResultsPanel(db=self._db, parent=self)
        self._results_panel.setObjectName("results_panel")
        self._splitter.addWidget(self._results_panel)

        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        # Wrap splitter + scan control in a vertical layout
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._splitter)

        self._scan_control = ScanControl(parent=self)
        layout.addWidget(self._scan_control)

        self.setCentralWidget(container)

        # Wire scan control buttons to slots
        self._scan_control.start_requested.connect(self._on_start)
        self._scan_control.pause_requested.connect(self._on_pause)
        self._scan_control.stop_requested.connect(self._on_stop)

        # Wire ResultsPanel → CompareView (plan §Phase 4 — comparison).
        self._results_panel.compare_view_requested.connect(self._on_compare_requested)

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(self.tr("Add folders to get started."))

    # ── Session management ───────────────────────────────────────────────

    def _restore_session(self) -> None:
        """
        On startup, check for a paused or in-progress session.
        If found, restore its folder list and update button state.
        """
        session = self._db.get_latest_session()
        if session and session["status"] in ("in_progress", "paused"):
            self._session_id = session["id"]
            self._folder_panel.set_session_id(self._session_id)
            self._results_panel.set_session_id(self._session_id)
            for folder in self._db.get_session_folders(self._session_id):
                # persist=False: folders already exist in the DB from previous run.
                self._folder_panel.add_folder(folder, persist=False)
            if session["status"] == "paused":
                self._scan_control.set_state_paused()
                self._status_bar.showMessage(
                    self.tr("Scan paused. Click Resume to continue.")
                )

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
            self._folder_panel.set_session_id(self._session_id)
            self._results_panel.set_session_id(self._session_id)
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
            self._folder_panel.add_folder(folder)

    @pyqtSlot()
    def _on_start(self) -> None:
        if self._scanner and self._scanner.isRunning():
            return  # Already scanning; ignore spurious clicks.

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
        self._scanner = Scanner(
            db=self._db,
            session_id=session_id,
            thumb_dir=self._thumb_dir,
            parent=self,
        )
        if is_resume:
            self._scanner.set_resuming(True)
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
        scanner.scan_started.connect(self._scan_control.on_scan_started)
        scanner.scan_paused.connect(self._scan_control.on_scan_paused)
        scanner.scan_resumed.connect(self._scan_control.on_scan_resumed)
        scanner.scan_stopped.connect(self._scan_control.on_scan_stopped)
        scanner.scan_complete.connect(self._scan_control.on_scan_complete)
        scanner.progress_updated.connect(self._scan_control.on_progress_updated)
        scanner.status_message.connect(self._status_bar.showMessage)
        scanner.scan_error.connect(self._on_scan_error)
        scanner.scan_complete.connect(self._on_scan_complete)
        # ResultsPanel live updates (plan §Phase 3 — live badge updates).
        scanner.file_discovered.connect(self._results_panel.on_file_discovered)
        scanner.hash_complete.connect(self._results_panel.on_hash_complete)
        scanner.duplicate_found.connect(self._results_panel.on_duplicate_found)

    @pyqtSlot()
    def _on_scan_complete(self) -> None:
        self._status_bar.showMessage(self.tr("Scan complete."))
        # Plan §Workflow 5 — after scan complete: upload export.
        self._run_sync(session_id=self._session_id)

    @pyqtSlot(str, str)
    def _on_scan_error(self, path: str, message: str) -> None:
        log.warning("Scan error on %s: %s", path, message)
        self._status_bar.showMessage(
            self.tr("Error: {0}").format(message)
        )

    # ── Compare view lifecycle (plan §Phase 4 — comparison) ────────────

    @pyqtSlot(str)
    def _on_compare_requested(self, pixel_hash: str) -> None:
        """Open the CompareView for a duplicate group, replacing the results panel."""
        if self._session_id is None:
            return
        session_folders = self._db.get_session_folders(self._session_id)
        self._compare_view = CompareView(
            db=self._db,
            session_id=self._session_id,
            pixel_hash=pixel_hash,
            session_folders=session_folders,
            parent=self,
        )
        self._compare_view.setObjectName("compare_view")
        self._compare_view.actions_confirmed.connect(self._on_actions_confirmed)
        self._compare_view.closed.connect(self._close_compare_view)
        # Swap: hide results panel, show compare view in the splitter.
        self._results_panel.hide()
        self._splitter.addWidget(self._compare_view)
        self._splitter.setStretchFactor(self._splitter.indexOf(self._compare_view), 1)
        self._status_bar.showMessage(
            self.tr("Comparing duplicate group (SHA: {0}\u2026)").format(pixel_hash[:8])
        )

    @pyqtSlot()
    def _on_actions_confirmed(self) -> None:
        """Refresh the results panel after actions are confirmed (plan §Post-Action Cleanup)."""
        self._results_panel.reload()

    @pyqtSlot()
    def _close_compare_view(self) -> None:
        """Close the CompareView and restore the results panel."""
        if self._compare_view is not None:
            self._compare_view.hide()
            self._compare_view.deleteLater()
            self._compare_view = None
        self._results_panel.show()
        self._results_panel.reload()
        self._status_bar.showMessage(self.tr("Ready."))

    # ── Export / Import (plan §Workflow 6 — manual sharing, Phase 5) ────

    @pyqtSlot()
    def _on_export(self) -> None:
        """Share > Export Scan Results — save current session as JSON."""
        if self._session_id is None:
            self._status_bar.showMessage(
                self.tr("No scan session to export.")
            )
            return

        # Prompt for display name.
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

        # Determine privacy level from sync_config (default: 'filename').
        privacy = config["export_privacy"] if config else "filename"

        # Build payload.
        try:
            payload = build_export_payload(
                self._db, self._session_id, username, privacy
            )
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Export Error"), str(exc))
            return

        # Choose save path.
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

        # Refresh cross-library view after import.
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
        """Start the OAuth2 sign-in flow in a background thread.

        run_local_server() blocks until the browser callback arrives, so it
        must not run on the Qt main thread — doing so freezes the event loop
        and prevents the browser window from receiving focus on Windows.
        """
        if self._drive_sync is None:
            self._status_bar.showMessage(self.tr("Sync not configured."))
            return
        if self._auth_worker is not None and self._auth_worker.isRunning():
            return  # Already authenticating
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
        if self._share_dialog is not None:
            self._share_dialog.set_signing_in(False)
            self._share_dialog.update_auth_status()

    @pyqtSlot()
    def _on_sync_now(self) -> None:
        """Trigger an immediate sync cycle (plan §Workflow 5 — Sync Now)."""
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

    # ── Help (Feature Request 1 — Help Menu) ─────────────────────────────

    @pyqtSlot()
    def _on_user_guide(self) -> None:
        """Help > User Guide — open the localised user guide dialog."""
        guide_dir = Path(__file__).resolve().parent.parent / "resources" / "help"
        dlg = HelpDialog(guide_dir=guide_dir, parent=self)
        dlg.exec()

    # ── Sync execution (plan §Workflow 5 — Ongoing sync) ─────────────────

    def sync_on_start(self) -> None:
        """Download peer exports silently in the background on app start.

        Plan §Workflow 5 — On app start: silently download other users'
        exports and update the Cross-Library view.
        Called from main.py after window.show().
        """
        self._run_sync(session_id=None)

    def _run_sync(self, session_id: int | None = None) -> None:
        """Run a sync cycle in a background thread (non-blocking).

        Plan §Workflow 5: status bar shows sync indicator while in progress.
        """
        if self._drive_sync is None:
            return
        config = self._db.get_sync_config()
        if not config or not config["sync_enabled"]:
            return
        if not self._drive_sync.is_authenticated():
            return
        if self._sync_worker is not None and self._sync_worker.isRunning():
            return  # Already syncing

        self._status_bar.showMessage(self.tr("\u2195 Syncing\u2026"))
        self._sync_worker = _SyncWorker(self._drive_sync, session_id)
        self._sync_worker.finished_status.connect(self._on_sync_finished)
        self._sync_worker.start()

    def _run_sync_blocking(self, session_id: int | None = None) -> None:
        """Run a sync cycle synchronously (for closeEvent).

        Plan §Workflow 5 — On app close: a final export upload runs.
        """
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
        """Update status bar after background sync completes.

        Plan §Workflow 5: status bar indicator.
        """
        if status == "synced":
            self._status_bar.showMessage(self.tr("\u2713 Synced."))
        elif status == "unavailable":
            self._status_bar.showMessage(
                self.tr("\u26a0 Sync unavailable \u2014 showing last known data")
            )
        else:
            self._status_bar.showMessage(self.tr("\u2713 Sync complete."))
        # Refresh cross-library data after sync.
        self._results_panel.update_cross_library_data()

    # ── Window close ─────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._scanner and self._scanner.isRunning():
            self._scanner.stop()
            self._scanner.wait(5000)
        # Wait for any in-progress auth or sync workers to finish.
        if self._auth_worker is not None and self._auth_worker.isRunning():
            self._auth_worker.wait(5000)
        if self._sync_worker is not None and self._sync_worker.isRunning():
            self._sync_worker.wait(5000)
        # Plan §Workflow 5 — on app close: final export upload.
        self._run_sync_blocking(session_id=self._session_id)
        event.accept()


# ── Background auth worker (non-blocking OAuth2 desktop flow) ────────────

class _AuthWorker(QThread):
    """Runs DriveSync.authenticate() in a background thread.

    flow.run_local_server() is a blocking call that opens a browser and waits
    for the OAuth2 callback.  Running it off the main thread keeps the Qt
    event loop alive so the browser receives focus and the UI stays responsive.

    Emits auth_finished(bool, str) — (True, "") on success,
    (False, reason) on failure.
    """

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
    """Runs DriveSync.sync() in a background thread.

    Emits finished_status(str) with the sync result status.
    """

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
