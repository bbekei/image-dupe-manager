"""
ui/help_dialog.py — User Guide dialog (Feature Request 1: Help Menu).

Displays the appropriate language user guide (Markdown) in a scrollable
QTextBrowser.  Language selection mirrors main.py._load_translators():
  - system locale prefix == 'hu'  →  USER_GUIDE_HU.md
  - any other locale              →  USER_GUIDE.md (English fallback)

If the localised file is missing, silently falls back to USER_GUIDE.md so
the dialog never raises an unhandled exception.
"""

import logging
from pathlib import Path

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

log = logging.getLogger(__name__)


class HelpDialog(QDialog):
    """
    Modal dialog that renders the user guide in the active UI language.

    Parameters
    ----------
    guide_dir : Path
        Directory containing USER_GUIDE.md and USER_GUIDE_HU.md.
        Passed from MainWindow so the caller controls resource location.
    parent : QWidget, optional
        Parent widget for Qt ownership.
    """

    def __init__(self, guide_dir: Path, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle(self.tr("User Guide"))
        self.setMinimumSize(800, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        # ── Language selection (same logic as main.py._load_translators) ──
        lang = QLocale.system().name()[:2]
        filename = "USER_GUIDE_HU.md" if lang == "hu" else "USER_GUIDE.md"
        guide_path = guide_dir / filename

        # Fallback: if localised file is missing, use English
        if not guide_path.exists():
            log.warning(
                "Guide file not found: %s — falling back to USER_GUIDE.md", guide_path
            )
            guide_path = guide_dir / "USER_GUIDE.md"

        try:
            text = guide_path.read_text(encoding="utf-8")
        except OSError:
            log.exception("Failed to read user guide from %s", guide_path)
            text = ""

        # ── Content browser ───────────────────────────────────────────────
        self._browser = QTextBrowser(self)
        self._browser.setOpenExternalLinks(True)
        self._browser.setMarkdown(text)

        # ── Close button ──────────────────────────────────────────────────
        close_btn = QPushButton(self.tr("Close"), self)
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        # ── Layout ────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.addWidget(self._browser, stretch=1)
        layout.addLayout(btn_row)
        self.setLayout(layout)
