"""Soft-delete bin commands: restore, purge, permanent delete."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from core.trash import purge_expired

log = logging.getLogger(__name__)


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


class BinCommandsMixin:
    def get_bin_items(self, session_id: int) -> list[dict]:
        """Return all soft-deleted items with thumbnail data."""
        rows = self._db.get_active_soft_deletes(session_id)
        result = _rows_to_list(rows)
        for item in result:
            file_row = self._db.get_file(item["file_id"]) if item.get("file_id") else None
            thumb_path = file_row["thumbnail_path"] if file_row else None
            item["thumbnail_data"] = self._read_thumbnail_base64(thumb_path)
        return result

    def restore_from_bin(self, soft_delete_id: int) -> None:
        """Restore a soft-deleted file to its original location."""
        from core.trash import recover
        rows = self._db.conn.execute(
            "SELECT * FROM soft_deletes WHERE id = ? AND recovered_at IS NULL",
            (soft_delete_id,),
        ).fetchone()
        if rows:
            recover(rows["trash_path"], rows["original_path"])
            now = datetime.now(timezone.utc).isoformat()
            self._db.record_recovery(soft_delete_id, now)

    def permanent_delete(self, soft_delete_ids: list[int]) -> None:
        """Permanently delete specified bin items from disk."""
        now = datetime.now(timezone.utc).isoformat()
        for sid in soft_delete_ids:
            row = self._db.conn.execute(
                "SELECT * FROM soft_deletes WHERE id = ?", (sid,),
            ).fetchone()
            if row and row["trash_path"]:
                try:
                    Path(row["trash_path"]).unlink(missing_ok=True)
                except OSError:
                    pass
                self._db.record_recovery(sid, now)

    def purge_expired(self) -> int:
        """Permanently delete all bin items past their 30-day retention period."""
        now = datetime.now(timezone.utc).isoformat()
        expired_rows = self._db.get_expired_soft_deletes(now)
        purged = purge_expired(self._trash_root)
        for row in expired_rows:
            self._db.record_recovery(row["id"], now)
        return len(purged)
