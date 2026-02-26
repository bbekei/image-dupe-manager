# DejaView Home Photo Manager — Feature Request Plan: Bottom Bar Height Fix

## Overview

The **ScanControl** bar (buttons + progress bar) at the bottom of the main window currently
occupies too much vertical space, taking up nearly half the window height. This change minimizes
the bottom bar to its natural height so that the **FolderPanel** (left) and **ResultsPanel**
(right) above it receive maximum vertical space.

---

## Problem

The central widget's `QVBoxLayout` adds the `QSplitter` and `ScanControl` without explicit
stretch factors. Qt's default stretch behaviour gives both widgets equal weight, so the
`ScanControl` bar — which only needs ~40 px of height for one row of buttons and a progress bar —
expands to fill roughly half the window.

---

## Solution

Two complementary changes that together guarantee the bottom bar stays compact:

1. **Set stretch factors on the vertical layout** in `MainWindow._build_central()`:
   - Give the splitter a stretch factor of **1** (takes all available space).
   - Give the scan control a stretch factor of **0** (stays at its natural size).

2. **Fix the ScanControl's vertical size policy** in `ScanControl._build_ui()`:
   - Set `self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)` so the
     widget reports a fixed vertical size to Qt's layout engine.

---

## User Experience

### Before

```
┌──────────────────────────────────────────────┐
│  Menu bar                                    │
├─────────────┬────────────────────────────────┤
│             │                                │
│  Folders    │  Results / Compare             │  ≈ 50%
│             │                                │
├─────────────┴────────────────────────────────┤
│                                              │
│  ▶ Start  ⏸ Pause  ⏹ Stop  [████░░░] 3/10  │  ≈ 50%
│                                              │
├──────────────────────────────────────────────┤
│  Status bar                                  │
└──────────────────────────────────────────────┘
```

### After

```
┌──────────────────────────────────────────────┐
│  Menu bar                                    │
├─────────────┬────────────────────────────────┤
│             │                                │
│             │                                │
│  Folders    │  Results / Compare             │  ≈ 95%
│             │                                │
│             │                                │
├─────────────┴────────────────────────────────┤
│  ▶ Start  ⏸ Pause  ⏹ Stop  [████░░░] 3/10  │  ≈ 5%
├──────────────────────────────────────────────┤
│  Status bar                                  │
└──────────────────────────────────────────────┘
```

---

## Requirements

| # | Requirement |
|---|-------------|
| L.1 | The ScanControl bar occupies only its natural height (~40 px), not half the window |
| L.2 | The splitter (FolderPanel + ResultsPanel) fills all remaining vertical space |
| L.3 | No visual or functional regression — buttons, progress bar, and status label work identically |
| L.4 | No new files are created; only existing files are modified |

---

## Architecture

### Modified files

| File | Change |
|------|--------|
| `ui/main_window.py` | Add stretch factors to the vertical layout in `_build_central()` |
| `ui/scan_control.py` | Set vertical size policy to `Fixed` in `_build_ui()` |

No new files, no i18n changes, no test changes required.

---

## Development Stages

### Stage 1 — Add stretch factors in `MainWindow._build_central()`

**Task 1.1** — In `ui/main_window.py`, method `_build_central()`, after the two `layout.addWidget()`
calls (lines 143–146), add stretch factors:

Change:

```python
layout.addWidget(self._splitter)

self._scan_control = ScanControl(parent=self)
layout.addWidget(self._scan_control)
```

To:

```python
layout.addWidget(self._splitter, stretch=1)

self._scan_control = ScanControl(parent=self)
layout.addWidget(self._scan_control, stretch=0)
```

This tells the layout engine to give all stretchable space to the splitter and none to the
scan control.

---

### Stage 2 — Set ScanControl size policy to Fixed height

**Task 2.1** — In `ui/scan_control.py`, method `_build_ui()`, add a size-policy import and call
at the top of the method (before the existing layout code):

Add to the existing import block:

```python
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,          # ← add
    QWidget,
)
```

Then at the start of `_build_ui()`:

```python
def _build_ui(self) -> None:
    self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    layout = QHBoxLayout(self)
    ...
```

This ensures the widget never grows beyond its natural height hint regardless of how much space
the parent layout offers.

---

## Verification

After both stages are complete, verify:

1. **Visual check:**
   - Launch the app: `cd dejaview && python main.py`
   - The bottom bar should be a thin strip (~40 px high) with buttons and progress bar.
   - The folder tree and results panel should fill the rest of the window.
   - Resize the window — the bottom bar height should stay constant.

2. **Functional check:**
   - Add a folder, start a scan — buttons toggle correctly, progress bar fills, status label
     updates.
   - Pause, resume, stop — all button states transition correctly.

3. **Existing tests still pass:**
   ```bash
   cd dejaview
   python -m pytest tests/unit/ --no-cov -q
   ```

---

## Files Changed (summary)

| Action | Path |
|--------|------|
| **Modify** | `dejaview/ui/main_window.py` — add `stretch=1` / `stretch=0` to layout |
| **Modify** | `dejaview/ui/scan_control.py` — add `QSizePolicy.Policy.Fixed` vertical policy |
