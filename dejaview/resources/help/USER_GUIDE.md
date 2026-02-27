# DejaView Home Photo Manager — User Guide

## What This App Does

DejaView Home Photo Manager finds duplicate photos across your folders so you can see exactly where duplicates exist. It compares images by their visual content — so it catches duplicates even if files have been renamed, re-saved with different settings, or had their metadata changed.

You can also share your scan results with family members to find photos that exist across multiple people's libraries, without uploading the actual photos anywhere.

---

## Installation

### From the Installer (Recommended)

1. Download **DejaView_Setup.exe** from the releases page
2. Run the installer — it works with a standard user account (no administrator required)
3. Choose your preferred language (English or Hungarian) during setup
4. Optionally create a desktop shortcut
5. Click **Finish** to launch DejaView

The app installs to `C:\Users\<you>\AppData\Local\Programs\DejaView` by default. Your scan database and thumbnails are stored separately at `%APPDATA%\DejaView\`.

### Uninstalling

Use **Add or Remove Programs** in Windows Settings, or run the uninstaller from the Start menu group.

---

## The Interface

The main window has three areas:

```
┌────────────────────────────────────────────────────────┐
│ Menu: File | Scan | Share | Help                        │
├──────────────┬─────────────────────────────────────────┤
│ FOLDER PANEL │  RESULTS PANEL                          │
│              │  [All | Duplicates Only | Cross-Library] │
│ [+ Add...]   │                                         │
│ [- Remove]   │  Your scan results appear here          │
│              │                                         │
│ ▶ C:\Photos  │                                         │
│ ▶ Z:\Family  │                                         │
├──────────────┴─────────────────────────────────────────┤
│ [▶ Start] [⏸ Pause] [⏹ Stop]   ████░░░░ 47%  230/490  │
└────────────────────────────────────────────────────────┘
```

- **Folder panel** (left) — the folders you want to scan. During scanning, each folder shows a live file count (e.g. *120 files, 47 hashed*)
- **Results panel** (right) — files found, with duplicate badges
- **Scan bar** (bottom) — start, pause, stop controls and progress

---

## Step 1 — Add Folders

1. Click **+ Add...** in the folder panel, or go to **File > Add Folder**
2. A folder browser opens — navigate to your photo folder and click OK
3. The folder appears in the list

You can add as many folders as you like, from different drives or network shares (e.g. `Z:\Family Photos`). To remove a folder, select it and click **– Remove**.

---

## Step 2 — Scan

Click **▶ Start** in the bottom bar. The scan runs in two stages:

### Stage 1 — Discovery
The app walks through all added folders and finds every file. All files appear in the results panel immediately — before any duplicate checking begins. The progress bar shows *Discovering files...*

### Stage 2 — Duplicate Detection
The app checks which files could be duplicates and compares their visual content, processing one folder at a time starting from the deepest subfolders. As each folder completes, **● DUPLICATE** badges and **● DUPLICATED FOLDER** markers update immediately — you can start browsing completed folders while the rest of the scan continues. The folder panel shows live progress per root folder (e.g. *120 files, 47 hashed*), and the progress bar shows *230 / 490* style progress with an estimated time remaining.

> Files with no badge after the scan are unique — no visual duplicate was found anywhere in your scanned folders.

### Pause and Resume
Click **⏸ Pause** at any time. The current file finishes processing, then the scan stops. The status shows **PAUSED**. You can close the app — progress is saved. Reopen the app and click **▶ Resume** to continue from where you left off. Files already processed are not re-checked.

### Stop
Click **⏹ Stop** to end the scan permanently. Partial results remain visible.

### Downloaded Photos
Photos downloaded from the internet or received via email may carry a Windows security mark ("Mark of the Web") that can prevent the app from reading them. DejaView automatically removes this mark from image files during scanning so they can be processed normally.

> After scanning, the app automatically switches to the **Duplicates Only** view if any duplicates were found. The status bar shows a summary like: *Scan complete: 150 files scanned, 12 duplicates in 5 groups.*

---

## Step 3 — Review Results

After scanning, use the filter bar at the top of the results panel to choose what to see:

| Filter | Shows |
|--------|-------|
| **All** | Every file found in your scanned folders |
| **Duplicates Only** | Only files that have at least one duplicate |
| **Cross-Library** | Files that also exist in a synced family member's library |

Switch to **Duplicates Only** to focus on just the duplicates. Files remain shown in their original folder structure so you can see where each copy lives.

Select any file with a **● DUPLICATE** badge, then click the **Compare** button in the toolbar. You can also double-click the file, or right-click and choose **Compare Duplicates**.

When all files inside a folder are duplicates, the folder itself is shown with a **● DUPLICATED FOLDER** badge and a file count. You can expand the folder to see individual files, or compare the folder as a whole to see where the duplicated content exists.

---

## Step 4 — Compare Duplicates

The Compare View shows all copies of a duplicate group side by side in a read-only viewer:

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   [image]    │   │   [image]    │   │   [image]    │
│ C:\Photos\   │   │ Z:\Family\   │   │ D:\Backup\   │
│ beach.jpg    │   │ photo.jpg    │   │ img0041.jpg  │
│ 2.1 MB       │   │ 1.8 MB       │   │ 2.1 MB       │
│ 2023-06-15   │   │ 2023-07-30   │   │ 2023-06-15   │
└──────────────┘   └──────────────┘   └──────────────┘
                    [Close]
```

Each tile shows a thumbnail preview, the file's location, size, and modification date. This is a read-only view — use it to inspect where your duplicates live and compare their details. Click **Close** to return to the results panel.

If you compare a duplicated folder, the Compare View shows folder-level tiles with the folder path, total file count, and size. This makes it easy to identify and manage entire folder copies.

---

## Sharing with Family Members

You can share your scan fingerprints with trusted people to find photos duplicated across different libraries. **The actual photos are never uploaded anywhere.** Only compact fingerprints (and optionally filenames) leave your machine.

### Setting Up Google Drive Sync

One person in the group does the initial setup once:

1. Go to **Share > Configure Sync...**
2. Enter a display name (e.g. `alice`) — this labels your data in the shared folder
3. Click **Sign in with Google** — a browser window opens for authorization. The app only gets access to files it creates, not your full Google Drive.
4. In Google Drive's website, create a shared folder and share it with your family members. The app shows a direct link and brief instructions for this step.
5. Paste the shared folder's URL or ID into the app
6. Choose a **privacy level** for what you share with others:

   | Level | Shares |
   |-------|--------|
   | **Filename only** *(default)* | Fingerprints and filenames; full paths stay private |
   | **Hash only** | Fingerprints only; filenames and paths stay private |
   | **Full path** | Fingerprints and complete file paths |

7. Click **Save**

Each other person repeats steps 2–7 with their own display name, pointing at the same shared folder.

### After Setup

The app handles sync automatically:

- **On startup** — silently downloads everyone else's latest results in the background
- **After each scan** — uploads your updated results automatically
- **On close** — runs a final upload if anything changed

The status bar shows:
- `↕ Syncing...` — sync in progress
- `✓ Synced 2 min ago` — up to date

**If you are offline**, the status bar shows `⚠ Sync unavailable — showing last known data`. The Cross-Library view still shows results from the last successful sync. Your upload is queued and sent automatically next time you are online.

### Viewing Cross-Library Duplicates

Switch to the **Cross-Library** filter to see your photos that also exist in someone else's library.

In the Compare View, tiles from other people's libraries show their display name. All tiles are read-only — the Compare View is for inspecting and comparing duplicates across libraries.

### Managing Synced Libraries

Go to **Share > Manage Synced Libraries** to see all the people you are syncing with. You can remove any person at any time; their data is cleared from your local database.

---

## Manual Export / Import (No Google Drive)

If you prefer not to use Google Drive, you can share results as a file:

1. **Export** — go to **Share > Export Scan Results...**, enter a display name, and save the `.json` file. Send it by email or USB to the other person.
2. **Import** — go to **Share > Import Scan Results...** and open a `.json` file you received. Cross-library matches appear immediately.

The privacy level you configured in **Share > Configure Sync** also controls what is included in manually exported files.

---

## Settings

### Changing the Language

The app automatically uses Hungarian or English based on your Windows system
language. To override this, go to **File > Settings**, choose your preferred
language from the dropdown, and click **Save**. You will need to restart the
application for the change to take effect.

### Theme

A theme selector is available in the Settings dialog. Currently only the
system default theme is supported; additional themes are planned for a
future release.
