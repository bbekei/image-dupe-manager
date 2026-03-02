"""
tests/unit/test_navigation.py — Tests for NavigationController.
"""

import pytest
from PyQt6.QtWidgets import QStackedWidget, QWidget

from ui.navigation import NavigationController


@pytest.fixture
def nav(qtbot):
    """NavigationController with a QStackedWidget and three test screens."""
    stacked = QStackedWidget()
    qtbot.addWidget(stacked)
    controller = NavigationController(stacked)
    controller.register_screen("dashboard", QWidget())
    controller.register_screen("cleanup", QWidget())
    controller.register_screen("settings", QWidget())
    return controller


class TestNavigationController:

    def test_register_screen(self, nav):
        assert nav.screen_names() == ["dashboard", "cleanup", "settings"]

    def test_register_duplicate_raises(self, nav):
        with pytest.raises(ValueError, match="already registered"):
            nav.register_screen("dashboard", QWidget())

    def test_navigate_to_unknown_raises(self, nav):
        with pytest.raises(ValueError, match="Unknown screen"):
            nav.navigate_to("nonexistent")

    def test_navigate_to_sets_current(self, nav):
        nav.navigate_to("dashboard")
        assert nav.current_screen() == "dashboard"

    def test_navigate_emits_signal(self, nav, qtbot):
        with qtbot.waitSignal(nav.screen_changed, timeout=500) as blocker:
            nav.navigate_to("cleanup")
        assert blocker.args == ["cleanup"]

    def test_navigate_same_screen_noop(self, nav, qtbot):
        nav.navigate_to("dashboard")
        # Navigating to the same screen should not emit
        nav.navigate_to("dashboard")
        # No assertion on signal — just ensure no crash

    def test_back_stack_basic(self, nav):
        nav.navigate_to("dashboard")
        nav.navigate_to("cleanup")
        assert nav.can_go_back()
        nav.go_back()
        assert nav.current_screen() == "dashboard"
        assert not nav.can_go_back()

    def test_back_stack_multi(self, nav):
        nav.navigate_to("dashboard")
        nav.navigate_to("cleanup")
        nav.navigate_to("settings")
        assert nav.current_screen() == "settings"

        nav.go_back()
        assert nav.current_screen() == "cleanup"

        nav.go_back()
        assert nav.current_screen() == "dashboard"

        nav.go_back()  # empty stack — no-op
        assert nav.current_screen() == "dashboard"

    def test_navigate_push_back_false(self, nav):
        nav.navigate_to("dashboard")
        nav.navigate_to("cleanup", push_back=False)
        assert nav.current_screen() == "cleanup"
        assert not nav.can_go_back()

    def test_widget_for(self, nav):
        w = nav.widget_for("dashboard")
        assert isinstance(w, QWidget)

    def test_widget_for_unknown(self, nav):
        assert nav.widget_for("nonexistent") is None

    def test_initial_state(self, qtbot):
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        nav = NavigationController(stacked)
        assert nav.current_screen() is None
        assert not nav.can_go_back()
        assert nav.screen_names() == []
