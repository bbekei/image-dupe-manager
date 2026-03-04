"""
data/sync.py — Google Drive sync for DejaView.

Module ownership (plan §Architecture):
- All Google Drive API calls live here.
- Calls export.py for payload building and import.
- Calls db.py for peer tables and sync_config.
- No direct UI interaction — emits status strings for the caller.

Plan §Phase 6:
- OAuth2 desktop flow (drive.file scope)
- Upload own export; download peer exports
- Offline fallback via pending_export flag
- Credential file created with 0o600 permissions (plan §Security)

Plan §Key Technical Decisions — Why Google Drive API:
- No dependency on cloud sync client being installed
- drive.file scope — app only sees files it created
- One shared Drive folder, shared via standard Drive sharing
"""

import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from data.db import Database

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation (plan §Security — Drive folder ID validation)
# ---------------------------------------------------------------------------

_FOLDER_ID_RE = re.compile(r'^[A-Za-z0-9_-]{25,50}$')

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def validate_folder_id(value: str) -> bool:
    """Return True iff value looks like a valid Google Drive folder ID.

    Plan §Security: 25–50 alphanumeric characters ([A-Za-z0-9_-]).
    """
    return isinstance(value, str) and bool(_FOLDER_ID_RE.match(value))


# ---------------------------------------------------------------------------
# Credential storage (plan §Security — OAuth2 token storage)
# ---------------------------------------------------------------------------

def save_credentials(creds, token_path: str | Path) -> None:
    """Write OAuth2 credentials to disk with restricted permissions.

    Plan §Security — OAuth2 token file creation:
    Creating via os.open with mode 0o600 ensures the file is
    owner-readable only before any data is written.
    """
    token_path = Path(token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(
        str(token_path),
        os.O_CREAT | os.O_WRONLY | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(fd, 'w') as f:
        f.write(creds.to_json())


def load_credentials(token_path: str | Path):
    """Load OAuth2 credentials from disk, or return None if missing/expired.

    Returns a google.oauth2.credentials.Credentials instance or None.
    """
    token_path = Path(token_path)
    if not token_path.exists():
        return None

    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        return creds
    except Exception:
        log.warning("Failed to load credentials from %s", token_path)
        return None


# ---------------------------------------------------------------------------
# DriveSync
# ---------------------------------------------------------------------------

class DriveSync:
    """Google Drive sync engine for DejaView.

    Manages upload/download of JSON exports to/from a shared Drive folder.
    All Drive API calls are in this class; everything is mockable via
    constructor injection of the service object.

    Args:
        db: Open Database instance.
        credentials_path: Path to the OAuth2 token file.
        client_secrets_path: Path to client_secrets.json for initial auth.
        service: Optional pre-built Drive API service (for testing).
    """

    def __init__(
        self,
        db: "Database",
        credentials_path: str | Path,
        client_secrets_path: str | Path | None = None,
        service=None,
    ):
        self._db = db
        self._creds_path = Path(credentials_path)
        self._secrets_path = (
            Path(client_secrets_path) if client_secrets_path else None
        )
        self._service = service
        self._status = "idle"  # 'idle' | 'syncing' | 'unavailable'

    @property
    def status(self) -> str:
        return self._status

    # ------------------------------------------------------------------
    # OAuth2 (plan §Security — credential and token storage)
    # ------------------------------------------------------------------

    def authenticate(self) -> tuple[bool, str]:
        """Run the OAuth2 desktop flow if needed.

        Returns (True, "") if credentials are valid after this call,
        or (False, reason) with a user-visible explanation on failure.
        """
        creds = load_credentials(self._creds_path)

        if creds and creds.valid:
            self._build_service(creds)
            return True, ""

        if creds and creds.expired and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                save_credentials(creds, self._creds_path)
                self._build_service(creds)
                return True, ""
            except Exception as exc:
                log.warning("Token refresh failed: %s", exc)
                # Fall through to full re-auth

        # Full OAuth2 desktop flow
        if self._secrets_path is None or not self._secrets_path.exists():
            msg = f"client_secrets.json not found at {self._secrets_path}"
            log.error(msg)
            return False, msg

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self._secrets_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            save_credentials(creds, self._creds_path)
            self._build_service(creds)
            return True, ""
        except Exception as exc:
            msg = f"OAuth2 flow failed: {exc}"
            log.error(msg)
            return False, msg

    def _build_service(self, creds) -> None:
        """Build the Drive API service from credentials."""
        if self._service is not None:
            return  # Pre-injected service (testing)
        from googleapiclient.discovery import build
        self._service = build('drive', 'v3', credentials=creds)

    def is_authenticated(self) -> bool:
        """Return True if a Drive service is available."""
        return self._service is not None

    # ------------------------------------------------------------------
    # Upload (plan §Architecture — sync.py uploads own export)
    # ------------------------------------------------------------------

    def upload(self, session_id: int, status_callback=None) -> bool:
        """Upload the current session's compressed export to Google Drive.

        R-COMP-03: Uses streaming gzip compression before upload.
        R-COMP-04: Stores SHA-256 in appProperties for integrity checks.
        R-COMP-05: Skips upload if SHA-256 matches last_upload_sha256.

        Args:
            session_id: The session to export.
            status_callback: Optional callable(str) for substage messages.

        Returns True on success.
        """
        if not self._service:
            log.warning("Upload called without authenticated service")
            return False

        config = self._db.get_sync_config()
        if not config:
            log.warning("Upload called without sync_config")
            return False

        folder_id = config["gdrive_folder_id"]
        if not folder_id or not validate_folder_id(folder_id):
            log.warning("Invalid or missing Drive folder ID")
            return False

        username = config["local_username"]
        privacy = config["export_privacy"]

        # Build compressed payload via export.py (R-COMP-03)
        if status_callback:
            status_callback("compressing")
        from data.export import build_compressed_export
        try:
            compressed, uncompressed_size, compressed_size = (
                build_compressed_export(self._db, session_id, username, privacy)
            )
        except ValueError as exc:
            log.error("Failed to build compressed export: %s", exc)
            return False

        # Compute SHA-256 of compressed blob (R-COMP-04)
        from data.compression import compute_sha256, format_compression_ratio
        blob_sha256 = compute_sha256(compressed)

        # Log compression ratio
        ratio_msg = format_compression_ratio(uncompressed_size, compressed_size)
        if ratio_msg:
            log.info("Upload: %s", ratio_msg)
        if status_callback:
            status_callback(f"compressed:{uncompressed_size}:{compressed_size}")

        # R-COMP-05: Skip-upload if unchanged
        last_sha = config["last_upload_sha256"]
        if last_sha and last_sha == blob_sha256:
            log.info("Upload skipped — data unchanged (SHA-256 match)")
            if status_callback:
                status_callback("upload_skipped")
            return True

        # Build media upload from compressed bytes
        if status_callback:
            status_callback("uploading")
        media_body = self._make_media_upload_bytes(
            compressed, mimetype='application/gzip'
        )
        file_metadata = {
            'name': f'{username}.json.gz',
            'mimeType': 'application/gzip',
            'appProperties': {'sha256': blob_sha256},
        }

        try:
            gdrive_file_id = config["gdrive_file_id"]
            if gdrive_file_id:
                # Update existing file
                self._service.files().update(
                    fileId=gdrive_file_id,
                    body={'appProperties': {'sha256': blob_sha256}},
                    media_body=media_body,
                ).execute()
                log.info("Updated Drive file %s", gdrive_file_id)
            else:
                # Create new file in the shared folder
                file_metadata['parents'] = [folder_id]
                result = self._service.files().create(
                    body=file_metadata,
                    media_body=media_body,
                    fields='id',
                ).execute()
                new_file_id = result.get('id')
                self._db.upsert_sync_config(gdrive_file_id=new_file_id)
                log.info("Created Drive file %s", new_file_id)

            # Update timestamps, SHA-256, and clear pending flag
            now = datetime.now(timezone.utc).isoformat()
            self._db.upsert_sync_config(
                last_exported_at=now,
                pending_export=0,
                last_upload_sha256=blob_sha256,
            )
            return True

        except Exception as exc:
            log.error("Drive upload failed: %s", exc)
            self._db.upsert_sync_config(pending_export=1)
            self._status = "unavailable"
            return False

    def _make_media_upload_bytes(self, data: bytes, mimetype: str = 'application/gzip'):
        """Create a MediaIoBaseUpload from raw bytes."""
        from googleapiclient.http import MediaIoBaseUpload
        stream = io.BytesIO(data)
        return MediaIoBaseUpload(stream, mimetype=mimetype, resumable=False)

    def _make_media_upload(self, content: str):
        """Create a MediaIoBaseUpload from a JSON string (legacy, kept for compat)."""
        from googleapiclient.http import MediaIoBaseUpload
        stream = io.BytesIO(content.encode('utf-8'))
        return MediaIoBaseUpload(
            stream, mimetype='application/json', resumable=False
        )

    # ------------------------------------------------------------------
    # Download peers (plan §Architecture — sync.py downloads peer exports)
    # ------------------------------------------------------------------

    def download_peers(self, status_callback=None) -> tuple[bool, dict[str, str]]:
        """Download and import all peer exports from the shared Drive folder.

        Supports both .json (legacy) and .json.gz (compressed) peer files.
        R-COMP-04: Verifies SHA-256 checksum from appProperties before import.

        Args:
            status_callback: Optional callable(str) for substage messages.

        Returns:
            (any_imported, peer_errors) where peer_errors maps
            peer_username -> error message for corrupt/failed downloads.
        """
        peer_errors: dict[str, str] = {}

        if not self._service:
            log.warning("Download called without authenticated service")
            return False, peer_errors

        config = self._db.get_sync_config()
        if not config:
            return False, peer_errors

        folder_id = config["gdrive_folder_id"]
        if not folder_id or not validate_folder_id(folder_id):
            return False, peer_errors

        local_username = config["local_username"]

        try:
            # List all files in the shared folder (JSON and gzip)
            results = self._service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields='files(id, name, modifiedTime, appProperties)',
                spaces='drive',
            ).execute()
            files = results.get('files', [])
        except Exception as exc:
            log.error("Drive list failed: %s", exc)
            self._status = "unavailable"
            return False, peer_errors

        any_imported = False
        for f in files:
            name = f.get('name', '')
            is_compressed = name.endswith('.json.gz')
            is_json = name.endswith('.json') and not is_compressed

            if not is_compressed and not is_json:
                continue

            # Extract peer username from filename
            if is_compressed:
                peer_username = name[:-8]  # strip .json.gz
            else:
                peer_username = name[:-5]  # strip .json

            # Skip our own export
            if peer_username == local_username:
                continue

            from data.export import validate_username
            if not validate_username(peer_username):
                log.warning("Skipping file with invalid username: %s", name)
                continue

            # Check if file has changed since last import
            drive_mtime = f.get('modifiedTime')
            existing_peer = self._db.get_remote_peer(peer_username)
            if existing_peer and existing_peer["file_mtime"] == drive_mtime:
                log.debug("Skipping unchanged peer file: %s", name)
                continue

            # Download the file content
            if status_callback:
                status_callback(f"downloading:{peer_username}")
            try:
                response = self._service.files().get_media(
                    fileId=f['id']
                ).execute()
            except Exception as exc:
                log.error("Failed to download %s: %s", name, exc)
                peer_errors[peer_username] = f"Download failed: {exc}"
                continue

            # R-COMP-04: Verify SHA-256 checksum for compressed files
            if is_compressed:
                app_props = f.get('appProperties', {}) or {}
                expected_sha = app_props.get('sha256')
                if expected_sha:
                    from data.compression import verify_checksum
                    if not verify_checksum(response, expected_sha):
                        msg = "Corrupt data — SHA-256 checksum mismatch"
                        log.warning("Peer %s: %s", peer_username, msg)
                        peer_errors[peer_username] = msg
                        continue

            # Import the payload
            if status_callback:
                status_callback(f"decompressing:{peer_username}")
            try:
                if is_compressed:
                    from data.export import import_compressed_payload
                    import_compressed_payload(self._db, response)
                else:
                    from data.export import import_payload
                    import_payload(self._db, response)

                # Update file_mtime for skip-unchanged logic
                now = datetime.now(timezone.utc).isoformat()
                self._db.upsert_remote_peer(
                    peer_username,
                    last_seen_at=now,
                    file_mtime=drive_mtime,
                )
                any_imported = True
                log.info("Imported peer export: %s", name)
            except ImportError as exc:
                msg = f"Import failed: {exc}"
                log.warning("Failed to import %s: %s", name, exc)
                peer_errors[peer_username] = msg
                continue

        if any_imported:
            now = datetime.now(timezone.utc).isoformat()
            self._db.upsert_sync_config(last_imported_at=now)

        return any_imported, peer_errors

    # ------------------------------------------------------------------
    # Full sync cycle
    # ------------------------------------------------------------------

    def sync(
        self,
        session_id: Optional[int] = None,
        status_callback=None,
    ) -> tuple[str, dict[str, str]]:
        """Run a full sync cycle: download peers, then upload if needed.

        Args:
            session_id: Session to export (None = no upload unless pending).
            status_callback: Optional callable(str) for substage messages.

        Returns:
            (status_string, peer_errors) where status is
            'synced', 'partial', or 'unavailable', and peer_errors maps
            peer_username -> error message for failed downloads.
        """
        self._status = "syncing"
        peer_errors: dict[str, str] = {}

        if not self._service:
            self._status = "unavailable"
            return self._status, peer_errors

        config = self._db.get_sync_config()
        if not config or not config["sync_enabled"]:
            self._status = "idle"
            return self._status, peer_errors

        download_ok = False
        upload_ok = False

        # Download peers first
        try:
            download_ok, peer_errors = self.download_peers(
                status_callback=status_callback
            )
        except Exception as exc:
            log.error("Sync download phase failed: %s", exc)
            self._status = "unavailable"

        # Upload if we have a session, or if there's a pending export
        should_upload = (
            session_id is not None
            or (config["pending_export"] and config["pending_export"] != 0)
        )
        if should_upload:
            effective_session_id = session_id
            if effective_session_id is None:
                # Use the latest session for a pending re-upload
                latest = self._db.get_latest_session()
                if latest:
                    effective_session_id = latest["id"]

            if effective_session_id is not None:
                try:
                    upload_ok = self.upload(
                        effective_session_id,
                        status_callback=status_callback,
                    )
                except Exception as exc:
                    log.error("Sync upload phase failed: %s", exc)
                    self._db.upsert_sync_config(pending_export=1)
                    self._status = "unavailable"

        if download_ok or upload_ok:
            self._status = "synced" if (download_ok and upload_ok) else "partial"
        elif self._status != "unavailable":
            self._status = "synced"  # Nothing to do is still success

        return self._status, peer_errors

    # ------------------------------------------------------------------
    # Peer management
    # ------------------------------------------------------------------

    def remove_peer(self, username: str) -> None:
        """Remove a peer and all their remote files from the DB.

        Plan test: test_remove_peer_clears_remote_files.
        """
        self._db.delete_remote_peer(username)
        log.info("Removed peer '%s' and their remote files", username)
