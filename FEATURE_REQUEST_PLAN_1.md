# DejaView Home Photo Manager — Feature Request Plan 1: Help Menu

## Overview

Add a **Help** menu to the application's menu bar containing a **User Guide** action. Clicking the
action opens a scrollable dialog that displays the user guide in the language that matches the
user's current UI language: `USER_GUIDE.md` for English, `USER_GUIDE_HU.md` for Hungarian. The
guide files are moved into the application resource tree so they are bundled by the existing
PyInstaller pipeline without extra configuration.

---

## User Experience

### Workflow: Opening the User Guide

**Step 1 — Access Help**

The user clicks the **Help** menu in the menu bar. The menu bar now reads:

```
File | View | Scan | Share | Help
```

The Help menu contains one item:

```
┌─────────────────────────┐
│  User Guide…            │
└─────────────────────────┘
```

**Step 2 — User Guide dialog opens**

A resizable modal dialog appears (minimum 800 × 600 px), titled **"User Guide"**
(or **"Felhasználói kézikönyv"** in Hungarian). The dialog displays the full guide content
rendered from Markdown using `QTextBrowser.setMarkdown()`. A scrollbar appears if the content
exceeds the visible area. A **Close** button sits at the bottom right.

**Step 3 — Language selection is automatic**

The guide displayed always matches the active UI language:

| System locale | Guide file shown |
|---------------|-----------------|
| `hu` (Hungarian) | `USER_GUIDE_HU.md` |
| Any other locale | `USER_GUIDE.md` |

The language check uses the same `QLocale.system().name()[:2]` logic already used by
`main.py._load_translators()`, so the guide language is consistent with the UI language.

**Step 4 — Closing the dialog**

The user clicks **Close** (or presses Escape / the window's ✕ button). The dialog closes. The
main window remains open and unchanged.

---

## Requirements

| # | Requirement |
|---|-------------|
| H.1 | A **Help** menu appears as the last item in the menu bar (after Share) |
| H.2 | The Help menu contains exactly one action: **User Guide…** |
| H.3 | Clicking User Guide… opens a modal dialog showing the guide content |
| H.4 | The guide is displayed in the user's UI language (Hungarian or English) |
| H.5 | The dialog is scrollable and resizable; minimum size 800 × 600 px |
| H.6 | The guide files are bundled with the application installer |
| H.7 | All new UI strings use `self.tr()` and are covered by i18n files |

---

## Architecture

### New file

```
dejaview/
└── ui/
    └── help_dialog.py     ← new; HelpDialog(QDialog)
```

### Modified files

| File | Change |
|------|--------|
| `ui/main_window.py` | Add Help menu + `_on_user_guide()` slot in `_build_menu()` |
| `resources/i18n/app.ts` | Add new source strings: "Help", "User Guide…", "Close" |
| `resources/i18n/app_hu.ts` | Add Hungarian translations for the three new strings |
| `resources/i18n/app_hu.qm` | Recompile from updated `app_hu.ts` |

### New resource files (copied from project root)

```
dejaview/
└── resources/
    └── help/
        ├── USER_GUIDE.md
        └── USER_GUIDE_HU.md
```

The source files `USER_GUIDE.md` and `USER_GUIDE_HU.md` at the repository root are **copied** (not
moved) into `dejaview/resources/help/` so the existing files stay discoverable in the repo while
the app bundles its own copy.

### HelpDialog class signature

```python
# ui/help_dialog.py
class HelpDialog(QDialog):
    def __init__(self, guide_dir: Path, parent=None) -> None:
        ...
```

`guide_dir` is passed in from `MainWindow._on_user_guide()` as
`Path(__file__).resolve().parent.parent / "resources" / "help"`, following the same pattern used
for `i18n_dir` in `main.py`.

### Language detection inside HelpDialog

```python
from PyQt6.QtCore import QLocale

lang = QLocale.system().name()[:2]
filename = "USER_GUIDE_HU.md" if lang == "hu" else "USER_GUIDE.md"
guide_path = guide_dir / filename
```

This is intentionally the same two-line check as `main.py._load_translators()` to ensure the
guide language is always consistent with the installed translator.

---

## Development Stages

### Stage 1 — Copy user guide files into resources

**Task 1.1** — Create the directory `dejaview/resources/help/`.

**Task 1.2** — Copy `USER_GUIDE.md` (repository root) to
`dejaview/resources/help/USER_GUIDE.md`.

**Task 1.3** — Copy `USER_GUIDE_HU.md` (repository root) to
`dejaview/resources/help/USER_GUIDE_HU.md`.

**Task 1.4** — Verify both files are byte-for-byte identical to the originals.

---

### Stage 2 — Implement `ui/help_dialog.py`

**Task 2.1** — Create `dejaview/ui/help_dialog.py` with class `HelpDialog(QDialog)`.

Constructor behaviour:
1. Call `super().__init__(parent)`.
2. Set the window title with `self.tr("User Guide")`.
3. Determine `filename` via `QLocale.system().name()[:2]`:
   - `"hu"` → `"USER_GUIDE_HU.md"`
   - anything else → `"USER_GUIDE.md"`
4. Build `guide_path = guide_dir / filename`.
5. Read `guide_path` as UTF-8 text; if the file is missing, fall back to
   `"USER_GUIDE.md"` silently (do not raise; display English content as fallback).
6. Create a `QTextBrowser` widget, call `.setMarkdown(text)` to render the guide.
7. Create a `QPushButton` labelled `self.tr("Close")` that calls `self.accept()`.
8. Lay out using `QVBoxLayout`: `QTextBrowser` (stretch=1) then the Close button (right-aligned
   via `QHBoxLayout` with a leading stretch).
9. Set minimum size to 800 × 600.
10. Set `Qt.WindowType.Window` so the dialog is independently resizable.

**Task 2.2** — Add the `from ui.help_dialog import HelpDialog` import to `ui/main_window.py`.

---

### Stage 3 — Add Help menu to `ui/main_window.py`

**Task 3.1** — In `MainWindow._build_menu()` (currently ends at line 114), append after the
Share menu block:

```python
# Help
help_menu = mb.addMenu(self.tr("Help"))
help_menu.addAction(self.tr("User Guide\u2026"), self._on_user_guide)
```

**Task 3.2** — Add the slot method `_on_user_guide()` to `MainWindow`:

```python
@pyqtSlot()
def _on_user_guide(self) -> None:
    guide_dir = Path(__file__).resolve().parent.parent / "resources" / "help"
    dlg = HelpDialog(guide_dir=guide_dir, parent=self)
    dlg.exec()
```

> Note: `_base_dir()` is defined in `main.py` and is not importable from `ui/` without a
> circular dependency. The equivalent `Path(__file__).resolve().parent.parent` resolves to the
> same `dejaview/` root from within `ui/main_window.py`. This matches how other modules compute
> resource paths.

---

### Stage 4 — Update i18n files

**Task 4.1** — Add the following `<message>` blocks to the `<context name="MainWindow">`
section of `dejaview/resources/i18n/app.ts`:

```xml
<message>
    <source>Help</source>
    <translation type="unfinished"></translation>
</message>
<message>
    <source>User Guide&#x2026;</source>
    <translation type="unfinished"></translation>
</message>
```

Append a new `<context name="HelpDialog">` block after the ShareDialog context:

```xml
<context>
    <name>HelpDialog</name>
    <message>
        <source>User Guide</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <source>Close</source>
        <translation type="unfinished"></translation>
    </message>
</context>
```

**Task 4.2** — Add the corresponding `<message>` blocks to `dejaview/resources/i18n/app_hu.ts`.

In `<context name="MainWindow">`:

```xml
<message>
    <source>Help</source>
    <translation>Súgó</translation>
</message>
<message>
    <source>User Guide&#x2026;</source>
    <translation>Felhasználói kézikönyv…</translation>
</message>
```

Append a new `<context name="HelpDialog">` block after the ShareDialog context:

```xml
<!-- ═══════════════════════════════════════════════════════════════════════
     HelpDialog (ui/help_dialog.py)
     ═══════════════════════════════════════════════════════════════════════ -->
<context>
    <name>HelpDialog</name>
    <message>
        <source>User Guide</source>
        <translation>Felhasználói kézikönyv</translation>
    </message>
    <message>
        <source>Close</source>
        <translation>Bezárás</translation>
    </message>
</context>
```

**Task 4.3** — Recompile the binary translation file:

```bash
cd dejaview
lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm
```

Verify: the command exits with code 0 and `app_hu.qm` is updated (newer mtime).

---

### Stage 5 — Tests

File: `tests/ui/test_help_dialog.py`

**Task 5.1** — `test_help_dialog_loads_english_guide_for_en_locale(qtbot, tmp_path)`

```
Given: USER_GUIDE.md and USER_GUIDE_HU.md exist in a tmp guide_dir
       QLocale.system().name() is mocked to return "en_US"
When:  HelpDialog(guide_dir) is constructed
Then:  The QTextBrowser's toPlainText() contains text from USER_GUIDE.md (not USER_GUIDE_HU.md)
```

**Task 5.2** — `test_help_dialog_loads_hungarian_guide_for_hu_locale(qtbot, tmp_path)`

```
Given: USER_GUIDE.md and USER_GUIDE_HU.md exist in a tmp guide_dir
       QLocale.system().name() is mocked to return "hu_HU"
When:  HelpDialog(guide_dir) is constructed
Then:  The QTextBrowser's toPlainText() contains text from USER_GUIDE_HU.md
```

**Task 5.3** — `test_help_dialog_falls_back_to_english_if_hu_guide_missing(qtbot, tmp_path)`

```
Given: Only USER_GUIDE.md exists in guide_dir (USER_GUIDE_HU.md is absent)
       QLocale.system().name() is mocked to return "hu_HU"
When:  HelpDialog(guide_dir) is constructed
Then:  No exception is raised
       The QTextBrowser's toPlainText() contains text from USER_GUIDE.md
```

**Task 5.4** — `test_help_dialog_close_button_closes_dialog(qtbot, tmp_path)`

```
Given: HelpDialog is open
When:  The Close button is clicked
Then:  The dialog's result() == QDialog.DialogCode.Accepted
       The dialog is no longer visible
```

**Task 5.5** — `test_help_dialog_minimum_size(qtbot, tmp_path)`

```
Given: HelpDialog is constructed
Then:  dialog.minimumWidth() >= 800
       dialog.minimumHeight() >= 600
```

**Task 5.6** — `test_help_menu_exists_in_main_window_menubar(qtbot, db, tmp_path)`

```
Given: MainWindow is constructed
Then:  A menu titled "Help" exists in the menu bar
```

**Task 5.7** — `test_user_guide_action_exists_in_help_menu(qtbot, db, tmp_path)`

```
Given: MainWindow is constructed
Then:  The Help menu contains an action whose text starts with "User Guide"
```

---

## i18n Summary

| String | Context | English | Hungarian |
|--------|---------|---------|-----------|
| `Help` | `MainWindow` | Help | Súgó |
| `User Guide…` | `MainWindow` | User Guide… | Felhasználói kézikönyv… |
| `User Guide` | `HelpDialog` | User Guide | Felhasználói kézikönyv |
| `Close` | `HelpDialog` | Close | Bezárás |

---

## Verification

After all stages are complete, verify end-to-end:

1. **Unit / UI tests pass:**
   ```bash
   cd dejaview
   python -m pytest tests/ui/test_help_dialog.py --no-cov -v
   python -m pytest tests/unit/ tests/integration/ --no-cov -q
   ```

2. **Manual smoke test (English):**
   - Launch the app with a non-Hungarian system locale
   - Click Help → User Guide… — the dialog opens with English content
   - Scroll through the guide to confirm it renders without error
   - Click Close — dialog closes, main window is unchanged

3. **Manual smoke test (Hungarian):**
   - Launch the app with system locale set to `hu`
   - Click Súgó → Felhasználói kézikönyv… — the dialog opens in Hungarian
   - Confirm the title bar reads "Felhasználói kézikönyv"

4. **i18n compilation check:**
   ```bash
   lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm
   ```
   Must exit 0 with no warnings about missing translations.

5. **PyInstaller bundle check** (optional, if building):
   - Ensure `dejaview/resources/help/` is included in the PyInstaller `.spec` `datas` list
   - Verify `USER_GUIDE.md` and `USER_GUIDE_HU.md` are present in the bundle's `resources/help/`
   - Open the packaged app and confirm Help → User Guide… works

---

## Files Changed / Created (summary)

| Action | Path |
|--------|------|
| **Create** | `dejaview/ui/help_dialog.py` |
| **Create** | `dejaview/resources/help/USER_GUIDE.md` (copied from root) |
| **Create** | `dejaview/resources/help/USER_GUIDE_HU.md` (copied from root) |
| **Create** | `dejaview/tests/ui/test_help_dialog.py` |
| **Modify** | `dejaview/ui/main_window.py` — add Help menu + `_on_user_guide()` slot |
| **Modify** | `dejaview/resources/i18n/app.ts` — add 4 new source strings |
| **Modify** | `dejaview/resources/i18n/app_hu.ts` — add 4 Hungarian translations |
| **Regenerate** | `dejaview/resources/i18n/app_hu.qm` — recompile from updated `.ts` |
