This document outlines the UI/UX requirements for the **Results Panel** of the Dejaview application. It assumes the Folder Selection/Scanning logic is already handled elsewhere and focuses entirely on the "Sync-Plan-Commit-Fulfill" journey.

---

# DEJAVIEW_UI_SCREEN_REQUIREMENTS.md

## 1. Screen: The Family Activity Dashboard (Home View)

*The entry point after a sync/scan is complete. It provides a high-level overview of the family "network."*

### UI Elements:

* **Status Summary Cards:** * "Local Duplicates Found: [X] (Potential Space: [GB])"
* "New Photos in Family: [Y]"
* "Pending Requests for You: [Z]"


* **Sync Status Bar:** Shows "Last Synced with Google Drive: [Time]" and a manual "Sync Now" button.

### User Action Requirements:

* **Navigate to Cleanup:** Clicking the Duplicate card opens Screen 2.
* **Navigate to Discovery:** Clicking the Family card opens Screen 3.
* **Approve Requests:** Clicking the Pending Requests card opens a simple "Grant/Deny" list for other users.

---

## Screen 2: Advanced Local Cleanup (High-Volume Mode)

*Optimized for 100k+ image repositories where manual scrolling is impossible.*

### 1. The "Big Data" Filtering Sidebar

To reduce the 100k set into manageable chunks, the sidebar must allow users to "drill down" before they ever look at a thumbnail.

* **Group by Directory:** Instead of a flat list, group duplicates by the folder they reside in (e.g., "Show me only duplicates found in `C:/Dump/2022/`").
* **Similarity Threshold:** A slider to switch between **Exact Match** (identical hash) and **Near Match** (if you implement fuzzy hashing later for resized versions).
* **Mass Filters:**
* **Date Range:** Filter by "Date Taken" (EXIF) or "File Created."
* **File Extension:** Filter by `.jpg`, `.raw`, `.png`, etc.
* **Redundancy Level:** Filter for images that have more than *X* copies (e.g., "Show me only the worst offenders with 5+ copies").
* **Family Safety:** A toggle for "Backed up in Family" (Only show duplicates that I know for a fact Uncle Bob or Mom also have).



### 2. The "Smart Grouping" Result Panel

Instead of a list of 100,000 files, the results are displayed as **"Duplicate Clusters."**

* **Cluster Summary View:** Each row represents a *set* of duplicates.
* *Left:* Master Thumbnail.
* *Middle:* Cluster Stats ("4 copies found in 3 different drives").
* *Right:* Action Menu ("Keep Best," "Keep Newest," "Keep Deepest Path").


* **Batch Selection Tools:**
* **"Select All in This Folder":** If a user realizes an entire folder is a backup of another, they can mark the whole directory for deletion in one click.
* **"Select by Pattern":** e.g., "Select all files containing `_copy` or `(1)` in the filename."



### 3. User Action Requirements (High-Volume)

* **Requirement - The "Selection Logic" Engine:** The user defines a rule (e.g., *"Keep the version with the highest resolution; if tied, keep the one in the folder 'My Pictures'"*). The app then applies this logic to the filtered set (e.g., 5,000 images) and marks them for the Review Plan.
* **Requirement - Virtual Scrolling:** The UI must implement virtualized lists/grids to ensure that rendering 100,000 rows doesn't crash the Windows process.
* **Requirement - The "Safety Toggle":** A "Lock Master Copies" toggle that makes it physically impossible to select the last remaining copy of any hash for deletion.

### 4. Metadata-Specific Sorting

* **Sort by "Waste":** Sort clusters by total file size (e.g., a cluster of 10 RAW files taking up 500MB should appear at the top, ahead of 2 small JPEGs).
* **Sort by "Path Length":** Often, the "best" copy is the one in the most organized (deepest) folder structure, while duplicates are in root "Temp" folders.

---

## Updated Screen-Level Requirements Summary

| UI Component | Action-Based Requirement |
| --- | --- |
| **Global Search** | User types a filename fragment or folder name to instantly isolate a subset of the 100k list. |
| **Path Exclusion** | User right-clicks a folder in the results and selects "Always Keep This Folder" to protect it from auto-selection logic. |
| **Statistical Header** | A live-updating counter: "2,405 groups selected |
| **Thumbnail On-Demand** | To save memory, thumbnails are only generated/loaded for the clusters currently visible on the screen. |

---

### Integration Thought:

Since you have 100k images, the `.json` file for the Google Drive sync could become quite large. Would you like me to add a requirement for **JSON Data Compression** or **Pagination** to the technical section of your library?
---

## 3. Screen: Family Discovery (The "Missing Gems")

*Focused on Use Case 3 (Requesting missing photos).*

### UI Elements:

* **Grid View:** Thumbnails of images found in family JSONs that are not present locally.
* **Provider Label:** A small text badge on each thumbnail (e.g., "From: Uncle Bob").
* **Filter Sidebar:** Filter by Provider (User), Date Taken, or "Not yet requested."

### User Action Requirements:

* **Request Image:** A "Heart" or "Plus" icon on the thumbnail to add to the "Request Queue."
* **Bulk Request:** Ability to click-and-drag to select multiple images and click "Request Selected."
* **View Details:** Double-click to see a larger preview (if a low-res thumbnail was included in the JSON).

---

## 4. Screen: Plan Review (The "Commit" Screen)

*The final gate before any file system or cloud changes occur.*

### UI Elements:

* **Two-Column Summary:**
* **Left:** List of files to be deleted locally.
* **Right:** List of files being requested from others.


* **Impact Totals:** "Local Storage Change: -1.2 GB | Network Activity: +150 MB."
* **The "Commit" Button:** A high-contrast button to execute the plan.

### User Action Requirements:

* **Remove from Plan:** A "Remove" (X) button next to any item to cancel that specific action before committing.
* **Final Execution:** Clicking "Apply Changes" triggers the file moves and the JSON upload to Google Drive.

---

## 5. Screen: Execution & Progress

*A simple, transparent view of the background automation.*

### UI Elements:

* **Task Progress Bars:** Separate bars for "Local Cleanup" and "Uploading Request Metadata."
* **Real-time Log:** A scrolling text area (optional/collapsible) showing:
* *Moving Image_001.jpg to Trash...*
* *Updating UserA.json on Google Drive...*



### User Action Requirements:

* **Minimize to Tray:** Allows the app to work in the background.
* **View Summary:** Once finished, changes to a "Done" button that leads back to the Dashboard.

---

## Screen Interaction Principles:

1. **Safety First:** No file is ever deleted without passing through the **Plan Review (Screen 4)**.
2. **No Dead Ends:** Every screen should have a "Back to Dashboard" or "Cancel" option.
3. **Visual Consistency:** Use color coding (e.g., Red for Deletion actions, Green for Requests/Additions) to help the user distinguish between losing and gaining data.