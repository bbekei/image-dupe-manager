"""
ui/navigation.py — Lightweight navigation controller for DejaView.

Wraps a QStackedWidget and maintains a back-stack so every screen
can return to the previous one (typically the Dashboard).

Usage:
    stacked = QStackedWidget()
    nav = NavigationController(stacked)
    nav.register_screen("dashboard", dashboard_widget)
    nav.register_screen("cleanup", cleanup_widget)
    nav.navigate_to("dashboard")
"""

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from PyQt6.QtWidgets import QStackedWidget

log = logging.getLogger(__name__)


class NavigationController(QObject):
    """Manages screen transitions via a QStackedWidget with back-stack.

    Signals:
        screen_changed(str): emitted after every navigation with the new screen name.
    """

    screen_changed = pyqtSignal(str)

    def __init__(self, stacked_widget: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack = stacked_widget
        self._screens: dict[str, int] = {}   # name → stack index
        self._back_stack: list[str] = []      # history (excludes current)
        self._current: str | None = None

    # ── Registration ──────────────────────────────────────────────────

    def register_screen(self, name: str, widget) -> None:
        """Add a widget to the stacked widget and register it under *name*.

        Raises ValueError if *name* is already registered.
        """
        if name in self._screens:
            raise ValueError(f"Screen '{name}' is already registered")
        idx = self._stack.addWidget(widget)
        self._screens[name] = idx
        log.debug("Registered screen '%s' at index %d", name, idx)

    # ── Navigation ────────────────────────────────────────────────────

    def navigate_to(self, name: str, *, push_back: bool = True) -> None:
        """Switch to the screen registered as *name*.

        If *push_back* is True (default) the current screen is pushed onto
        the back-stack so that ``go_back()`` can return to it.
        """
        if name not in self._screens:
            raise ValueError(f"Unknown screen '{name}'")
        if name == self._current:
            return  # Already there

        if push_back and self._current is not None:
            self._back_stack.append(self._current)

        self._current = name
        self._stack.setCurrentIndex(self._screens[name])
        self.screen_changed.emit(name)
        log.debug("Navigated to '%s' (back-stack depth: %d)",
                  name, len(self._back_stack))

    def go_back(self) -> None:
        """Return to the previous screen on the back-stack.

        If the stack is empty this is a no-op.
        """
        if not self._back_stack:
            return
        previous = self._back_stack.pop()
        self.navigate_to(previous, push_back=False)

    # ── Queries ───────────────────────────────────────────────────────

    def current_screen(self) -> str | None:
        """Return the name of the currently visible screen, or None."""
        return self._current

    def can_go_back(self) -> bool:
        """Return True if the back-stack is non-empty."""
        return len(self._back_stack) > 0

    def screen_names(self) -> list[str]:
        """Return all registered screen names (insertion order)."""
        return list(self._screens.keys())

    def widget_for(self, name: str):
        """Return the QWidget registered under *name*, or None."""
        idx = self._screens.get(name)
        if idx is None:
            return None
        return self._stack.widget(idx)
