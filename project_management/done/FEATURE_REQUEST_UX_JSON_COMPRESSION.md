This requirement focuses on optimizing the storage and transfer of the image database metadata. Given the 100k+ image count, a raw JSON file containing hashes, paths, and metadata could easily exceed 50-100MB per user. Compressing this data before uploading to Google Drive is critical for reducing bandwidth and staying within Drive's storage/api limits.

Here is the requirement specification for the **JSON Data Compression and Synchronization Module**.

---

# DEJAVIEW_TECH_REQUIREMENTS: Data Compression

## 1. Objective

To minimize the footprint of the shared image database files on Google Drive and reduce the time required for synchronization (Up/Down) by implementing a compressed binary format for the JSON-structured data.

## 2. Technical Requirements

### R-COMP-01: Algorithm Selection

* **Method:** The application shall use **GZip** (RFC 1952) for compression.
* **Rationale:** GZip is in Python's standard library (`gzip` module) — no extra dependency needed. It provides 90%+ compression ratio for repetitive text data like file paths and hexadecimal hashes. Brotli offers marginal gains for this data profile and is not worth the added dependency.

### R-COMP-02: File Naming and Extension

* **Standard:** Compressed files shall use the `.json.gz` extension (e.g., `User_Bob.json.gz`).
* **Interoperability:** This allows the app to immediately identify that the file requires decompression before parsing, while still signaling that the underlying schema is JSON.

### R-COMP-03: Implementation Logic — Streaming Compression

* **Pre-Upload:** The app shall use `gzip.GzipFile` wrapping a `BytesIO` and stream-write the JSON into it with `json.dump()` directly, avoiding building the full uncompressed JSON string in memory. This halves peak memory usage for large payloads (100k+ records). The resulting compressed `BytesIO` is uploaded to Google Drive.
* **Post-Download:** Upon fetching a remote file, the app shall check the file extension. If `.json.gz`, it must decompress the stream in-memory without writing the uncompressed version to the local disk to maintain privacy and speed.

### R-COMP-04: Integrity Check (Checksum)

* **Requirement:** The SHA-256 checksum of the compressed `.json.gz` blob shall be stored as a **Google Drive custom file property** (`appProperties.sha256`). This avoids double-serialization (computing a hash over JSON, then injecting it back into the JSON).
* **Validation:** The receiving app must compute SHA-256 of the downloaded blob and compare it to the `appProperties.sha256` value before decompressing. If mismatched, the file is flagged as corrupt.

### R-COMP-05: Skip-Upload Optimization (ETag)

* **Requirement:** Before uploading, compute the SHA-256 of the compressed blob and compare it to the last uploaded hash (stored in `sync_config.last_upload_sha256`). If unchanged, skip the upload entirely.
* **Rationale:** Avoids unnecessary Google Drive API calls when the user re-syncs without any data changes.

---

## 3. Data Optimization Strategies (Pre-Compression)

To make the compression even more effective for 100k+ records, the following formatting rules apply:

| Strategy | Requirement |
| --- | --- |
| **Path Tokenization** | Replace common root paths (e.g., `C:\Users\Name\Pictures`) with short tokens (e.g., `<ROOT>`) within the JSON. Reconstruct the full path locally after decompression. |
| **Field Shortening** | Use short keys in the JSON schema (e.g., `"h"` for `"hash"`, `"p"` for `"path"`, `"s"` for `"size"`) to reduce the raw string size before the compressor runs. |
| **Redundancy Removal** | If 10 files share the same hash, the JSON structure should be **Hash-Centric**: Store the Hash once, followed by an array of its many file paths, rather than repeating the hash for every path. |

---

## 4. Performance Targets

* **Compression Target:** A 50MB raw JSON file (typical for 100k records) should be reduced to **< 5MB** after GZip compression.
* **Processing Time:** Compression and decompression of a 100k-record set must take **less than 2 seconds** on a standard Windows desktop (i5 processor / 8GB RAM).

---

## 5. User Impact & UI Requirements

### 5.1 Execution Screen

* **Requirement:** The **Execution Screen** shall display substage messages during the Cloud Sync phase:
  - "Compressing database..." while gzip runs
  - "Uploading compressed data..." during the Drive upload
  - "Downloading peer data..." during peer download
  - "Decompressing peer data..." during decompression
* **Compression Ratio Reporting:** After compression completes, display the savings: e.g., *"Compressed 47 MB → 3.2 MB (93% reduction)"*. This is computed by comparing `len()` of the uncompressed JSON vs. the compressed blob.

### 5.2 Dashboard — Error Recovery

* **Requirement:** If a compressed file fails integrity check or decompression, the app must flag the specific `provider_username` as "Sync Failed - Corrupt Data" on the **Dashboard** instead of crashing.
* **Retry:** A **"Retry Download"** action shall appear next to the error, allowing the user to re-fetch the corrupt peer file without triggering a full sync cycle.

---

## 6. Delta Sync (Incremental Export)

### R-DELTA-01: Change Tracking

* **Requirement:** Track `last_exported_at` per file record. On export, only include records changed (inserted, modified, or deleted) since the last successful upload.
* **Rationale:** For 100k records where only a handful change between syncs, delta export shrinks the payload dramatically even *before* compression.

### R-DELTA-02: Merge Semantics

* **Requirement:** The receiving side shall merge delta payloads into its `remote_files` table. Deltas include an `"action"` field per entry: `"upsert"` or `"delete"`.
* **Full Export Fallback:** If the delta grows larger than 50% of a full export (by record count), fall back to a full export instead. This avoids pathological cases where many small deltas accumulate.

---

## 7. Implementation Touchpoints

These are the specific files and integration points for this feature, validated against the current codebase:

| File | Change |
| --- | --- |
| `data/export.py` | Add `build_compressed_export()` — streaming gzip via `BytesIO` + `json.dump()`. Add field shortening, path tokenization, and hash-centric grouping to payload builder. |
| `data/sync.py` | `upload()`: compress before upload, store SHA-256 in `appProperties`, compare with `last_upload_sha256` for skip-upload. `download_peers()`: detect `.json.gz`, verify checksum, decompress in-memory. |
| `data/db.py` | Add `last_upload_sha256` column to `sync_config`. Add `last_exported_at` tracking per file (for delta sync). |
| `core/executor.py` | Emit log messages for compression/upload substages so ExecutionScreen can display them. |
| `ui/execution_screen.py` | Display substage text ("Compressing...", "Uploading...") and compression ratio report during Cloud Sync phase. |
| `ui/dashboard.py` | Add corruption indicator per peer in sync status area. Add "Retry Download" action for failed peers. |
| `resources/i18n/app.ts` | Add EN translations for all new `tr()` strings. |
| `resources/i18n/app_hu.ts` | Add HU translations for all new `tr()` strings. Recompile with `lrelease`. |
| `tests/unit/` | Test compression/decompression round-trip, checksum validation, skip-upload logic, delta merge, corrupt file handling, field shortening/expansion, path tokenization/reconstruction. |

---
