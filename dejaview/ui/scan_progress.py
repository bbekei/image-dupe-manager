"""
ui/scan_progress.py — Unified multi-step scan progress panel.

Replaces the ResultsPanel in the splitter while a scan is running.
Shows an overall progress bar, per-phase step indicators with mini
progress bars, and a single ETA for the entire scanning process.

No tree model, no DB queries, no filter proxy — pure display widget.

The ResultsPanel is hidden during scanning and populated once when
the scan completes (or pauses), avoiding the O(N) incremental tree
update cost that caused UI freezes on large scans (70k+ files).
"""

import logging
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)

# Phase weights for overall progress computation.
_WEIGHTS_SIM = {"discovery": 0.05, "hashing": 0.55, "similarity": 0.35, "finalize": 0.05}
_WEIGHTS_NO_SIM = {"discovery": 0.05, "hashing": 0.90, "finalize": 0.05}

_ICON_PENDING = "\u25cb"   # empty circle
_ICON_ACTIVE = "\u25cf"    # filled circle
_ICON_COMPLETE = "\u2713"  # checkmark

_BAR_STYLE = (
    "QProgressBar { border: 1px solid #bbb; border-radius: 3px;"
    " background: #f0f0f0; text-align: center; }"
    " QProgressBar::chunk { background: #0078d4; border-radius: 2px; }"
)


class _StepRow:
    """One row in the step indicator list."""

    def __init__(self, name: str, parent: QWidget) -> None:
        self.widget = QWidget(parent)
        row = QHBoxLayout(self.widget)
        row.setContentsMargins(0, 2, 0, 2)

        self.icon = QLabel(_ICON_PENDING, self.widget)
        self.icon.setFixedWidth(20)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.icon)

        self.name_label = QLabel(name, self.widget)
        self.name_label.setFixedWidth(130)
        row.addWidget(self.name_label)

        self.mini_bar = QProgressBar(self.widget)
        self.mini_bar.setRange(0, 100)
        self.mini_bar.setValue(0)
        self.mini_bar.setFixedHeight(8)
        self.mini_bar.setFixedWidth(100)
        self.mini_bar.setTextVisible(False)
        self.mini_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #ccc; border-radius: 2px;"
            " background: #e8e8e8; }"
            " QProgressBar::chunk { background: #0078d4; border-radius: 1px; }"
        )
        self.mini_bar.hide()
        row.addWidget(self.mini_bar)

        self.status_text = QLabel("", self.widget)
        self.status_text.setStyleSheet("color: #666;")
        row.addWidget(self.status_text, stretch=1)

        self.set_pending()

    def set_pending(self) -> None:
        self.icon.setText(_ICON_PENDING)
        self.icon.setStyleSheet("color: #999; font-size: 12px;")
        self.name_label.setStyleSheet("color: #999; font-size: 13px;")
        self.status_text.setText("")
        self.status_text.setStyleSheet("color: #999; font-size: 12px;")
        self.mini_bar.hide()
        self.mini_bar.setValue(0)

    def set_active(self, text: str, progress_pct: int = -1) -> None:
        self.icon.setText(_ICON_ACTIVE)
        self.icon.setStyleSheet("color: #0078d4; font-size: 12px;")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.status_text.setText(text)
        self.status_text.setStyleSheet("color: #333; font-size: 12px;")
        if progress_pct >= 0:
            self.mini_bar.setValue(min(100, progress_pct))
            self.mini_bar.show()
        else:
            self.mini_bar.hide()

    def set_complete(self, text: str) -> None:
        self.icon.setText(_ICON_COMPLETE)
        self.icon.setStyleSheet("color: #2e7d32; font-size: 12px;")
        self.name_label.setStyleSheet("color: #2e7d32; font-size: 13px;")
        self.status_text.setText(text)
        self.status_text.setStyleSheet("color: #2e7d32; font-size: 12px;")
        self.mini_bar.hide()

    def set_visible(self, visible: bool) -> None:
        self.widget.setVisible(visible)


class ScanProgressWidget(QWidget):
    """Unified multi-step progress display shown during scanning."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Overall timing
        self._overall_start: float | None = None
        self._similarity_enabled: bool = False

        # Phase state — detected by signal arrival, not message keywords.
        self._phase = "idle"  # idle|discovery|hashing|similarity|finalize|complete

        # Per-phase counters
        self._discovery_count: int = 0
        self._hash_current: int = 0
        self._hash_total: int = 0
        self._sim_current: int = 0
        self._sim_total: int = 0

        # Completion flags
        self._discovery_done = False
        self._hashing_done = False
        self._similarity_done = False
        self._finalize_done = False

        self._build_ui()

        # 1-second timer for smooth ETA, decoupled from batched progress signals.
        self._eta_timer = QTimer(self)
        self._eta_timer.setInterval(1000)
        self._eta_timer.timeout.connect(self._on_eta_tick)

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 0, 40, 0)

        layout.addStretch(2)

        # Title
        self._title = QLabel(self.tr("Scanning in progress\u2026"), self)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self._title)

        layout.addSpacing(16)

        # Overall progress bar (range 0-1000 for 0.1% precision).
        self._overall_bar = QProgressBar(self)
        self._overall_bar.setRange(0, 1000)
        self._overall_bar.setValue(0)
        self._overall_bar.setMinimumWidth(300)
        self._overall_bar.setMaximumWidth(500)
        self._overall_bar.setStyleSheet(_BAR_STYLE + " QProgressBar { height: 20px; }")
        self._overall_bar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        bar_container = QWidget(self)
        bar_layout = QVBoxLayout(bar_container)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self._overall_bar)
        layout.addWidget(bar_container)

        layout.addSpacing(4)

        # ETA label
        self._eta_label = QLabel("", self)
        self._eta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._eta_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self._eta_label)

        layout.addSpacing(20)

        # Step indicator rows (centered container)
        steps_container = QWidget(self)
        steps_container.setMaximumWidth(460)
        steps_layout = QVBoxLayout(steps_container)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.setSpacing(2)

        self._step_discovery = _StepRow(self.tr("Discovery"), steps_container)
        steps_layout.addWidget(self._step_discovery.widget)

        self._step_hashing = _StepRow(self.tr("Hashing"), steps_container)
        steps_layout.addWidget(self._step_hashing.widget)

        self._step_similarity = _StepRow(self.tr("Similarity"), steps_container)
        steps_layout.addWidget(self._step_similarity.widget)

        self._step_finalize = _StepRow(self.tr("Finalize"), steps_container)
        steps_layout.addWidget(self._step_finalize.widget)

        steps_outer = QHBoxLayout()
        steps_outer.addStretch()
        steps_outer.addWidget(steps_container)
        steps_outer.addStretch()
        layout.addLayout(steps_outer)

        layout.addStretch(3)

    # ── Public API ────────────────────────────────────────────────────

    def set_similarity_enabled(self, enabled: bool) -> None:
        """Configure whether similarity steps are shown."""
        self._similarity_enabled = enabled
        self._step_similarity.set_visible(enabled)
        self._step_finalize.set_visible(enabled)

    # ── Scanner signal slots ─────────────────────────────────────────

    @pyqtSlot()
    def on_scan_started(self) -> None:
        self._phase = "discovery"
        self._overall_start = time.monotonic()
        self._discovery_count = 0
        self._hash_current = 0
        self._hash_total = 0
        self._sim_current = 0
        self._sim_total = 0
        self._discovery_done = False
        self._hashing_done = False
        self._similarity_done = False
        self._finalize_done = False

        self._overall_bar.setValue(0)
        self._title.setText(self.tr("Scanning in progress\u2026"))
        self._eta_label.setText("")

        self._step_discovery.set_active(self.tr("searching\u2026"))
        self._step_hashing.set_pending()
        self._step_similarity.set_pending()
        self._step_finalize.set_pending()

        if not self._eta_timer.isActive():
            self._eta_timer.start()

    @pyqtSlot(int, str)
    def on_file_discovered(self, file_id: int, path: str) -> None:
        self._discovery_count += 1
        # Throttle: update label every 500 files.
        if self._discovery_count % 500 == 0:
            self._step_discovery.set_active(
                self.tr("{0} files found").format(self._discovery_count)
            )

    @pyqtSlot(int, int)
    def on_progress_updated(self, current: int, total: int) -> None:
        """Pass 2 hashing progress."""
        # First call marks transition from discovery → hashing.
        if not self._discovery_done:
            self._discovery_done = True
            self._step_discovery.set_complete(
                self.tr("{0} files found").format(self._discovery_count)
            )

        self._phase = "hashing"
        self._hash_current = current
        self._hash_total = total

        self._refresh_all()

    @pyqtSlot(int, int)
    def on_similarity_progress(self, current: int, total: int) -> None:
        """Pass 3a similarity hashing progress."""
        # First call marks transition from hashing → similarity.
        if not self._hashing_done:
            self._hashing_done = True

        self._phase = "similarity"
        self._sim_current = current
        self._sim_total = total

        # When similarity hashing reaches 100%, transition to finalize.
        if current >= total and total > 0:
            self._similarity_done = True
            self._phase = "finalize"

        self._refresh_all()

    @pyqtSlot(int)
    def on_similarity_grouping_complete(self, group_count: int) -> None:
        """Pass 3c grouping done — finalize complete."""
        self._finalize_done = True
        self._refresh_all()

    @pyqtSlot(str)
    def on_status_message(self, message: str) -> None:
        """Kept for potential logging; phase detection uses signal arrival."""
        pass

    @pyqtSlot()
    def on_scan_complete(self) -> None:
        self._eta_timer.stop()
        self._phase = "complete"
        self._discovery_done = True
        self._hashing_done = True
        if self._similarity_enabled:
            self._similarity_done = True
            self._finalize_done = True

        self._overall_bar.setValue(1000)
        self._title.setText(self.tr("Scan complete"))

        # Show elapsed time.
        if self._overall_start is not None:
            elapsed = time.monotonic() - self._overall_start
            self._eta_label.setText(
                self.tr("Completed in {0}").format(self._format_duration(elapsed))
            )
        else:
            self._eta_label.setText("")

        # Mark all steps complete.
        self._step_discovery.set_complete(
            self.tr("{0} files found").format(self._discovery_count)
        )
        hash_text = (
            self.tr("{0} files").format(self._hash_total)
            if self._hash_total > 0
            else self.tr("complete")
        )
        self._step_hashing.set_complete(hash_text)
        if self._similarity_enabled:
            sim_text = (
                self.tr("{0} files").format(self._sim_total)
                if self._sim_total > 0
                else self.tr("complete")
            )
            self._step_similarity.set_complete(sim_text)
            self._step_finalize.set_complete(self.tr("complete"))

    @pyqtSlot()
    def on_scan_paused(self) -> None:
        self._eta_timer.stop()
        self._title.setText(self.tr("Scan paused"))

    @pyqtSlot()
    def on_scan_stopped(self) -> None:
        self._eta_timer.stop()
        self._title.setText(self.tr("Scan stopped"))

    # ── Internal ──────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        """Update all visual elements from current state."""
        self._update_step_indicators()

        overall = self._compute_overall_progress()
        self._overall_bar.setValue(int(overall * 1000))

        eta = self._compute_overall_eta()
        self._eta_label.setText(eta)

    def _update_step_indicators(self) -> None:
        # Discovery
        if self._discovery_done:
            self._step_discovery.set_complete(
                self.tr("{0} files found").format(self._discovery_count)
            )
        elif self._phase == "discovery":
            text = (
                self.tr("{0} files found").format(self._discovery_count)
                if self._discovery_count > 0
                else self.tr("searching\u2026")
            )
            self._step_discovery.set_active(text)

        # Hashing
        if self._hashing_done:
            self._step_hashing.set_complete(
                self.tr("{0} files").format(self._hash_total)
            )
        elif self._phase == "hashing" and self._hash_total > 0:
            pct = int(self._hash_current / self._hash_total * 100)
            self._step_hashing.set_active(
                self.tr("{0} / {1} files").format(
                    self._hash_current, self._hash_total
                ),
                progress_pct=pct,
            )

        if not self._similarity_enabled:
            return

        # Similarity
        if self._similarity_done:
            self._step_similarity.set_complete(
                self.tr("{0} files").format(self._sim_total)
            )
        elif self._phase == "similarity" and self._sim_total > 0:
            pct = int(self._sim_current / self._sim_total * 100)
            self._step_similarity.set_active(
                self.tr("{0} / {1} files").format(
                    self._sim_current, self._sim_total
                ),
                progress_pct=pct,
            )

        # Finalize
        if self._finalize_done:
            self._step_finalize.set_complete(self.tr("complete"))
        elif self._phase == "finalize":
            self._step_finalize.set_active(self.tr("processing\u2026"))

    def _compute_overall_progress(self) -> float:
        """Return 0.0..1.0 representing total scan progress."""
        w = _WEIGHTS_SIM if self._similarity_enabled else _WEIGHTS_NO_SIM
        progress = 0.0

        # Discovery: no total, so half weight while active, full when done.
        if self._discovery_done:
            progress += w["discovery"]
        elif self._phase == "discovery":
            progress += w["discovery"] * 0.5

        # Hashing: fractional.
        if self._hashing_done:
            progress += w["hashing"]
        elif self._hash_total > 0:
            progress += w["hashing"] * (self._hash_current / self._hash_total)

        if self._similarity_enabled:
            # Similarity hashing: fractional.
            if self._similarity_done:
                progress += w["similarity"]
            elif self._sim_total > 0:
                progress += w["similarity"] * (self._sim_current / self._sim_total)

            # Finalize: binary.
            if self._finalize_done:
                progress += w["finalize"]
            elif self._phase == "finalize":
                progress += w["finalize"] * 0.5
        else:
            # Without similarity, finalize weight is granted once hashing is done.
            if self._hashing_done:
                progress += w["finalize"]

        return min(1.0, progress)

    def _compute_overall_eta(self) -> str:
        if self._overall_start is None:
            return ""
        overall = self._compute_overall_progress()
        if overall <= 0.01:
            return ""
        elapsed = time.monotonic() - self._overall_start
        if elapsed <= 0:
            return ""
        estimated_total = elapsed / overall
        remaining = max(0, estimated_total - elapsed)
        return self.tr("~{0} left").format(self._format_duration(remaining))

    @pyqtSlot()
    def _on_eta_tick(self) -> None:
        self._refresh_all()

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
