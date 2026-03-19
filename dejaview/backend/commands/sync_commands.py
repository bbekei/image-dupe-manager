"""Export, import, Google Drive sync, peers, and requests commands."""

import json
import logging
from pathlib import Path

from data.export import build_export_payload, import_payload

log = logging.getLogger(__name__)


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


class SyncCommandsMixin:
    def export_hashes(self, session_id: int) -> str:
        """Export hashes and metadata to a JSON file for sharing."""
        config = self._db.get_sync_config()
        username = config["local_username"] if config else "local_user"
        privacy = config["export_privacy"] if config else "hash_only"
        payload = build_export_payload(self._db, session_id, username, privacy)

        export_path = self._app_dir / f"export_{session_id}.json"
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return str(export_path)

    def import_hashes(self, file_path: str) -> dict:
        """Import a peer's hash export file.

        Validates that the file exists, has a ``.json`` extension, and is
        within a reasonable size before parsing.
        """
        if not file_path:
            return {"imported": 0, "treasures": 0, "error": "no_file_provided"}

        resolved = Path(file_path).resolve(strict=False)
        if resolved.suffix.lower() != ".json":
            log.warning("Import rejected — not a .json file: %s", file_path)
            return {"imported": 0, "treasures": 0, "error": "invalid_file_type"}

        if not resolved.is_file():
            log.warning("Import rejected — file not found: %s", file_path)
            return {"imported": 0, "treasures": 0, "error": "file_not_found"}

        MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB
        if resolved.stat().st_size > MAX_IMPORT_BYTES:
            log.warning("Import rejected — file too large: %s", file_path)
            return {"imported": 0, "treasures": 0, "error": "file_too_large"}

        with open(resolved, "rb") as f:
            raw = f.read()

        try:
            username = import_payload(self._db, raw)
        except ImportError as exc:
            log.warning("Import rejected: %s", exc)
            return {"imported": 0, "error": str(exc)}
        return {"imported": 1, "username": username}

    def sync_drive(self) -> dict:
        """Upload export to Google Drive and download peer exports."""
        if not self._drive_sync:
            return {"status": "unavailable", "errors": {}}

        session = self._db.get_latest_session()
        if not session:
            return {"status": "no_session", "errors": {}}

        status, errors = self._drive_sync.sync(session["id"])
        return {"status": status, "errors": errors}

    def get_sync_config(self) -> dict:
        """Return the current sync configuration."""
        config = self._db.get_sync_config()
        authenticated = (
            self._drive_sync.is_authenticated() if self._drive_sync else False
        )
        if not config:
            return {
                "local_username": "",
                "gdrive_folder_id": "",
                "export_privacy": "filename",
                "sync_enabled": False,
                "authenticated": authenticated,
            }
        return {
            "local_username": config["local_username"] or "",
            "gdrive_folder_id": config["gdrive_folder_id"] or "",
            "export_privacy": config["export_privacy"] or "filename",
            "sync_enabled": bool(config["sync_enabled"]),
            "authenticated": authenticated,
        }

    def save_sync_config(
        self, username: str, folder_id: str, privacy: str
    ) -> dict:
        """Validate and persist sync configuration.

        Returns ``{"ok": True}`` on success or
        ``{"ok": False, "error": "..."}`` on validation failure.
        """
        from data.export import validate_username
        from data.sync import validate_folder_id

        username = (username or "").strip()
        folder_id = (folder_id or "").strip()

        if not validate_username(username):
            return {"ok": False, "error": "invalid_username"}

        if folder_id and not validate_folder_id(folder_id):
            return {"ok": False, "error": "invalid_folder_id"}

        sync_enabled = 1 if folder_id else 0
        self._db.upsert_sync_config(
            local_username=username,
            gdrive_folder_id=folder_id or None,
            export_privacy=privacy,
            sync_enabled=sync_enabled,
        )
        return {"ok": True}

    def authenticate_drive(self) -> dict:
        """Run OAuth2 authentication flow for Google Drive.

        Returns ``{"ok": True}`` on success or
        ``{"ok": False, "error": "..."}`` on failure.
        """
        if not self._drive_sync:
            return {"ok": False, "error": "Drive sync not available"}
        ok, msg = self._drive_sync.authenticate()
        return {"ok": ok, "error": msg}

    def remove_peer(self, username: str) -> None:
        """Remove a synced peer and all their data."""
        if self._drive_sync:
            self._drive_sync.remove_peer(username)
        else:
            self._db.delete_remote_peer(username)

    def get_remote_peers(self) -> list[dict]:
        rows = self._db.get_all_remote_peers()
        return _rows_to_list(rows)

    def get_requests(self, session_id: int) -> list[dict]:
        rows = self._db.get_requests_for_session(session_id)
        return _rows_to_list(rows)

    def respond_to_request(self, request_id: int, response: str) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._db.update_request_status(request_id, response, responded_at=now)
