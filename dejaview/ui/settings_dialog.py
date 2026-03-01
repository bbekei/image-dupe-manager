"""
ui/settings_dialog.py — Application Settings dialog.

Allows the user to change:
  - Language: Auto (system default), English, or Magyar (Hungarian)
  - Theme: System Default (placeholder for future themes)

Settings are persisted in the app_config table via Database.upsert_app_config().
"""

from PyQt6.QtCore import pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from data.db import Database


class SettingsDialog(QDialog):
    """Modal dialog for application-wide settings."""

    settings_saved = pyqtSignal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self.setWindowTitle(self.tr("Settings"))
        self.setMinimumWidth(380)

        self._build_ui()
        self._load_current()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Language combo box.
        self._lang_combo = QComboBox(self)
        self._lang_combo.addItem(self.tr("Auto (system default)"), "auto")
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("Magyar", "hu")
        form.addRow(self.tr("Language"), self._lang_combo)

        # Theme combo box (placeholder).
        self._theme_combo = QComboBox(self)
        self._theme_combo.addItem(self.tr("System Default"), "system")
        self._theme_combo.setEnabled(False)
        self._theme_combo.setToolTip(
            self.tr("Additional themes coming in a future release.")
        )
        form.addRow(self.tr("Theme"), self._theme_combo)

        # Theme hint label.
        hint = QLabel(
            self.tr("Additional themes coming in a future release."), self
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", hint)

        # Performance telemetry checkbox.
        self._perf_check = QCheckBox(
            self.tr("Enable performance telemetry"), self
        )
        self._perf_check.setObjectName("perf_check")
        self._perf_check.setToolTip(
            self.tr(
                "Log scan timing, lock contention, and signal rates to a CSV\n"
                "file in the DejaView data folder for diagnostics."
            )
        )
        form.addRow(self.tr("Diagnostics"), self._perf_check)

        perf_hint = QLabel(
            self.tr("CSV saved to %APPDATA%\\DejaView on next scan start."),
            self,
        )
        perf_hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", perf_hint)

        layout.addLayout(form)
        layout.addStretch()

        # Buttons.
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._save_btn = QPushButton(self.tr("Save"), self)
        self._save_btn.setObjectName("save_btn")
        self._cancel_btn = QPushButton(self.tr("Cancel"), self)
        self._cancel_btn.setObjectName("cancel_btn")

        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

        self._save_btn.clicked.connect(self._on_save)
        self._cancel_btn.clicked.connect(self.reject)

    def _load_current(self) -> None:
        """Load current settings from DB into the UI."""
        config = self._db.get_app_config()
        if config is None:
            return  # defaults already set in combo boxes

        lang = config["language"]
        for i in range(self._lang_combo.count()):
            if self._lang_combo.itemData(i) == lang:
                self._lang_combo.setCurrentIndex(i)
                break

        theme = config["theme"]
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == theme:
                self._theme_combo.setCurrentIndex(i)
                break

        try:
            self._perf_check.setChecked(bool(config["perf_logging"]))
        except (KeyError, TypeError):
            pass

    @pyqtSlot()
    def _on_save(self) -> None:
        """Save settings to DB and close."""
        new_lang = self._lang_combo.currentData()
        new_theme = self._theme_combo.currentData()

        # Check if language changed.
        config = self._db.get_app_config()
        old_lang = config["language"] if config else "auto"

        new_perf = 1 if self._perf_check.isChecked() else 0
        self._db.upsert_app_config(
            language=new_lang, theme=new_theme, perf_logging=new_perf
        )

        if new_lang != old_lang:
            QMessageBox.information(
                self,
                self.tr("Settings"),
                self.tr("Please restart DejaView to apply the new language."),
            )

        self.settings_saved.emit()
        self.accept()
