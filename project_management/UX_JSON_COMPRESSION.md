This requirement focuses on optimizing the storage and transfer of the image database metadata. Given the 100k+ image count, a raw JSON file containing hashes, paths, and metadata could easily exceed 50–100MB per user. Compressing this data before uploading to Google Drive is critical for reducing bandwidth and staying within Drive’s storage/api limits.

Here is the requirement specification for the **JSON Data Compression and Synchronization Module**.

---

# DEJAVIEW_TECH_REQUIREMENTS: Data Compression

## 1. Objective

To minimize the footprint of the shared image database files on Google Drive and reduce the time required for synchronization (Up/Down) by implementing a compressed binary format for the JSON-structured data.

## 2. Technical Requirements

### R-COMP-01: Algorithm Selection

* **Method:** The application shall use **GZip** (RFC 1952) or **Brotli** for compression.
* **Rationale:** GZip is natively supported by most Windows development frameworks (`System.IO.Compression`) and provides a high compression ratio (often 90%+) for repetitive text data like file paths and hexadecimal hashes.

### R-COMP-02: File Naming and Extension

* **Standard:** Compressed files shall use the `.json.gz` extension (e.g., `User_Bob.json.gz`).
* **Interoperability:** This allows the app to immediately identify that the file requires decompression before parsing, while still signaling that the underlying schema is JSON.

### R-COMP-03: Implementation Logic

* **Pre-Upload:** The app shall serialize the internal database to a JSON string, compress it in memory (or via a temporary stream), and upload only the resulting binary stream to Google Drive.
* **Post-Download:** Upon fetching a remote file, the app shall check the file extension. If `.json.gz`, it must decompress the stream into a JSON reader without writing the uncompressed version to the local disk (In-memory decompression) to maintain privacy and speed.

### R-COMP-04: Integrity Check (Checksum)

* **Requirement:** Since compression can be sensitive to bit-flips during network transfer, the JSON schema shall include a root-level `checksum` or `sha256` field calculated *before* compression.
* **Validation:** The receiving app must verify the checksum after decompression to ensure the database was not corrupted during the Google Drive sync.

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

* **Requirement:** The **Execution Screen (Screen 5)** shall display "Compressing Database..." and "Uploading Compressed Data..." to inform the user why the process might pause briefly before the network activity starts.
* **Requirement:** If a compressed file fails to decompress, the app must flag the specific `provider_username` as "Sync Failed - Corrupt Data" on the **Dashboard (Screen 1)** instead of crashing.

---