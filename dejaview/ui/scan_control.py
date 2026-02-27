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
import time

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
        self._eta_reset()

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
        self._status_label.setMinimumWidth(200)
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
        self._eta_reset()

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
        self._eta_reset()

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

        now = time.monotonic()

        # Start timing on the first completed file.
        if current == 1:
            self._eta_start = now
            self._eta_last_update = 0.0
            self._eta_text = ""

        # Show total elapsed time on completion.
        if current >= total and total > 0 and self._eta_start is not None:
            elapsed = now - self._eta_start
            label = self.tr("{0} / {1} \u2014 {2}").format(
                current, total, self._format_duration(elapsed)
            )
            self._status_label.setText(label)
            return

        # Update ETA at most once per second to avoid flickering.
        if (
            current > 0
            and total > 0
            and self._eta_start is not None
            and now - self._eta_last_update >= 1.0
        ):
            elapsed = now - self._eta_start
            if elapsed <= 0:
                elapsed = 0.001  # guard against instant completion in tests
            rate = current / elapsed
            remaining = (total - current) / rate
            self._eta_text = self.tr("~{0} left").format(
                self._format_duration(remaining)
            )
            self._eta_last_update = now

        if self._eta_text:
            label = self.tr("{0} / {1} \u2014 {2}").format(
                current, total, self._eta_text
            )
        else:
            label = self.tr("{0} / {1}").format(current, total)
        self._status_label.setText(label)

    # ── ETA helpers ─────────────────────────────────────────────────────

    def _eta_reset(self) -> None:
        """Reset ETA tracking state."""
        self._eta_start: float | None = None
        self._eta_last_update: float = 0.0
        self._eta_text: str = ""

    def _format_duration(self, seconds: float) -> str:
        """Format seconds into a human-readable duration string."""
        s = int(seconds)
        if s < 60:
            return self.tr("{0}s").format(s)
        m, s = divmod(s, 60)
        if m < 60:
            return self.tr("{0}m {1}s").format(m, s)
        h, m = divmod(m, 60)
        if h < 24:
            return self.tr("{0}h {1}m").format(h, m)
        d, h = divmod(h, 24)
        return self.tr("{0}d {1}h").format(d, h)
