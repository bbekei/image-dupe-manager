# DejaView — User Guide

## What This App Does

DejaView finds duplicate and visually similar photos across your folders. It compares images by their visual content — so it catches duplicates even if files have been renamed, re-saved with different settings, or had their metadata changed.

You can also share your scan fingerprints with family members to find photos that exist across multiple people's libraries, without uploading the actual photos anywhere.

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

The main window has a **sidebar** on the left with navigation links and a **content area** on the right:

- **Dashboard** — Start scans and view session history
- **Browse Duplicates** — Review exact duplicate groups and decide what to keep or delete
- **Browse Similarities** — Review visually similar images side by side
- **Review Plan** — See a summary of all planned actions before executing
- **Execute Plan** — Run the cleanup with live progress
- **Duplicates Bin** — Restore or permanently delete soft-deleted files
- **Family Library** — Share fingerprints with family via Google Drive or file export
- **Requests** — Manage incoming and outgoing photo requests
- **Settings** — Language, theme, performance tuning, and sync configuration
- **Help** — This guide

---

## Getting Started

### Step 1 — Start a Scan

1. Go to the **Dashboard**
2. Click **Start New Scan** in the top-right corner
3. A folder picker opens — select one or more folders containing your photos
4. The scan starts automatically

**Similarity detection:** Before starting the scan, you can tick the **Enable similarity detection** checkbox next to the Start button. This adds an extra pass that finds visually similar (but not identical) images. It takes longer but catches near-duplicates like crops, resizes, or re-compressed versions.

### Step 2 — Monitor Progress

The **Scan Progress** panel appears on the Dashboard during scanning. It shows:

- **Current phase** — Discovering files, Computing hashes, or Analyzing similarity
- **Progress bar** with file count (e.g. "230 of 490 files")
- **Duplicate count** — updates live as new duplicates are found
- **Error count** — files that couldn't be read (with the last error shown)

**Controls during a scan:**

| Button | Action |
|--------|--------|
| **Pause** | Pauses the scan. Progress is saved — you can close the app and resume later. |
| **Stop** | Ends the scan permanently. Partial results remain available. |
| **Resume** | Continues a paused scan from where it left off. Already-processed files are skipped. |

When the scan finishes, a **View Results** button appears to jump straight to Browse Duplicates.

> **Downloaded photos:** Photos downloaded from the internet may carry a Windows security mark ("Mark of the Web"). DejaView automatically removes this mark during scanning so the files can be processed normally.

---

## Browse Duplicates

The **Browse Duplicates** screen has a two-panel layout:

- **Left panel** — A scrollable list of duplicate groups, each identified by a short hash and file count
- **Right panel** — The files in the selected group, with thumbnails, file paths, sizes, and dimensions

### Marking Files

Each file in a group has three action buttons:

| Button | Color when active | Meaning |
|--------|------------------|---------|
| **Keep** (checkmark) | Green | Keep this file |
| **Delete** (trash) | Red | Move this file to the Duplicates Bin |
| **Ignore** (eye-off) | Yellow | Skip this file — take no action |

Clicking an active button again toggles the action off.

### Keep and Delete Others

For groups with 4 or more files, the Keep button has a dropdown arrow. Click the arrow and choose **Keep and delete all others** to mark one file as Keep and all remaining files in the group as Delete in a single action.

### Smart Selection Presets

The preset toolbar above the group list lets you automatically mark files across all groups:

| Preset | Rule |
|--------|------|
| **Keep Largest** | Keeps the file with the largest file size in each group |
| **Keep Newest** | Keeps the most recently modified file |
| **Keep Oldest** | Keeps the oldest file by modification date |
| **Keep Shortest Path** | Keeps the file with the shortest file path |
| **Keep Highest Resolution** | Keeps the file with the highest pixel dimensions |

### Folder Scope

The folder icon button next to each file's action buttons enables **folder scope**. When activated, the action you set on that file is applied to all scanned files in the same folder, across all duplicate groups. A confirmation prompt appears before applying.

---

## Browse Similarities

The **Browse Similarities** screen lets you review groups of visually similar (but not identical) images. This screen is only populated if you enabled similarity detection during the scan.

### Compare Slider

At the top of the screen, a **compare slider** shows two images side by side with a draggable divider. This lets you spot subtle visual differences between similar files.

### Selecting Files for Comparison

Click any image thumbnail in the grid below to assign it to the left (L) or right (R) slot in the compare slider. Click an already-selected image to deselect it. The first two images in each group are pre-selected automatically.

### Keeper Recommendation

A green banner shows the **recommended file to keep** along with the reason (e.g. highest resolution, largest file). This is a suggestion — you can override it with your own choices.

### Group Navigation

Use the **Back** and **Next** buttons to move between similarity groups. The current position is shown as "1 / 5" etc.

### Actions and Presets

The same Keep / Delete / Ignore buttons and smart presets from Browse Duplicates are available here.

---

## Review Plan

Before executing any changes, visit **Review Plan** to see a summary of all your decisions:

- **Keep count** — files that will remain untouched
- **Delete count** — files that will be moved to the Duplicates Bin
- **Ignore count** — files skipped (no action)
- **Total recoverable space** — how much disk space will be freed

A scrollable list shows each planned action with the file path and size.

**Clear All Actions** resets all decisions if you want to start over.

---

## Execute Plan

Click **Execute Plan** on the Review Plan screen to begin. A confirmation dialog reminds you that files will be moved to the Duplicates Bin and can be recovered within 30 days.

The **Execute** screen shows:

- **Progress bar** with current/total count
- **Stage indicator** — "Local Cleanup" (moving files to bin) followed by "Cloud Sync" if family sharing is configured
- **Real-time log** — each file operation as it happens
- **Completion summary** — success and error counts

When execution finishes, a **View Duplicates Bin** button appears.

---

## Duplicates Bin

Deleted files are not removed from disk immediately. They are moved to the **Duplicates Bin** where they can be recovered for 30 days.

Each item shows:

- The original file path and size
- **Expiration countdown** — "Expires in X days" or "Expired"
- **Restore** button — moves the file back to its original location

### Permanent Deletion

- Select items with checkboxes, then click **Permanently Delete** to remove them from disk. This cannot be undone.
- **Purge Expired** removes all items past the 30-day window. A confirmation dialog appears first.

---

## Family Sharing

You can share scan fingerprints with trusted family members to find photos duplicated across different people's libraries. **The actual photos are never uploaded anywhere.** Only compact fingerprints (and optionally filenames) leave your machine.

### Setting Up Google Drive Sync

1. Go to **Settings** and scroll to the **Google Drive Sync** section
2. Enter a **Display Name** (e.g. `alice`) — this labels your data in the shared folder
3. Click **Sign in with Google** — a browser window opens for authorization. The app only gets access to files it creates, not your full Google Drive.
4. In Google Drive's website, create a shared folder and share it with your family members
5. Paste the shared folder's ID into the **Shared Folder ID** field
6. Choose a **privacy level** for what you share with others:

   | Level | Shares |
   |-------|--------|
   | **Filename only** *(default)* | Fingerprints and filenames; full paths stay private |
   | **Hash only** | Fingerprints only; filenames and paths stay private |
   | **Full path** | Fingerprints and complete file paths |

7. Click **Save Sync Settings**

Each other family member repeats these steps with their own display name, pointing at the same shared folder.

### Manual Export / Import

If you prefer not to use Google Drive, go to the **Family Library** screen:

- **Export Hashes** — saves your scan fingerprints to a `.json` file. Send it by email or USB to the other person.
- **Import Hashes** — opens a `.json` file you received. Cross-library matches appear immediately.

The privacy level from Settings also controls what is included in exported files.

### Managing Synced Libraries

The **Family Library** screen shows all connected family members with their last sync date. You can **Sync Now** to pull the latest data, or remove a member (their data is cleared from your local database).

---

## Requests

The **Requests** screen has two tabs:

- **Incoming** — photo requests from family members. You can **Approve** or **Decline** each request.
- **Outgoing** — requests you've sent to others. Shows the current status (Pending, Approved, Declined, or Cancelled).

---

## Settings

### Language

Choose between **English**, **Hungarian**, or **Auto-detect** (follows your Windows system language).

### Theme

Switch between **Dark** and **Light** mode.

### Performance

| Setting | Description |
|---------|-------------|
| **Max Scan Workers** | Number of CPU threads used during scanning (1–16). Higher values scan faster but use more CPU. |
| **Scan Throttle (ms)** | Delay between operations (0–5000). Higher values reduce CPU usage during scanning. 0 = no throttling. |
| **Performance Logging** | When enabled, writes detailed timing data to a CSV file for diagnostics. |

### Google Drive Sync

See the [Family Sharing](#family-sharing) section above for setup instructions.
