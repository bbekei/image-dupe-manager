# Feature Request 1 — Help Menu: Progress Tracker

## Overall: 100% complete (5/5 stages done)

## Stages Checklist

| Stage | Status | Notes/Blockers | Completed By |
|-------|--------|----------------|--------------|
| **1 — Copy guide files into resources** | ✅ Done | `resources/help/` created; both guides byte-identical to originals | Task #1.1–1.4 |
| **2 — Implement `ui/help_dialog.py`** | ✅ Done | `HelpDialog(QDialog)` — `QTextBrowser.setMarkdown()`, language auto-detect, English fallback, min 800×600 | Task #2.1–2.2 |
| **3 — Add Help menu to `main_window.py`** | ✅ Done | `Help` menu added after Share; `_on_user_guide()` slot; import added | Task #3.1–3.2 |
| **4 — Update i18n files** | ✅ Done | 4 new strings in app.ts + app_hu.ts; `lrelease` compiled 125 translations (was 121) | Task #4.1–4.3 |
| **5 — Tests** | ✅ Done | 7 new tests — all pass (0.31 s) | Task #5.1–5.7 |

---

## Stage 1: Copy Guide Files — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 1.1 | Create `dejaview/resources/help/` directory | ✅ Done | `mkdir -p dejaview/resources/help/` |
| 1.2 | Copy `USER_GUIDE.md` from repo root | ✅ Done | `dejaview/resources/help/USER_GUIDE.md` |
| 1.3 | Copy `USER_GUIDE_HU.md` from repo root | ✅ Done | `dejaview/resources/help/USER_GUIDE_HU.md` |
| 1.4 | Verify files byte-for-byte identical | ✅ Done | `diff` exited 0 — "All files identical" |

---

## Stage 2: `ui/help_dialog.py` — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 2.1 | `HelpDialog(QDialog)` class | ✅ Done | 83 LOC — language detect via `QLocale.system().name()[:2]`, `QTextBrowser.setMarkdown()`, English fallback if HU file missing, min 800×600 |
| 2.2 | Import added to `main_window.py` | ✅ Done | `from ui.help_dialog import HelpDialog` |

### HelpDialog behaviour

| Component | Description |
|-----------|-------------|
| Language selection | `QLocale.system().name()[:2] == 'hu'` → `USER_GUIDE_HU.md`; else → `USER_GUIDE.md` |
| Fallback | If HU file absent: `log.warning(...)`, silently loads `USER_GUIDE.md` |
| Render | `QTextBrowser.setMarkdown(text)` — markdown rendered, links clickable |
| Layout | `QVBoxLayout`: browser (stretch=1) + right-aligned Close button row |
| Close | `QPushButton("Close")` → `self.accept()`; Escape / ✕ also close |
| Size | `setMinimumSize(800, 600)` + `Qt.WindowType.WindowMaximizeButtonHint` |

---

## Stage 3: Help Menu in `main_window.py` — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 3.1 | Help menu appended after Share in `_build_menu()` | ✅ Done | `mb.addMenu(self.tr("Help"))` + `addAction(self.tr("User Guide…"), self._on_user_guide)` at line 117 |
| 3.2 | `_on_user_guide()` slot | ✅ Done | Resolves `guide_dir` via `Path(__file__).resolve().parent.parent / "resources" / "help"`, opens `HelpDialog.exec()` |

---

## Stage 4: i18n Files — Detailed Breakdown

| # | Task | Status | Artifact |
|---|------|--------|----------|
| 4.1 | New strings in `app.ts` | ✅ Done | `Help`, `User Guide…` added to `<context name="MainWindow">`; new `<context name="HelpDialog">` with `User Guide` + `Close` |
| 4.2 | Hungarian translations in `app_hu.ts` | ✅ Done | `Súgó`, `Felhasználói kézikönyv…`, `Felhasználói kézikönyv`, `Bezárás` |
| 4.3 | Recompile `app_hu.qm` | ✅ Done | `lrelease` — 125 translations compiled (121 → 125; +4 new strings) |

### New i18n strings

| Source | Context | Hungarian |
|--------|---------|-----------|
| `Help` | `MainWindow` | Súgó |
| `User Guide…` | `MainWindow` | Felhasználói kézikönyv… |
| `User Guide` | `HelpDialog` | Felhasználói kézikönyv |
| `Close` | `HelpDialog` | Bezárás |

---

## Stage 5: Tests — Detailed Breakdown

| # | Test | Status | Coverage |
|---|------|--------|----------|
| 5.1 | `test_help_dialog_loads_english_guide_for_en_locale` | ✅ Pass | EN locale → USER_GUIDE.md content loaded |
| 5.2 | `test_help_dialog_loads_hungarian_guide_for_hu_locale` | ✅ Pass | HU locale → USER_GUIDE_HU.md content loaded |
| 5.3 | `test_help_dialog_falls_back_to_english_if_hu_guide_missing` | ✅ Pass | HU locale, no HU file → no exception, EN fallback |
| 5.4 | `test_help_dialog_close_button_closes_dialog` | ✅ Pass | Close button → `accepted` signal fired |
| 5.5 | `test_help_dialog_minimum_size` | ✅ Pass | `minimumWidth() ≥ 800`, `minimumHeight() ≥ 600` |
| 5.6 | `test_help_menu_exists_in_main_window_menubar` | ✅ Pass | "Help" present in menu bar actions |
| 5.7 | `test_user_guide_action_exists_in_help_menu` | ✅ Pass | "User Guide…" action present in Help menu |

---

## Regression Test Results

**After implementation — full suite with all stages complete:**

```
python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q
```

| Metric | Before feature | After feature |
|--------|---------------|---------------|
| Tests passed | 288 (baseline from EXECUTION.md Phase 6) | 301 |
| Tests added | — | +7 (new `test_help_dialog.py`) |
| Tests skipped | 10 | 10 |
| Tests failed | 3 (pre-existing) | 3 (same pre-existing) |
| Run time | ~8.4 s | ~9.5 s |

**Pre-existing failures** (present in original codebase, confirmed via `git stash`; unrelated to this feature):

- `test_regression_wf6_manual_export_import_round_trip[hash_only]`
- `test_regression_wf6_manual_export_import_round_trip[filename]`
- `test_regression_wf6_manual_export_import_round_trip[full_path]`

All 7 new Help-menu tests pass. No regressions introduced.

---

## Files Changed / Created

| Action | Path | Size |
|--------|------|------|
| **Created** | `dejaview/ui/help_dialog.py` | 83 LOC |
| **Created** | `dejaview/resources/help/USER_GUIDE.md` | copied from root |
| **Created** | `dejaview/resources/help/USER_GUIDE_HU.md` | copied from root |
| **Created** | `dejaview/tests/ui/test_help_dialog.py` | 7 tests, 112 LOC |
| **Modified** | `dejaview/ui/main_window.py` | +11 LOC (import, Help menu, slot) |
| **Modified** | `dejaview/resources/i18n/app.ts` | +14 lines (4 new source strings + HelpDialog context) |
| **Modified** | `dejaview/resources/i18n/app_hu.ts` | +18 lines (4 Hungarian translations + HelpDialog context) |
| **Regenerated** | `dejaview/resources/i18n/app_hu.qm` | 125 translations (was 121) |

---

## Local Commands

```bash
# Run help dialog tests only
cd dejaview && python -m pytest tests/ui/test_help_dialog.py --no-cov -v

# Run full test suite
cd dejaview && python -m pytest tests/unit/ tests/integration/ tests/ui/ --no-cov -q

# Recompile Hungarian QM after any .ts change
lrelease resources/i18n/app_hu.ts -qm resources/i18n/app_hu.qm
```
