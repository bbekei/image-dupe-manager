"""
ui/execution_screen.py — Execution progress screen (UX Redesign Phase 3).

Shows progress bars for Local Cleanup and Cloud Sync stages,
a collapsible real-time log, and a Done button on completion.
Follows the ScanProgressWidget pattern for smooth ETA display.
"""

import logging
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)

_PROGRESS_STYLE = (
    "QProgressBar { border: 1px solid #bbb; border-radius: 3px;"
    " background: #f0f0f0; height: 18px; text-align: center; }"
    " QProgressBar::chunk { background: #0078d4; border-radius: 2px; }"
)
_PROGRESS_DONE_STYLE = (
    "QProgressBar { border: 1px solid #bbb; border-radius: 3px;"
    " background: #f0f0f0; height: 18px; text-align: center; }"
    " QProgressBar::chunk { background: #2e7d32; border-radius: 2px; }"
)


class ExecutionScreen(QWidget):
    """Progress display during plan execution.

    Signals:
        done_requested:         user clicks Done — go back to dashboard
        minimize_requested:     user clicks Minimize to Tray
    """

    done_requested = pyqtSignal()
    minimize_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 0
        self._total = 0
        self._eta_start: float | None = None
        self._stage = "cleanup"
        self._finished = False

        self._build_ui()

        self._eta_timer = QTimer(self)
        self._eta_timer.setInterval(1000)
        self._eta_timer.timeout.connect(self._update_eta)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 24, 40, 24)
        root.setSpacing(12)

        root.addStretch(1)

        # Title
        self._title = QLabel(self.tr("Executing plan\u2026"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(16)
        self._title.setFont(title_font)
        root.addWidget(self._title)

        root.addSpacing(20)

        # Stage A: Local Cleanup
        self._cleanup_label = QLabel(self.tr("Local Cleanup"))
        cleanup_font = QFont()
        cleanup_font.setBold(True)
        self._cleanup_label.setFont(cleanup_font)
        root.addWidget(self._cleanup_label)

        self._cleanup_bar = QProgressBar()
        self._cleanup_bar.setRange(0, 100)
        self._cleanup_bar.setValue(0)
        self._cleanup_bar.setStyleSheet(_PROGRESS_STYLE)
        self._cleanup_bar.setMaximumWidth(600)
        root.addWidget(self._cleanup_bar)

        self._cleanup_count = QLabel("")
        self._cleanup_count.setStyleSheet("color: #666;")
        root.addWidget(self._cleanup_count)

        root.addSpacing(12)

        # Stage B: Cloud Sync
        self._sync_label = QLabel(self.tr("Cloud Sync"))
        sync_font = QFont()
        sync_font.setBold(True)
        self._sync_label.setFont(sync_font)
        self._sync_label.setStyleSheet("color: #999;")
        root.addWidget(self._sync_label)

        self._sync_bar = QProgressBar()
        self._sync_bar.setRange(0, 0)  # indeterminate
        self._sync_bar.setStyleSheet(_PROGRESS_STYLE)
        self._sync_bar.setMaximumWidth(600)
        self._sync_bar.setEnabled(False)
        root.addWidget(self._sync_bar)

        self._sync_status = QLabel(self.tr("Waiting for cleanup to complete\u2026"))
        self._sync_status.setStyleSheet("color: #999;")
        root.addWidget(self._sync_status)

        root.addSpacing(16)

        # Real-time log (collapsible)
        self._log_toggle = QPushButton(self.tr("\u25b6 Show Log"))
        self._log_toggle.setFlat(True)
        self._log_toggle.setStyleSheet("text-align: left; color: #0078d4;")
        self._log_toggle.clicked.connect(self._toggle_log)
        root.addWidget(self._log_toggle)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMaximumHeight(200)
        self._log_area.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px;"
            " background: #1e1e1e; color: #d4d4d4;"
            " border: 1px solid #333; border-radius: 4px;"
        )
        self._log_area.hide()
        root.addWidget(self._log_area)

        root.addStretch(2)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._minimize_btn = QPushButton(self.tr("Minimize to Tray"))
        self._minimize_btn.clicked.connect(self.minimize_requested)
        btn_row.addWidget(self._minimize_btn)

        self._done_btn = QPushButton(self.tr("Done"))
        self._done_btn.setMinimumHeight(36)
        self._done_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white;"
            " border: none; border-radius: 4px; padding: 6px 32px;"
            " font-weight: bold; }"
            " QPushButton:hover { background-color: #1b5e20; }"
        )
        self._done_btn.clicked.connect(self.done_requested)
        self._done_btn.hide()
        btn_row.addWidget(self._done_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

    # ── Executor signal slots ─────────────────────────────────────────

    @pyqtSlot()
    def on_execution_started(self) -> None:
        self._current = 0
        self._total = 0
        self._eta_start = None
        self._stage = "cleanup"
        self._finished = False
        self._cleanup_bar.setValue(0)
        self._cleanup_count.setText("")
        self._sync_bar.setEnabled(False)
        self._sync_status.setText(self.tr("Waiting for cleanup to complete\u2026"))
        self._sync_label.setStyleSheet("color: #999;")
        self._title.setText(self.tr("Executing plan\u2026"))
        self._done_btn.hide()
        self._minimize_btn.show()
        self._log_area.clear()
        self._eta_timer.start()

    @pyqtSlot(int, int)
    def on_progress_updated(self, current: int, total: int) -> None:
        self._current = current
        self._total = total

        if self._eta_start is None and current > 0:
            self._eta_start = time.monotonic()

        if total > 0:
            pct = min(100, int(current / total * 100))
            self._cleanup_bar.setValue(pct)

        self._refresh_cleanup_label()

    @pyqtSlot(str)
    def on_stage_changed(self, stage: str) -> None:
        self._stage = stage
        if stage == "sync":
            self._cleanup_bar.setValue(100)
            self._cleanup_bar.setStyleSheet(_PROGRESS_DONE_STYLE)
            self._cleanup_label.setStyleSheet("color: #2e7d32;")
            self._sync_bar.setEnabled(True)
            self._sync_bar.setRange(0, 0)  # indeterminate
            self._sync_label.setStyleSheet("font-weight: bold;")
            self._sync_status.setText(self.tr("Syncing\u2026"))
            self._sync_status.setStyleSheet("color: #666;")

    @pyqtSlot(str)
    def on_sync_substage(self, substage: str) -> None:
        """Update sync status label based on substage key from executor."""
        if substage == "compressing":
            self._sync_status.setText(self.tr("Compressing database\u2026"))
        elif substage.startswith("compressed:"):
            parts = substage.split(":")
            if len(parts) == 3:
                try:
                    raw = int(parts[1])
                    gz = int(parts[2])
                    if raw > 0:
                        pct = int((1 - gz / raw) * 100)
                        self._sync_status.setText(
                            self.tr("Compressed {0} \u2192 {1} ({2}% reduction)").format(
                                self._format_size(raw),
                                self._format_size(gz),
                                pct,
                            )
                        )
                except (ValueError, ZeroDivisionError):
                    pass
        elif substage == "uploading":
            self._sync_status.setText(
                self.tr("Uploading compressed data\u2026")
            )
        elif substage == "upload_skipped":
            self._sync_status.setText(
                self.tr("Upload skipped \u2014 data unchanged")
            )
        elif substage.startswith("downloading:"):
            peer = substage.split(":", 1)[1]
            self._sync_status.setText(
                self.tr("Downloading peer data: {0}\u2026").format(peer)
            )
        elif substage.startswith("decompressing:"):
            peer = substage.split(":", 1)[1]
            self._sync_status.setText(
                self.tr("Decompressing peer data: {0}\u2026").format(peer)
            )

    @pyqtSlot(str)
    def on_log_message(self, message: str) -> None:
        self._log_area.append(message)

    @pyqtSlot(int, int)
    def on_execution_complete(self, success: int, errors: int) -> None:
        self._eta_timer.stop()
        self._finished = True

        self._cleanup_bar.setValue(100)
        self._cleanup_bar.setStyleSheet(_PROGRESS_DONE_STYLE)
        self._cleanup_label.setStyleSheet("color: #2e7d32;")

        self._sync_bar.setRange(0, 100)
        self._sync_bar.setValue(100)
        self._sync_bar.setStyleSheet(_PROGRESS_DONE_STYLE)
        self._sync_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        self._sync_status.setText(self.tr("Complete"))
        self._sync_status.setStyleSheet("color: #2e7d32;")

        if errors > 0:
            self._title.setText(
                self.tr("Execution complete \u2014 {0} deleted, {1} errors").format(
                    success, errors
                )
            )
        else:
            self._title.setText(
                self.tr("Execution complete \u2014 {0} files deleted").format(success)
            )

        self._done_btn.show()
        self._minimize_btn.hide()

    @pyqtSlot(str, str)
    def on_execution_error(self, path: str, message: str) -> None:
        self._log_area.append(
            f'<span style="color:#e53935;">Error: {path} \u2014 {message}</span>'
        )

    # ── Internal ──────────────────────────────────────────────────────

    def _refresh_cleanup_label(self) -> None:
        eta_text = self._compute_eta()
        if eta_text:
            self._cleanup_count.setText(
                self.tr("{0} / {1} files \u2014 {2}").format(
                    self._current, self._total, eta_text
                )
            )
        else:
            self._cleanup_count.setText(
                self.tr("{0} / {1} files").format(self._current, self._total)
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
        if not self._finished:
            self._refresh_cleanup_label()

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

    @staticmethod
    def _format_size(n: int) -> str:
        """Format byte count as human-readable size."""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f} MB"
        if n >= 1_000:
            return f"{n / 1_000:.1f} KB"
        return f"{n} B"

    def _toggle_log(self) -> None:
        if self._log_area.isVisible():
            self._log_area.hide()
            self._log_toggle.setText(self.tr("\u25b6 Show Log"))
        else:
            self._log_area.show()
            self._log_toggle.setText(self.tr("\u25bc Hide Log"))
