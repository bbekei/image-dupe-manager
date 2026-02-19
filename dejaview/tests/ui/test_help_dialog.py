"""
tests/ui/test_help_dialog.py — UI tests for ui/help_dialog.py.
Feature Request 1: Help Menu — plan §Stage 5 Tests.

Tests cover:
  - Language-based guide file selection (en / hu)
  - Fallback to English when localised file is missing
  - Close button dismisses the dialog
  - Minimum size enforced
  - Help menu presence in MainWindow menu bar
  - User Guide action presence in Help menu
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ui.help_dialog import HelpDialog
from ui.main_window import MainWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EN_MARKER = "English User Guide Content — unique en marker"
_HU_MARKER = "Magyar Felhasználói kézikönyv — egyedi jelölő"


@pytest.fixture
def guide_dir(tmp_path: Path) -> Path:
    """Temp directory with both guide files containing unique marker text."""
    d = tmp_path / "help"
    d.mkdir()
    (d / "USER_GUIDE.md").write_text(
        f"# User Guide\n\n{_EN_MARKER}\n", encoding="utf-8"
    )
    (d / "USER_GUIDE_HU.md").write_text(
        f"# Felhasználói kézikönyv\n\n{_HU_MARKER}\n", encoding="utf-8"
    )
    return d


@pytest.fixture
def guide_dir_en_only(tmp_path: Path) -> Path:
    """Temp directory with only the English guide (no HU file)."""
    d = tmp_path / "help_en"
    d.mkdir()
    (d / "USER_GUIDE.md").write_text(
        f"# User Guide\n\n{_EN_MARKER}\n", encoding="utf-8"
    )
    return d


# ---------------------------------------------------------------------------
# Tests 5.1 – 5.5: HelpDialog widget
# ---------------------------------------------------------------------------

def test_help_dialog_loads_english_guide_for_en_locale(qtbot, guide_dir):
    # FR1 §Task 5.1 — English locale → USER_GUIDE.md content shown
    with patch("ui.help_dialog.QLocale") as mock_locale_cls:
        mock_locale_cls.system.return_value.name.return_value = "en_US"
        dlg = HelpDialog(guide_dir=guide_dir)
        qtbot.addWidget(dlg)

    plain = dlg._browser.toPlainText()
    assert _EN_MARKER in plain, f"Expected English marker in browser text, got: {plain[:200]}"
    assert _HU_MARKER not in plain


def test_help_dialog_loads_hungarian_guide_for_hu_locale(qtbot, guide_dir):
    # FR1 §Task 5.2 — Hungarian locale → USER_GUIDE_HU.md content shown
    with patch("ui.help_dialog.QLocale") as mock_locale_cls:
        mock_locale_cls.system.return_value.name.return_value = "hu_HU"
        dlg = HelpDialog(guide_dir=guide_dir)
        qtbot.addWidget(dlg)

    plain = dlg._browser.toPlainText()
    assert _HU_MARKER in plain, f"Expected HU marker in browser text, got: {plain[:200]}"
    assert _EN_MARKER not in plain


def test_help_dialog_falls_back_to_english_if_hu_guide_missing(qtbot, guide_dir_en_only):
    # FR1 §Task 5.3 — HU locale but no HU file → English fallback, no exception
    with patch("ui.help_dialog.QLocale") as mock_locale_cls:
        mock_locale_cls.system.return_value.name.return_value = "hu_HU"
        dlg = HelpDialog(guide_dir=guide_dir_en_only)
        qtbot.addWidget(dlg)

    plain = dlg._browser.toPlainText()
    assert _EN_MARKER in plain, (
        f"Expected English fallback marker in browser text, got: {plain[:200]}"
    )


def test_help_dialog_close_button_closes_dialog(qtbot, guide_dir):
    # FR1 §Task 5.4 — Close button dismisses dialog with Accepted result
    with patch("ui.help_dialog.QLocale") as mock_locale_cls:
        mock_locale_cls.system.return_value.name.return_value = "en_US"
        dlg = HelpDialog(guide_dir=guide_dir)
        qtbot.addWidget(dlg)

    # Find the Close button (text == "Close")
    from PyQt6.QtWidgets import QPushButton
    buttons = dlg.findChildren(QPushButton)
    close_btn = next(b for b in buttons if b.text() == "Close")

    with qtbot.waitSignal(dlg.accepted, timeout=2_000):
        close_btn.click()


def test_help_dialog_minimum_size(qtbot, guide_dir):
    # FR1 §Task 5.5 — Dialog enforces minimum 800 × 600
    with patch("ui.help_dialog.QLocale") as mock_locale_cls:
        mock_locale_cls.system.return_value.name.return_value = "en_US"
        dlg = HelpDialog(guide_dir=guide_dir)
        qtbot.addWidget(dlg)

    assert dlg.minimumWidth() >= 800
    assert dlg.minimumHeight() >= 600


# ---------------------------------------------------------------------------
# Tests 5.6 – 5.7: Help menu in MainWindow
# ---------------------------------------------------------------------------

@pytest.fixture
def win(qtbot, db, thumb_dir):
    """MainWindow with a fresh DB (no session)."""
    w = MainWindow(db=db, thumb_dir=thumb_dir)
    qtbot.addWidget(w)
    return w


def test_help_menu_exists_in_main_window_menubar(win):
    # FR1 §Task 5.6 — "Help" menu is present in the menu bar
    mb = win.menuBar()
    menu_titles = [action.text() for action in mb.actions()]
    assert "Help" in menu_titles, (
        f"Expected 'Help' in menu bar titles, got: {menu_titles}"
    )


def test_user_guide_action_exists_in_help_menu(win):
    # FR1 §Task 5.7 — Help menu contains a "User Guide…" action
    mb = win.menuBar()
    help_action = next(
        (a for a in mb.actions() if a.text() == "Help"), None
    )
    assert help_action is not None, "Help menu not found in menu bar"

    help_menu = help_action.menu()
    assert help_menu is not None

    action_texts = [a.text() for a in help_menu.actions()]
    assert any(t.startswith("User Guide") for t in action_texts), (
        f"Expected 'User Guide…' action in Help menu, got: {action_texts}"
    )
