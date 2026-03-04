"""
verify_main.py — Standalone GUI for the DejaView Deletion Verifier.

Minimal PyQt6 application that verifies every trashed image has an
identical pixel-hash duplicate in the source directory.

Run from source:   python verify_main.py
Build to EXE:      pyinstaller verify.spec --noconfirm
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Import verification logic — works both from source and PyInstaller bundle
# ---------------------------------------------------------------------------
# When running from source the tests package is importable directly.
# When frozen by PyInstaller, verify_deletions.py is bundled as a top-level
# module (see verify.spec datas).

try:
    from tests.e2e.verify_deletions import (
        DEFAULT_TRASH_ROOT,
        VerificationReport,
        verify_deletions,
    )
except ImportError:
    from verify_deletions import (  # type: ignore[no-redef]
        DEFAULT_TRASH_ROOT,
        VerificationReport,
        verify_deletions,
    )


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _VerifyWorker(QThread):
    """Runs verify_deletions in a background thread."""

    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # (current, total)
    phase = pyqtSignal(str)          # "source" or "trash"
    finished_ok = pyqtSignal(object)  # VerificationReport
    finished_err = pyqtSignal(str)    # error message

    def __init__(
        self, source_dir: str, trash_dir: str, csv_path: str, parent=None
    ):
        super().__init__(parent)
        self._source_dir = source_dir
        self._trash_dir = trash_dir
        self._csv_path = csv_path
        self._current_phase = "source"

    def run(self) -> None:
        try:
            # We intercept on_log and on_progress to emit signals.
            # The progress callback is called for both phases;
            # we track which phase via the log messages.
            def _on_log(msg: str) -> None:
                if "Scanning trash" in msg or "Verifying trash" in msg:
                    self._current_phase = "trash"
                self.phase.emit(self._current_phase)
                self.log.emit(msg)

            def _on_progress(current: int, total: int) -> None:
                self.progress.emit(current, total)

            report = verify_deletions(
                self._source_dir,
                self._trash_dir,
                self._csv_path,
                on_log=_on_log,
                on_progress=_on_progress,
            )
            self.finished_ok.emit(report)
        except Exception as exc:
            self.finished_err.emit(str(exc))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class VerifyWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DejaView — Deletion Verifier")
        self.setMinimumSize(640, 520)
        self._worker: _VerifyWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Title ───────────────────────────────────────────────────────
        title = QLabel("DejaView — Deletion Verifier")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Verifies every trashed image has an identical copy "
            "in the source folder."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # ── Source directory row ────────────────────────────────────────
        layout.addWidget(QLabel("Source folder (where originals remain):"))
        row_src = QHBoxLayout()
        self._src_edit = QLineEdit()
        self._src_edit.setPlaceholderText("Select the folder that was scanned for duplicates...")
        row_src.addWidget(self._src_edit)
        btn_src = QPushButton("Browse...")
        btn_src.setFixedWidth(90)
        btn_src.clicked.connect(self._browse_source)
        row_src.addWidget(btn_src)
        layout.addLayout(row_src)

        # ── Trash directory row ─────────────────────────────────────────
        layout.addWidget(QLabel("Trash folder:"))
        row_trash = QHBoxLayout()
        self._trash_edit = QLineEdit()
        self._trash_edit.setText(str(DEFAULT_TRASH_ROOT))
        row_trash.addWidget(self._trash_edit)
        btn_trash = QPushButton("Browse...")
        btn_trash.setFixedWidth(90)
        btn_trash.clicked.connect(self._browse_trash)
        row_trash.addWidget(btn_trash)
        layout.addLayout(row_trash)

        # ── Verify button ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._verify_btn = QPushButton("Verify")
        self._verify_btn.setFixedSize(120, 36)
        self._verify_btn.setStyleSheet(
            "QPushButton { background: #0078d4; color: white; font-weight: bold;"
            " border: none; border-radius: 4px; font-size: 14px; }"
            "QPushButton:hover { background: #106ebe; }"
            "QPushButton:disabled { background: #ccc; color: #888; }"
        )
        self._verify_btn.clicked.connect(self._start_verify)
        btn_row.addWidget(self._verify_btn)
        layout.addLayout(btn_row)

        # ── Progress bar ────────────────────────────────────────────────
        self._phase_label = QLabel("")
        self._phase_label.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self._phase_label)

        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setValue(0)
        self._progress.setStyleSheet(
            "QProgressBar { border: 1px solid #bbb; border-radius: 3px;"
            " background: #f0f0f0; height: 20px; text-align: center; }"
            "QProgressBar::chunk { background: #0078d4; border-radius: 2px; }"
        )
        layout.addWidget(self._progress)

        # ── Log area ───────────────────────────────────────────────────
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 12px;"
            " background: #1e1e1e; color: #d4d4d4; border: 1px solid #bbb;"
            " border-radius: 3px; }"
        )
        layout.addWidget(self._log, stretch=1)

        # ── Result banner ───────────────────────────────────────────────
        self._result_label = QLabel("")
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_label.setMinimumHeight(48)
        self._result_label.setStyleSheet("font-size: 14px; border-radius: 4px;")
        self._result_label.hide()
        layout.addWidget(self._result_label)

        # ── CSV path label ──────────────────────────────────────────────
        self._csv_label = QLabel("")
        self._csv_label.setStyleSheet("color: #555; font-size: 11px;")
        self._csv_label.setWordWrap(True)
        self._csv_label.hide()
        layout.addWidget(self._csv_label)

    # ── Browse slots ────────────────────────────────────────────────────

    @pyqtSlot()
    def _browse_source(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if d:
            self._src_edit.setText(d)

    @pyqtSlot()
    def _browse_trash(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Trash Folder", self._trash_edit.text()
        )
        if d:
            self._trash_edit.setText(d)

    # ── Verification ────────────────────────────────────────────────────

    @pyqtSlot()
    def _start_verify(self) -> None:
        source = self._src_edit.text().strip()
        trash = self._trash_edit.text().strip()

        if not source:
            self._append_log("ERROR: Please select a source folder.")
            return
        if not Path(source).is_dir():
            self._append_log(f"ERROR: Source folder not found: {source}")
            return
        if not trash:
            self._append_log("ERROR: Please select a trash folder.")
            return
        if not Path(trash).is_dir():
            self._append_log(f"ERROR: Trash folder not found: {trash}")
            return

        # CSV goes next to the exe (or cwd) with a timestamp.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = str(
            Path(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd())
            / f"deletion_verification_{timestamp}.csv"
        )

        # Reset UI state.
        self._result_label.hide()
        self._csv_label.hide()
        self._log.clear()
        self._progress.setValue(0)
        self._phase_label.setText("")
        self._verify_btn.setEnabled(False)

        self._append_log(f"Source:  {source}")
        self._append_log(f"Trash:   {trash}")
        self._append_log(f"Report:  {csv_path}")
        self._append_log("")

        self._worker = _VerifyWorker(source, trash, csv_path, parent=self)
        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.phase.connect(self._on_phase)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.finished_err.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(str)
    def _append_log(self, msg: str) -> None:
        self._log.append(msg)
        # Auto-scroll to bottom.
        sb = self._log.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    @pyqtSlot(int, int)
    def _on_progress(self, current: int, total: int) -> None:
        self._progress.setMaximum(total)
        self._progress.setValue(current)
        self._progress.setFormat(f"{current} / {total}")

    @pyqtSlot(str)
    def _on_phase(self, phase: str) -> None:
        if phase == "source":
            self._phase_label.setText("Phase 1/2: Hashing source images...")
        else:
            self._phase_label.setText("Phase 2/2: Verifying trashed images...")

    @pyqtSlot(object)
    def _on_finished(self, report: VerificationReport) -> None:
        self._verify_btn.setEnabled(True)
        self._phase_label.setText("Done.")
        self._progress.setValue(self._progress.maximum())

        self._append_log("")
        self._append_log("=" * 50)
        self._append_log(f"  Total trashed images : {report.total_trash}")
        self._append_log(f"  Verified (matched)   : {len(report.matched)}")
        self._append_log(f"  MISSING (no match)   : {len(report.missing)}")
        self._append_log(f"  Errors (unhashable)  : {len(report.errors)}")
        self._append_log("=" * 50)

        if report.ok:
            self._result_label.setText(
                f"PASS — All {len(report.matched)} trashed images "
                f"have verified duplicates"
            )
            self._result_label.setStyleSheet(
                "background: #28a745; color: white; font-size: 15px;"
                " font-weight: bold; padding: 10px; border-radius: 4px;"
            )
        else:
            parts = []
            if report.missing:
                parts.append(f"{len(report.missing)} MISSING")
            if report.errors:
                parts.append(f"{len(report.errors)} errors")
            self._result_label.setText(
                f"FAIL — {', '.join(parts)} out of {report.total_trash} trashed images"
            )
            self._result_label.setStyleSheet(
                "background: #dc3545; color: white; font-size: 15px;"
                " font-weight: bold; padding: 10px; border-radius: 4px;"
            )
        self._result_label.show()

        if report.csv_path:
            self._csv_label.setText(f"CSV report: {report.csv_path}")
            self._csv_label.show()

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._verify_btn.setEnabled(True)
        self._phase_label.setText("Error.")
        self._append_log(f"\nFATAL ERROR: {msg}")
        self._result_label.setText(f"ERROR — {msg}")
        self._result_label.setStyleSheet(
            "background: #dc3545; color: white; font-size: 15px;"
            " font-weight: bold; padding: 10px; border-radius: 4px;"
        )
        self._result_label.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = VerifyWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
