"""
ui/similarity_model.py — Two-level tree model for similarity groups.

Groups similar files by perceptual hash proximity.  Follows the same
two-level tree pattern as ui/cluster_model.py.

  Level 0: Similarity group rows (member count, total size, max distance)
  Level 1: Individual files (resolution, size, date, path, distance)

Plan reference: §S4.1.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import (
    QAbstractItemModel,
    QCoreApplication,
    QModelIndex,
    Qt,
)

from core.similarity_selection import recommend_keeper
from data.db import Database

# ---------------------------------------------------------------------------
# Custom data roles
# ---------------------------------------------------------------------------

ROLE_GROUP_ID = Qt.ItemDataRole.UserRole + 20
ROLE_FILE_ID = Qt.ItemDataRole.UserRole + 21
ROLE_FILE_PATH = Qt.ItemDataRole.UserRole + 22
ROLE_FILE_SIZE = Qt.ItemDataRole.UserRole + 23
ROLE_DISTANCE = Qt.ItemDataRole.UserRole + 24
ROLE_IS_RECOMMENDED = Qt.ItemDataRole.UserRole + 25
ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 26  # "group" or "file"
ROLE_THUMBNAIL_PATH = Qt.ItemDataRole.UserRole + 27
ROLE_WIDTH = Qt.ItemDataRole.UserRole + 28
ROLE_HEIGHT = Qt.ItemDataRole.UserRole + 29
ROLE_MODIFIED_AT = Qt.ItemDataRole.UserRole + 30


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SimilarFileData:
    """One file within a similarity group."""
    file_id: int
    path: str
    size: int
    modified_at: str
    thumbnail_path: str
    width: int
    height: int
    distance: int
    pixel_hash: str
    is_recommended: bool = False


@dataclass
class SimilarityGroupData:
    """A group of perceptually similar files."""
    group_id: int
    files: list[SimilarFileData] = field(default_factory=list)
    member_count: int = 0
    total_size: int = 0
    max_distance: int = 0
    recommended_file_id: int = 0
    representative_name: str = ""
    status: str = "pending"


def _tr(source: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate("SimilarityModel", source, disambiguation)


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

COLUMNS = [
    _tr("Name"),
    _tr("Members"),
    _tr("Resolution"),
    _tr("Size"),
    _tr("Distance"),
]
COL_NAME = 0
COL_MEMBERS = 1
COL_RESOLUTION = 2
COL_SIZE = 3
COL_DISTANCE = 4


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _format_resolution(w: int, h: int) -> str:
    if w and h:
        return f"{w}\u00d7{h}"
    return ""


# ---------------------------------------------------------------------------
# Similarity model
# ---------------------------------------------------------------------------

class SimilarityModel(QAbstractItemModel):
    """Two-level tree model grouping files by perceptual similarity.

    Parent rows are similarity group summaries; child rows are individual files.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups: list[SimilarityGroupData] = []

    # ── Loading ───────────────────────────────────────────────────────

    def load_from_db(self, db: Database, session_id: int) -> None:
        """Reload similarity group data from the database."""
        self.beginResetModel()
        self._groups.clear()

        groups = db.get_similarity_groups(session_id)

        for g in groups:
            group_id = g["id"]
            member_rows = db.get_similarity_group_members(group_id)
            member_dicts = [dict(m) for m in member_rows]

            if not member_dicts:
                continue

            # Determine recommended keeper.
            rec_id, _ = recommend_keeper(member_dicts)

            files: list[SimilarFileData] = []
            max_dist = 0
            total_size = 0
            for m in member_dicts:
                dist = m.get("distance", 0) or 0
                size = m.get("size", 0) or 0
                max_dist = max(max_dist, dist)
                total_size += size
                files.append(SimilarFileData(
                    file_id=m["id"],
                    path=m.get("path", ""),
                    size=size,
                    modified_at=m.get("modified_at", "") or "",
                    thumbnail_path=m.get("thumbnail_path", "") or "",
                    width=m.get("width", 0) or 0,
                    height=m.get("height", 0) or 0,
                    distance=dist,
                    pixel_hash=m.get("pixel_hash", "") or "",
                    is_recommended=(m["id"] == rec_id),
                ))

            rep_name = min(
                (os.path.basename(f.path) for f in files),
                key=len,
            )

            group_data = SimilarityGroupData(
                group_id=group_id,
                files=files,
                member_count=len(files),
                total_size=total_size,
                max_distance=max_dist,
                recommended_file_id=rec_id,
                representative_name=rep_name,
                status=g.get("status", "pending") or "pending",
            )
            self._groups.append(group_data)

        self.endResetModel()

    # ── Accessors ─────────────────────────────────────────────────────

    @property
    def groups(self) -> list[SimilarityGroupData]:
        return self._groups

    def group_count(self) -> int:
        return len(self._groups)

    def total_files(self) -> int:
        return sum(g.member_count for g in self._groups)

    # ── QAbstractItemModel interface ──────────────────────────────────

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._groups)
        if parent.internalId() == 0 and not parent.parent().isValid():
            idx = parent.row()
            if 0 <= idx < len(self._groups):
                return self._groups[idx].member_count
        return 0

    def index(
        self, row: int, column: int, parent: QModelIndex = QModelIndex()
    ) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        if not parent.parent().isValid():
            return self.createIndex(row, column, parent.row() + 1)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        internal_id = index.internalId()
        if internal_id == 0:
            return QModelIndex()
        return self.createIndex(internal_id - 1, 0, 0)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        if (orientation == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole):
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        internal_id = index.internalId()
        row = index.row()
        col = index.column()

        if internal_id == 0:
            if row < 0 or row >= len(self._groups):
                return None
            return self._group_data(self._groups[row], row, col, role)
        else:
            group_idx = internal_id - 1
            if group_idx < 0 or group_idx >= len(self._groups):
                return None
            group = self._groups[group_idx]
            if row < 0 or row >= len(group.files):
                return None
            return self._file_data(group.files[row], group, col, role)

    def _group_data(
        self, group: SimilarityGroupData, group_idx: int, col: int, role: int
    ):
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:
                return group.representative_name
            if col == COL_MEMBERS:
                return str(group.member_count)
            if col == COL_RESOLUTION:
                return ""
            if col == COL_SIZE:
                return _format_size(group.total_size)
            if col == COL_DISTANCE:
                return _tr("max {0}").format(group.max_distance)
        elif role == ROLE_GROUP_ID:
            return group.group_id
        elif role == ROLE_NODE_TYPE:
            return "group"
        elif role == ROLE_FILE_SIZE:
            return group.total_size
        elif role == ROLE_THUMBNAIL_PATH:
            for f in group.files:
                if f.is_recommended and f.thumbnail_path:
                    return f.thumbnail_path
            for f in group.files:
                if f.thumbnail_path:
                    return f.thumbnail_path
            return ""
        elif role == Qt.ItemDataRole.ToolTipRole:
            return _tr("{0} similar files \u00b7 {1} total").format(
                group.member_count, _format_size(group.total_size)
            )
        return None

    def _file_data(
        self, file_data: SimilarFileData, group: SimilarityGroupData,
        col: int, role: int
    ):
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:
                prefix = "\u2605 " if file_data.is_recommended else ""
                return prefix + os.path.basename(file_data.path)
            if col == COL_MEMBERS:
                return os.path.dirname(file_data.path)
            if col == COL_RESOLUTION:
                return _format_resolution(file_data.width, file_data.height)
            if col == COL_SIZE:
                return _format_size(file_data.size)
            if col == COL_DISTANCE:
                return str(file_data.distance)
        elif role == ROLE_FILE_ID:
            return file_data.file_id
        elif role == ROLE_FILE_PATH:
            return file_data.path
        elif role == ROLE_FILE_SIZE:
            return file_data.size
        elif role == ROLE_DISTANCE:
            return file_data.distance
        elif role == ROLE_IS_RECOMMENDED:
            return file_data.is_recommended
        elif role == ROLE_NODE_TYPE:
            return "file"
        elif role == ROLE_THUMBNAIL_PATH:
            return file_data.thumbnail_path
        elif role == ROLE_WIDTH:
            return file_data.width
        elif role == ROLE_HEIGHT:
            return file_data.height
        elif role == ROLE_MODIFIED_AT:
            return file_data.modified_at
        elif role == ROLE_GROUP_ID:
            return group.group_id
        elif role == Qt.ItemDataRole.ToolTipRole:
            tip = file_data.path
            if file_data.is_recommended:
                tip = _tr("\u2605 Recommended") + "\n" + tip
            return tip
        return None
