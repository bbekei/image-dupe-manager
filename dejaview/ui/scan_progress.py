"""
ui/scan_progress.py — Scan progress panel shown during active scanning.

Replaces the ResultsPanel in the splitter while a scan is running.
Shows a centered progress bar, file count with ETA, and phase indicators.
No tree model, no DB queries, no filter proxy — pure display widget.

The ResultsPanel is hidden during scanning and populated once when
the scan completes (or pauses), avoiding the O(N) incremental tree
update cost that caused UI freezes on large scans (70k+ files).
"""

import logging
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class ScanProgressWidget(QWidget):
    """Centered progress display shown in the splitter during scanning."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 0
        self._total = 0
        self._eta_start: float | None = None
        self._discovery_count: int | None = None
        self._phase = "discovery"  # "discovery" | "hashing"

        self._build_ui()

        # 1-second timer for smooth ETA, decoupled from batched progress signals.
        self._eta_timer = QTimer(self)
        self._eta_timer.setInterval(1000)
        self._eta_timer.timeout.connect(self._update_eta)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 0, 40, 0)

        # Vertical centering via spacers.
        layout.addStretch(2)

        # Title
        self._title = QLabel(self.tr("Scanning in progress\u2026"), self)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self._title)

        layout.addSpacing(16)

        # Progress bar — explicit chunk color avoids the Qt 6 / Windows 11
        # native-style bug where the bar disappears in inactive windows.
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMinimumWidth(300)
        self._progress.setMaximumWidth(500)
        self._progress.setStyleSheet(
            "QProgressBar { border: 1px solid #bbb; border-radius: 3px;"
            " background: #f0f0f0; height: 20px; text-align: center; }"
            " QProgressBar::chunk { background: #0078d4; border-radius: 2px; }"
        )
        self._progress.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        bar_container = QWidget(self)
        bar_layout = QVBoxLayout(bar_container)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self._progress)
        layout.addWidget(bar_container)

        layout.addSpacing(8)

        # Count + ETA label
        self._count_label = QLabel("", self)
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self._count_label)

        layout.addSpacing(16)

        # Phase indicators
        self._phase_label = QLabel("", self)
        self._phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._phase_label.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(self._phase_label)

        layout.addStretch(3)

    # ── Scanner signal slots ─────────────────────────────────────────────

    @pyqtSlot(int, int)
    def on_progress_updated(self, current: int, total: int) -> None:
        self._current = current
        self._total = total
        self._phase = "hashing"

        if total > 0:
            self._progress.setValue(min(100, int(current / total * 100)))

        if self._eta_start is None and current > 0:
            self._eta_start = time.monotonic()
            if not self._eta_timer.isActive():
                self._eta_timer.start()

        self._refresh_labels()

    @pyqtSlot(str)
    def on_status_message(self, message: str) -> None:
        """Track phase transitions from scanner status messages."""
        lower = message.lower()
        if "discover" in lower:
            self._phase = "discovery"
        elif "hash" in lower:
            self._phase = "hashing"

    @pyqtSlot()
    def on_scan_started(self) -> None:
        self._phase = "discovery"
        self._current = 0
        self._total = 0
        self._eta_start = None
        self._discovery_count = None
        self._progress.setValue(0)
        self._title.setText(self.tr("Scanning in progress\u2026"))
        self._count_label.setText("")
        self._phase_label.setText(
            self.tr("Pass 1: Discovering files\u2026")
        )

    @pyqtSlot(int, str)
    def on_file_discovered(self, file_id: int, path: str) -> None:
        """Track discovery count for the phase label."""
        if self._discovery_count is None:
            self._discovery_count = 0
        self._discovery_count += 1
        # Throttle label updates to avoid excessive main-thread work.
        if self._discovery_count % 500 == 0:
            self._phase_label.setText(
                self.tr("Pass 1: Discovering files\u2026  ({0} found)").format(
                    self._discovery_count
                )
            )

    @pyqtSlot()
    def on_scan_complete(self) -> None:
        self._eta_timer.stop()
        self._progress.setValue(100)
        self._title.setText(self.tr("Scan complete"))

    @pyqtSlot()
    def on_scan_paused(self) -> None:
        self._eta_timer.stop()
        self._title.setText(self.tr("Scan paused"))

    @pyqtSlot()
    def on_scan_stopped(self) -> None:
        self._eta_timer.stop()
        self._title.setText(self.tr("Scan stopped"))

    # ── Internal ─────────────────────────────────────────────────────────

    def _refresh_labels(self) -> None:
        eta_text = self._compute_eta()
        if eta_text:
            self._count_label.setText(
                self.tr("{0} / {1} files \u2014 {2}").format(
                    self._current, self._total, eta_text
                )
            )
        else:
            self._count_label.setText(
                self.tr("{0} / {1} files").format(self._current, self._total)
            )

        discovery_text = self.tr("Pass 1: Discovery \u2713")
        if self._discovery_count:
            discovery_text = self.tr("Pass 1: Discovery \u2713  ({0} files)").format(
                self._discovery_count
            )
        self._phase_label.setText(
            discovery_text + "\n"
            + self.tr("Pass 2: Hashing\u2026  ({0} / {1})").format(
                self._current, self._total
            )
        )

    def _compute_eta(self) -> str:
        if (
            self._current <= 0
            or self._total <= 0
            or self._eta_start is None
        ):
            return ""
        elapsed = time.monotonic() - self._eta_start
        if elapsed <= 0:
            return ""
        rate = self._current / elapsed
        remaining = max(0, (self._total - self._current)) / rate
        return self.tr("~{0} left").format(self._format_duration(remaining))

    @pyqtSlot()
    def _update_eta(self) -> None:
        self._refresh_labels()

    def _format_duration(self, seconds: float) -> str:
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
