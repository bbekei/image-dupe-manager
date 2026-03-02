# DEJAVIEW_UX_REQUIREMENTS.md

## 📸 Overview

**Dejaview** is a family-oriented photo deduplication and synchronization tool. It uses local hashing to identify duplicates and an asynchronous JSON-handshake via Google Drive to allow family members to identify missing photos in their collections and request them from one another.

---

## 1. The Core User Journey: "Sync-Plan-Commit-Fulfill"

### Phase 1: Discovery (The Sync)

* **Local Hashing:** The app scans local directories and generates unique hashes.
* **Remote Fetch:** The app pulls all available `*.json` files from the shared Google Drive folder.
* **Data Merging:** The local database merges these records, tagging each with a `provider_username`.
* **Categorization:** * **Local Clutter:** Multiple paths for one hash on the user's machine.
* **Safe Duplicates:** Local hashes that also exist in at least one relative's JSON.
* **Family Treasures:** Hashes found in family JSONs that do not exist locally.



### Phase 2: Planning (Decision Making)

* **Cleanup Mode:** The user views "Local Clutter." They can select specific files for deletion or use "Auto-Select" logic.
* **Discovery Mode:** The user browses "Family Treasures." They can mark specific items as "Requested."

### Phase 3: Plan Review (The "Shopping Cart")

* **Validation Summary:** A final confirmation screen showing: *"You are about to delete 45 files (Saved: 1.2GB) and request 12 files from 'User_Bob'."*
* **Conflict Check:** Ensure the "Master Copy" (highest resolution/uncompressed) is the one being kept before confirming deletions.

### Phase 4: Execution (The Commit)

* **Local Action:** Files are moved to a temporary "App Trash" or the System Recycle Bin (nondestructive).
* **Cloud Export:** The app generates an updated `[YourName].json`. This file includes a `requests_outgoing` block containing the hashes needed from other users.

### Phase 5: The Handshake (Fulfillment)

* **Passive Notification:** When "User_Bob" opens his app, it detects the request in the shared JSON.
* **Approval/Transfer:** Upon Bob's approval, his app uploads the actual image file to a `Shared_Transfers/For_[YourName]/` directory on Google Drive.
* **Ingestion:** Your app detects the file, moves it to your local library, and updates the JSON to clear the request.

---

## 2. UX Design Recommendations

### A. The "Master Copy" Visual Badge

* **Requirement:** In any duplicate view, the app must automatically identify and badge the highest-quality version (based on resolution/file size).
* **Goal:** Prevent users from accidentally deleting the original high-res photo and keeping a compressed thumbnail.

### B. The "Family Activity" Feed

* **Requirement:** A dashboard on the home screen showing asynchronous updates.
* **Elements:** * *"User_Mom is requesting 5 photos."*
* *"10 photos from User_Dad are ready to download."*
* *"Last Sync: [Timestamp]."*



### C. Nondestructive "Soft-Delete"

* **Requirement:** Instead of immediate permanent deletion, move files to a hidden `.dejaview_trash` folder.
* **Goal:** Build user trust and allow for 30-day recovery.

---

## 3. Integration with Existing Features

| Feature | Requirement |
| --- | --- |
| **JSON Provider Tagging** | Display a "Pill" or Avatar (e.g., `[Bob]`) next to thumbnails in the Family Treasures view. |
| **Google Drive Sync** | Implement a "Manual Sync" button and an "Auto-Sync on Launch" toggle. |
| **Hash-based Intercept** | If a user tries to request a photo they *already* have (detected via hash but in an unscanned folder), notify them instead of downloading. |

---

## 4. Improvement Ideas & Future Scalability

* **Smart Selection Presets:** Allow users to auto-select duplicates based on:
* *Quality First:* Keep largest resolution.
* *Organization First:* Keep the one in the most "organized" folder path.


* **Privacy Zones:** Allow users to mark specific local folders as "Private." Hashes from these folders are used for local deduplication but are **never** included in the exported JSON.
* **Folder Mapping:** When a request is fulfilled, provide a "Save to..." dialog to ensure the new photo lands in the correct part of the user's library.
* **Delta Updates:** To keep JSON files small, implement a system that only pushes "changes" since the last timestamped sync.
