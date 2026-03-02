"""
ui/tray.py — System tray icon for DejaView (UX Redesign Phase 3).

Minimal QSystemTrayIcon: shown during background execution,
balloon notification on completion, click to restore window.
"""

import logging

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon

log = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    """System tray icon for minimized execution progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("DejaView")
        # Use the app window icon if available, otherwise a default
        if parent and parent.windowIcon() and not parent.windowIcon().isNull():
            self.setIcon(parent.windowIcon())
        else:
            self.setIcon(QIcon.fromTheme("applications-graphics"))

    def show_progress(self, message: str) -> None:
        """Show the tray icon with a tooltip message."""
        self.setToolTip(f"DejaView — {message}")
        self.show()

    def notify_complete(self, message: str) -> None:
        """Show a balloon notification when execution finishes."""
        if self.supportsMessages():
            self.showMessage("DejaView", message, QSystemTrayIcon.MessageIcon.Information, 5000)
        self.setToolTip(f"DejaView — {message}")
