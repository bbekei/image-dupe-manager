"""Similarity group detection and selection commands."""

import logging

from core.similarity_selection import (
    SimilarityPreset,
    apply_similarity_preset,
    recommend_keeper,
)
from core.sort_chain import SortCriterion

_EVT_SELECTION_PROGRESS = "selection:progress"
_EVT_SELECTION_COMPLETE = "selection:complete"

log = logging.getLogger(__name__)


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


class SimilarityCommandsMixin:
    def get_similarity_groups(
        self, session_id: int, offset: int = 0, limit: int = 50
    ) -> dict:
        """Return paginated similarity group summaries (no members/thumbnails)."""
        total = self._db.get_similarity_group_count(session_id)
        db_groups = self._db.get_similarity_groups_paginated(
            session_id, offset, limit,
        )
        groups = []
        for g in db_groups:
            groups.append({
                "id": g["id"],
                "session_id": g["session_id"],
                "member_count": g["member_count"],
                "status": g["status"],
                "representative_path": g["representative_path"],
            })
        return {"groups": groups, "total_count": total}

    def get_similarity_group_detail(self, group_id: int) -> dict:
        """Return full member data with thumbnails for a single group.

        Each member dict includes an ``action`` key (``'keep'``, ``'delete'``,
        ``'ignore'``, or ``None`` if undecided), mirroring ``get_group_detail``.
        """
        members = self._db.get_similarity_group_members(group_id)
        member_list = _rows_to_list(members)
        if member_list:
            session_id = member_list[0]["session_id"]
            file_ids = [m["id"] for m in member_list]
            actions = self._get_group_actions(session_id, file_ids)
        else:
            actions = {}
        for m in member_list:
            m["thumbnail_data"] = self._read_thumbnail_base64(
                m.get("thumbnail_path")
            )
            m["action"] = actions.get(m["id"])
        return {
            "id": group_id,
            "member_count": len(member_list),
            "members": member_list,
        }

    def apply_similarity_preset(
        self,
        session_id: int,
        preset: str,
        group_ids: list[int] | None = None,
    ) -> dict:
        """Apply selection preset to similarity groups.

        Clears existing similarity actions before applying (scoped clear).
        """
        preset_enum = SimilarityPreset[preset]
        if group_ids is None:
            self._db.clear_similarity_actions(session_id)
        keep, delete = apply_similarity_preset(
            self._db, session_id, preset_enum, group_ids=group_ids,
            progress_callback=lambda c, t: self._emit(
                _EVT_SELECTION_PROGRESS, {"current": c, "total": t}
            ),
        )
        self._emit(_EVT_SELECTION_COMPLETE, {
            "keep_count": keep, "delete_count": delete,
            "active_preset": preset,
        })
        return {"keep_count": keep, "delete_count": delete, "active_preset": preset}

    def apply_custom_similarity_selection(
        self, session_id: int, criteria: list[dict]
    ) -> dict:
        """Apply a custom sort-chain to similarity groups.

        Args:
            criteria: List of {"field": str, "ascending": bool} dicts.
        """
        chain = [SortCriterion(c["field"], c["ascending"]) for c in criteria]
        self._db.clear_similarity_actions(session_id)
        keep, delete = apply_similarity_preset(
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

    def recommend_keeper(self, files: list[dict]) -> dict:
        """Return the recommended file to keep and the reason."""
        file_id, reason = recommend_keeper(files)
        return {"file_id": file_id, "reason": reason}
