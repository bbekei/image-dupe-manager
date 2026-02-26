"""
ui/scan_control.py — Scan control bar (plan Req 4.2).

Buttons: Start / Resume | Pause | Stop
Progress bar + "N / Total" counter label.

Button state machine (plan §UI Tests: scan_control.py):
  Initial   : Start=enabled, Pause=disabled, Stop=disabled
  Scanning  : Start=disabled, Pause=enabled,  Stop=enabled
  Paused    : Start(Resume)=enabled, Pause=disabled, Stop=enabled
  Stopped   : Start=enabled, Pause=disabled, Stop=disabled
  Complete  : Start=enabled, Pause=disabled, Stop=disabled

Emits start_requested / pause_requested / stop_requested signals.
Receives on_scan_* slots wired by MainWindow._wire_scanner().
"""

import logging

from PyQt6.QtCore import pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QWidget,
)

log = logging.getLogger(__name__)


class ScanControl(QWidget):
    """Bottom bar: Start/Pause/Stop buttons + progress bar + status label."""

    start_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    stop_requested  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._set_initial_state()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        self._start_btn = QPushButton(self)
        self._pause_btn = QPushButton(self)
        self._stop_btn  = QPushButton(self)

        layout.addWidget(self._start_btn)
        layout.addWidget(self._pause_btn)
        layout.addWidget(self._stop_btn)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress, stretch=1)

        self._status_label = QLabel("", self)
        self._status_label.setMinimumWidth(120)
        layout.addWidget(self._status_label)

        self._start_btn.clicked.connect(self.start_requested)
        self._pause_btn.clicked.connect(self.pause_requested)
        self._stop_btn.clicked.connect(self.stop_requested)

    # ── Button label helpers (all UI strings go through tr()) ────────────

    def _start_label(self)  -> str: return self.tr("\u25b6 Start")
    def _resume_label(self) -> str: return self.tr("\u25b6 Resume")
    def _pause_label(self)  -> str: return self.tr("\u23f8 Pause")
    def _stop_label(self)   -> str: return self.tr("\u23f9 Stop")

    # ── State machine ────────────────────────────────────────────────────

    def _set_initial_state(self) -> None:
        self._start_btn.setText(self._start_label())
        self._start_btn.setEnabled(True)
        self._pause_btn.setText(self._pause_label())
        self._pause_btn.setEnabled(False)
        self._stop_btn.setText(self._stop_label())
        self._stop_btn.setEnabled(False)
        self._progress.setValue(0)
        self._status_label.setText("")

    def set_state_paused(self) -> None:
        """Called by MainWindow when restoring a paused session on startup."""
        self.on_scan_paused()

    @pyqtSlot()
    def on_scan_started(self) -> None:
        self._start_btn.setEnabled(False)
        self._pause_btn.setText(self._pause_label())
        self._pause_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)
        self._status_label.setText("")

    @pyqtSlot()
    def on_scan_paused(self) -> None:
        self._start_btn.setText(self._resume_label())
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_label.setText(self.tr("PAUSED"))

    @pyqtSlot()
    def on_scan_resumed(self) -> None:
        self._start_btn.setEnabled(False)
        self._pause_btn.setText(self._pause_label())
        self._pause_btn.setEnabled(True)
        self._status_label.setText("")

    @pyqtSlot()
    def on_scan_stopped(self) -> None:
        self._set_initial_state()

    @pyqtSlot()
    def on_scan_complete(self) -> None:
        self._set_initial_state()
        self._status_label.setText(self.tr("Complete"))

    @pyqtSlot(int, int)
    def on_progress_updated(self, current: int, total: int) -> None:
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        self._status_label.setText(self.tr("{0} / {1}").format(current, total))
