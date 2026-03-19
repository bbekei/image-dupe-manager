"""Duplicate group actions, presets, custom selection, plan and execution commands."""

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path

from core.selection import SelectionPreset, apply_preset
from core.sort_chain import SortCriterion

_EVT_SELECTION_PROGRESS = "selection:progress"
_EVT_SELECTION_COMPLETE = "selection:complete"
_EVT_EXEC_PROGRESS = "exec:progress"

log = logging.getLogger(__name__)


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


class FileActionCommandsMixin:
    # ── Shared thumbnail helpers (also used by similarity and bin mixins) ──────

    def _is_safe_thumb_path(self, thumb_path: str) -> bool:
        """Return True only if *thumb_path* resolves inside ``self._thumb_dir``."""
        try:
            resolved = Path(thumb_path).resolve(strict=False)
            return resolved.is_relative_to(self._thumb_dir.resolve())
        except (OSError, ValueError):
            return False

    def _read_thumbnail_base64(self, thumb_path: str | None) -> str:
        """Read a thumbnail file and return a data URI, or empty string.

        Only reads files that resolve inside the application's thumbnail
        directory to prevent arbitrary file reads.
        """
        if not thumb_path:
            return ""
        if not self._is_safe_thumb_path(thumb_path):
            log.warning("Blocked thumbnail read outside thumb_dir: %s", thumb_path)
            return ""
        try:
            data = Path(thumb_path).read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
        except OSError:
            return ""

    # ── Shared action helpers (also used by similarity mixin) ─────────────────

    def _get_file_action(self, session_id: int, file_id: int) -> str | None:
        """Return the current action for a file, or None if undecided."""
        row = self._db.conn.execute(
            "SELECT action FROM file_actions "
            "WHERE session_id = ? AND file_id = ?",
            (session_id, file_id),
        ).fetchone()
        return row["action"] if row else None

    def _get_group_actions(self, session_id: int, file_ids: list[int]) -> dict[int, str]:
        """Return ``{file_id: action}`` for the given file IDs."""
        if not file_ids:
            return {}
        ph = ",".join("?" * len(file_ids))
        rows = self._db.conn.execute(
            f"SELECT file_id, action FROM file_actions "
            f"WHERE session_id = ? AND file_id IN ({ph})",
            [session_id, *file_ids],
        ).fetchall()
        return {r["file_id"]: r["action"] for r in rows}

    def _auto_keep_last_undecided(self, session_id: int, pixel_hash: str) -> None:
        """If only one undecided file remains in a group, auto-mark it 'keep'."""
        group_files = self._db.get_files_by_pixel_hash(session_id, pixel_hash)
        file_ids = [f["id"] for f in group_files]
        existing = self._get_group_actions(session_id, file_ids)
        undecided = [fid for fid in file_ids if fid not in existing]
        if len(undecided) == 1:
            now = datetime.now(timezone.utc).isoformat()
            self._db.set_file_action(
                session_id, undecided[0], "keep", "file", now
            )

    # ── Duplicate groups ──────────────────────────────────────────────────────

    def get_duplicate_groups(
        self,
        session_id: int,
        offset: int = 0,
        limit: int = 50,
        filters: dict | None = None,
    ) -> dict:
        """Paginated query returning duplicate groups with file metadata."""
        groups_rows = self._db.get_duplicate_groups(session_id)
        total_count = len(groups_rows)
        result = []
        for i, g in enumerate(groups_rows):
            if i < offset:
                continue
            if len(result) >= limit:
                break
            files = self._db.get_files_by_pixel_hash(session_id, g["pixel_hash"])
            result.append({
                "pixel_hash": g["pixel_hash"],
                "hash_algorithm": g["hash_algorithm"],
                "file_count": g["file_count"],
                "files": _rows_to_list(files),
            })
        return {"groups": result, "total_count": total_count}

    def get_group_detail(self, session_id: int, pixel_hash: str) -> list[dict]:
        """Return full metadata for all files in a specific duplicate group.

        Each file dict includes an ``action`` key (``'keep'``, ``'delete'``,
        ``'ignore'``, or ``None`` if undecided).
        """
        files = self._db.get_files_by_pixel_hash(session_id, pixel_hash)
        result = _rows_to_list(files)
        file_ids = [f["id"] for f in result]
        actions = self._get_group_actions(session_id, file_ids)
        for f in result:
            f["thumbnail_data"] = self._read_thumbnail_base64(f.get("thumbnail_path"))
            f["action"] = actions.get(f["id"])
        return result

    def set_file_action(self, file_id: int, action: str, scope: str) -> dict:
        """Mark a file with an action (keep/delete/ignore).

        Supports toggle: clicking the same action again clears it.
        Auto-keep: when 'delete' leaves only one undecided file in the
        duplicate group, that file is automatically marked 'keep'.

        Returns ``{"actions": {file_id: action, ...}}`` for every file in the
        group so the frontend can refresh its state in one round-trip.
        """
        if not isinstance(file_id, int) or not isinstance(action, str) or not isinstance(scope, str):
            return {"actions": {}}
        if action not in ("keep", "delete", "ignore"):
            return {"actions": {}}
        if scope not in ("file", "folder"):
            return {"actions": {}}
        file_row = self._db.get_file(file_id)
        if not file_row:
            return {"actions": {}}

        session_id = file_row["session_id"]
        pixel_hash = file_row["pixel_hash"]
        now = datetime.now(timezone.utc).isoformat()

        current = self._get_file_action(session_id, file_id)
        if current == action:
            self._db.clear_file_action(session_id, file_id)
        else:
            self._db.set_file_action(session_id, file_id, action, scope, now)
            if action == "delete" and pixel_hash:
                self._auto_keep_last_undecided(session_id, pixel_hash)

        group_actions = {}
        if pixel_hash:
            group_files = self._db.get_files_by_pixel_hash(session_id, pixel_hash)
            file_ids = [f["id"] for f in group_files]
            group_actions = self._get_group_actions(session_id, file_ids)
        return {"actions": group_actions}

    def keep_and_delete_others(
        self, keep_file_id: int, group_file_ids: list[int]
    ) -> dict:
        """Mark one file 'keep' and all others in the group 'delete'.

        Works for both duplicate groups (shared pixel_hash) and similarity
        groups (different pixel_hashes).  Accepts the full list of file IDs
        in the group from the frontend so no grouping assumptions are needed.

        Returns ``{"actions": {file_id: action, ...}}`` for the whole group.
        """
        if not isinstance(keep_file_id, int):
            return {"actions": {}}
        if not isinstance(group_file_ids, list) or not all(isinstance(i, int) for i in group_file_ids):
            return {"actions": {}}
        now = datetime.now(timezone.utc).isoformat()
        file_row = self._db.get_file(keep_file_id)
        if not file_row:
            return {"actions": {}}

        session_id = file_row["session_id"]

        for fid in group_file_ids:
            if fid == keep_file_id:
                self._db.set_file_action(session_id, fid, "keep", "file", now)
            else:
                self._db.set_file_action(session_id, fid, "delete", "file", now)

        return {
            "actions": self._get_group_actions(session_id, group_file_ids)
        }

    def apply_folder_action(
        self, session_id: int, folder_path: str, action: str
    ) -> dict:
        """Apply an action to ALL scanned files in a folder across all groups.

        Unlike ``set_file_action`` (single-file toggle), this is a batch
        operation: it sets the action on every file whose parent directory
        matches *folder_path*, skipping files that already carry the same
        action.  Auto-keep logic is triggered per-group when deleting.

        Returns ``{"affected": <int>}`` — the number of files changed.
        """
        now = datetime.now(timezone.utc).isoformat()
        norm = folder_path.replace("\\", "/")
        rows = self._db.conn.execute(
            """
            SELECT f.id, f.pixel_hash FROM files f
            WHERE f.session_id = ?
              AND REPLACE(f.path, '\\', '/') LIKE ? || '/%'
              AND f.pixel_hash IS NOT NULL
              AND f.pixel_hash IN (
                  SELECT pixel_hash FROM files
                  WHERE session_id = ? AND pixel_hash IS NOT NULL
                  GROUP BY pixel_hash HAVING COUNT(*) > 1
              )
            """,
            (session_id, norm, session_id),
        ).fetchall()

        affected = 0
        seen_hashes: set[str] = set()
        for r in rows:
            fid = r["id"]
            ph = r["pixel_hash"]
            current = self._get_file_action(session_id, fid)
            if current == action:
                continue
            self._db.set_file_action(session_id, fid, action, "folder", now)
            affected += 1
            if ph:
                seen_hashes.add(ph)

        if action == "delete":
            for ph in seen_hashes:
                self._auto_keep_last_undecided(session_id, ph)

        return {"affected": affected}

    def apply_selection_preset(
        self, session_id: int, preset: str, group_ids: list[str] | None = None
    ) -> dict:
        """Apply a smart selection preset to specified groups.

        Clears existing duplicate actions before applying (scoped clear).
        """
        preset_enum = SelectionPreset[preset]
        if group_ids is None:
            self._db.clear_duplicate_actions(session_id)
        keep, delete = apply_preset(
            self._db, session_id, preset_enum,
            pixel_hashes=group_ids,
            progress_callback=lambda c, t: self._emit(
                _EVT_SELECTION_PROGRESS, {"current": c, "total": t}
            ),
        )
        self._emit(_EVT_SELECTION_COMPLETE, {
            "keep_count": keep, "delete_count": delete,
            "active_preset": preset,
        })
        return {"keep_count": keep, "delete_count": delete, "active_preset": preset}

    def apply_custom_selection(
        self, session_id: int, criteria: list[dict]
    ) -> dict:
        """Apply a custom sort-chain to duplicate groups.

        Args:
            criteria: List of {"field": str, "ascending": bool} dicts.
        """
        chain = [SortCriterion(c["field"], c["ascending"]) for c in criteria]
        self._db.clear_duplicate_actions(session_id)
        keep, delete = apply_preset(
            self._db, session_id, chain,
            progress_callback=lambda c, t: self._emit(
                _EVT_SELECTION_PROGRESS, {"current": c, "total": t}
            ),
        )
        self._emit(_EVT_SELECTION_COMPLETE, {
            "keep_count": keep, "delete_count": delete,
            "active_preset": "custom",
        })
        return {"keep_count": keep, "delete_count": delete, "active_preset": "custom"}

    def get_plan_summary(self, session_id: int) -> dict:
        """Return all planned actions for review before execution."""
        summary = self._db.get_plan_summary(session_id)
        actions_rows = self._db.get_delete_actions_with_paths(session_id)
        actions = []
        for r in actions_rows:
            actions.append({
                "file_id": r["file_id"],
                "path": r["path"],
                "size": r["size"],
                "action": "delete",
                "pixel_hash": r["pixel_hash"] or "",
            })
        return {
            "keep_count": summary.get("keep_count", 0),
            "delete_count": summary.get("delete_count", 0),
            "ignore_count": summary.get("ignore_count", 0),
            "total_size_bytes": summary.get("delete_bytes", 0),
            "actions": actions,
        }

    def execute_plan(self, session_id: int) -> None:
        """Execute all planned file actions (soft-delete, sync). Emits progress events."""
        from core.executor import PlanExecutor

        executor = PlanExecutor(
            db=self._db,
            session_id=session_id,
            trash_root=self._trash_root,
            drive_sync=self._drive_sync,
        )
        self._executor = executor

        executor.progress_updated.connect(
            lambda c, t: self._emit(_EVT_EXEC_PROGRESS, {
                "current": c, "total": t, "action": "cleanup", "file_path": "",
            }),
        )
        executor.execution_complete.connect(
            lambda s, e: self._emit("exec:complete", {
                "success": s, "errors": e,
                "summary": f"{s} succeeded, {e} failed",
            }),
        )
        executor.execution_error.connect(
            lambda path, msg: self._emit("exec:error", {
                "message": msg, "file_path": path,
            }),
        )
        executor.log_message.connect(
            lambda msg: self._emit(_EVT_EXEC_PROGRESS, {
                "action": "log", "file_path": msg,
            }),
        )
        executor.stage_changed.connect(
            lambda stage: self._emit(_EVT_EXEC_PROGRESS, {
                "action": stage, "file_path": "",
            }),
        )

        executor.start()

    def clear_all_actions(self, session_id: int) -> None:
        """Clear all planned actions for a session."""
        self._db.clear_all_actions(session_id)
