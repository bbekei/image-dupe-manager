# Feature Request Execution: Bottom Bar Height Fix

## Overview
Minimizing the ScanControl bottom bar so that the FolderPanel and ResultsPanel receive maximum
vertical space. See FEATURE_REQUEST_PLAN_LAYOUT_FIX.md for the full plan.

---

## Task Log

### Stage 1: Add Stretch Factors in MainWindow._build_central()

| # | Task | Status | Details |
|---|------|--------|---------|
| 1.1 | Add stretch factors to vertical layout | ✅ Done | Changed `layout.addWidget(self._splitter)` → `layout.addWidget(self._splitter, stretch=1)` and `layout.addWidget(self._scan_control)` → `layout.addWidget(self._scan_control, stretch=0)` in `ui/main_window.py` lines 143–146. |

---

### Stage 2: Set ScanControl Size Policy to Fixed Height

| # | Task | Status | Details |
|---|------|--------|---------|
| 2.1 | Add QSizePolicy import | ✅ Done | Added `QSizePolicy` to the existing `from PyQt6.QtWidgets import (...)` block in `ui/scan_control.py`. |
| 2.2 | Set vertical size policy to Fixed | ✅ Done | Added `self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)` as the first line of `ScanControl._build_ui()`. |

---

### Verification

| # | Task | Status | Details |
|---|------|--------|---------|
| V.1 | Existing unit tests pass | ✅ Done | `python -m pytest tests/unit/ --no-cov -q` — 151 passed, 10 skipped in 9.83s. No regressions. |
| V.2 | Manual visual check | ⬜ Pending | Launch `python main.py` and confirm bottom bar is a thin strip, resize window to verify bar height stays constant. |

---

## Files Changed (summary)

| Action | Path | Lines Changed |
|--------|------|---------------|
| **Modify** | `dejaview/ui/main_window.py` | Lines 143, 146: added `stretch=1` / `stretch=0` |
| **Modify** | `dejaview/ui/scan_control.py` | Import block: added `QSizePolicy`; `_build_ui()`: added `setSizePolicy(...)` |
