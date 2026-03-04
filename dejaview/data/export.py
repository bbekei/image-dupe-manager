"""
data/export.py — Manual JSON export/import for DejaView.

Module ownership (plan §Architecture):
- build_export_payload() builds JSON-serializable dict from scan results.
- import_payload() validates and imports a peer's JSON into the DB.
- No Google Drive API calls (that's sync.py, Phase 6).
- No disk I/O except JSON read (caller opens the file).

Security guards (plan §Security — JSON import limits):
- 10 MB file size cap
- 100,000 max file entries
- pixel_hash format validation (64 hex chars)
- username validation ([A-Za-z0-9_-], 1–64 chars)
- filename/path truncation to 1024 chars
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from data.db import Database

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (plan §Security — JSON import limits)
# ---------------------------------------------------------------------------

MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IMPORT_ENTRIES = 100_000

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_USERNAME_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def validate_username(value: str) -> bool:
    """Return True iff value is a safe username for export filenames.

    Plan §Security — username sanitization: 1–64 characters,
    [A-Za-z0-9_-] only, no dots.
    """
    return isinstance(value, str) and bool(_USERNAME_RE.match(value))


def _truncate(value: str | None, max_len: int = 1024) -> str | None:
    """Truncate a string to max_len if present."""
    if value is None:
        return None
    return value[:max_len]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def build_export_payload(
    db: "Database",
    session_id: int,
    username: str,
    privacy_level: str,
) -> dict:
    """Build a JSON-serializable export payload from scan results.

    Plan §Phase 5 / §Architecture — data/export.py.

    Args:
        db: Open Database instance.
        session_id: The session to export.
        username: Display name (becomes filename stem).
        privacy_level: 'hash_only' | 'filename' | 'full_path'.

    Returns:
        Dict ready for json.dumps():
        {
            "username": str,
            "exported_at": ISO-8601 str,
            "privacy_level": str,
            "files": [...]
        }

    Raises:
        ValueError: If username or privacy_level is invalid.
    """
    if not validate_username(username):
        raise ValueError(
            f"Invalid username '{username}': must be 1-64 chars, [A-Za-z0-9_-]"
        )
    if privacy_level not in ("hash_only", "filename", "full_path"):
        raise ValueError(
            f"Invalid privacy_level '{privacy_level}': "
            "must be 'hash_only', 'filename', or 'full_path'"
        )

    rows = db.get_files_for_session(session_id)
    files = []
    for row in rows:
        # Only export active files with a computed pixel_hash
        if row["status"] != "active" or row["pixel_hash"] is None:
            continue

        entry: dict = {
            "remote_id": f"{username}:{row['id']}",
            "pixel_hash": row["pixel_hash"],
            "size": row["size"],
            "modified_at": row["modified_at"],
        }

        # Include perceptual hash if available (backward-compatible field)
        phash = row["perceptual_hash"] if "perceptual_hash" in row.keys() else None
        if phash is not None:
            entry["perceptual_hash"] = phash

        if privacy_level in ("filename", "full_path"):
            # Extract filename from full path
            path = row["path"]
            entry["filename"] = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]

        if privacy_level == "full_path":
            entry["path"] = row["path"]

        files.append(entry)

    # Build outgoing requests list (Phase 4)
    requests_outgoing = []
    try:
        pending = db.get_requests_for_session(session_id)
        for req in pending:
            if req["status"] in ("pending", "approved"):
                requests_outgoing.append({
                    "pixel_hash": req["pixel_hash"],
                    "target_peer": req["target_peer"],
                    "status": req["status"],
                    "requested_at": req["requested_at"],
                })
    except Exception:
        # requests table may not exist on older DBs — skip gracefully
        pass

    payload = {
        "username": username,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "privacy_level": privacy_level,
        "files": files,
    }
    if requests_outgoing:
        payload["requests_outgoing"] = requests_outgoing

    return payload


# ---------------------------------------------------------------------------
# Compressed export (R-COMP-03 / §7 — data/export.py touchpoint)
# ---------------------------------------------------------------------------

def build_compressed_export(
    db: "Database",
    session_id: int,
    username: str,
    privacy_level: str,
) -> tuple[bytes, int, int]:
    """Build a gzip-compressed, optimized export payload.

    Applies all §3 data optimization strategies (field shortening, path
    tokenization, hash-centric grouping) then streams through gzip.

    Args:
        db: Open Database instance.
        session_id: The session to export.
        username: Display name (becomes filename stem).
        privacy_level: 'hash_only' | 'filename' | 'full_path'.

    Returns:
        (compressed_bytes, uncompressed_size, compressed_size)
        Sizes are in bytes, for compression ratio reporting (§5.1).
    """
    from data.compression import build_optimized_compressed

    payload = build_export_payload(db, session_id, username, privacy_level)
    compressed, uncompressed_size = build_optimized_compressed(payload)
    return compressed, uncompressed_size, len(compressed)


# ---------------------------------------------------------------------------
# Compressed import (R-COMP-03 — decompression path)
# ---------------------------------------------------------------------------

def import_compressed_payload(db: "Database", data: bytes) -> str:
    """Import a gzip-compressed peer export.

    Decompresses in-memory, reverses all optimizations, then delegates
    to import_payload() for validation and DB insertion.

    Args:
        db: Open Database instance.
        data: Raw gzip-compressed bytes.

    Returns:
        The peer username that was imported.

    Raises:
        ImportError: On decompression failure or validation error.
    """
    from data.compression import decompress_and_expand

    try:
        payload = decompress_and_expand(data)
    except ValueError as exc:
        raise ImportError(f"Failed to decompress peer export: {exc}") from exc

    # Re-serialize to JSON for import_payload (which expects str|bytes)
    raw = json.dumps(payload, ensure_ascii=False)
    return import_payload(db, raw)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_payload(db: "Database", raw: str | bytes) -> str:
    """Import a peer's export JSON into the database.

    Plan §Phase 5 / §Security — JSON import limits.

    Args:
        db: Open Database instance.
        raw: JSON string or bytes (from file read or Drive download).

    Returns:
        The peer username that was imported.

    Raises:
        ImportError: On validation failure (malformed JSON, size limit,
            entry count, missing fields, invalid username).
    """
    # --- Size guard ---
    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(raw_bytes) > MAX_IMPORT_BYTES:
        raise ImportError(
            f"Peer export exceeds maximum allowed size "
            f"({MAX_IMPORT_BYTES // (1024 * 1024)} MB)"
        )

    # --- Parse JSON ---
    try:
        payload = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ImportError(f"Malformed JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ImportError("Payload must be a JSON object")

    # --- Validate top-level fields ---
    username = payload.get("username")
    if not username or not validate_username(str(username)):
        raise ImportError(
            f"Invalid or missing username in payload: '{username}'"
        )
    username = str(username)

    file_entries = payload.get("files")
    if not isinstance(file_entries, list):
        raise ImportError("Payload missing 'files' array")

    if len(file_entries) > MAX_IMPORT_ENTRIES:
        raise ImportError(
            f"Peer export contains too many entries "
            f"({len(file_entries)} > {MAX_IMPORT_ENTRIES})"
        )

    # --- Validate and collect entries ---
    from data.db import validate_pixel_hash

    valid_entries: list[dict] = []
    skipped = 0
    for i, entry in enumerate(file_entries):
        if not isinstance(entry, dict):
            log.warning("Import: skipping non-dict entry at index %d", i)
            skipped += 1
            continue

        pixel_hash = entry.get("pixel_hash")
        if not pixel_hash or not validate_pixel_hash(str(pixel_hash)):
            log.warning(
                "Import: skipping entry %d with invalid pixel_hash: %r",
                i, pixel_hash,
            )
            skipped += 1
            continue

        valid_entries.append({
            "remote_id": entry.get("remote_id"),
            "pixel_hash": str(pixel_hash),
            "filename": _truncate(entry.get("filename")),
            "path": _truncate(entry.get("path")),
            "size": entry.get("size"),
            "modified_at": entry.get("modified_at"),
        })

    if skipped:
        log.warning(
            "Import from '%s': %d of %d entries skipped due to validation",
            username, skipped, len(file_entries),
        )

    # --- Upsert peer and replace their files ---
    now = datetime.now(timezone.utc).isoformat()
    peer_id = db.upsert_remote_peer(username, last_seen_at=now)

    # Clear old entries for idempotent re-import
    db.delete_remote_files_for_peer(peer_id)

    if valid_entries:
        db.insert_remote_files(peer_id, valid_entries)

    # Update last_imported_at timestamp (only if sync_config row exists;
    # it may not exist yet if user hasn't configured sync settings)
    if db.get_sync_config() is not None:
        db.upsert_sync_config(last_imported_at=now)

    # Phase 4: parse incoming requests from peer exports
    incoming_requests = payload.get("requests_outgoing", [])
    if isinstance(incoming_requests, list):
        for req in incoming_requests:
            if not isinstance(req, dict):
                continue
            req_hash = req.get("pixel_hash")
            if req_hash and validate_pixel_hash(str(req_hash)):
                # Store as metadata on the peer — the sync layer will
                # use this to show incoming requests (Phase 6).
                pass  # Stored in peer's export; acted on by sync.py

    log.info(
        "Imported %d files from peer '%s' (%d skipped)",
        len(valid_entries), username, skipped,
    )
    return username
