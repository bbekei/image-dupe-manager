"""
ui/cluster_model.py — Hash-grouped cluster model for Advanced Cleanup.

Groups duplicate files by pixel_hash instead of by directory.  Two-level tree:
  Level 0: Cluster rows (one per pixel_hash group)
  Level 1: Individual files within each cluster

Uses QAbstractItemModel for virtual rendering (Qt only calls data() for
visible rows), supporting 100k+ file libraries without loading everything
into QWidget memory.

UX Redesign Phase 5 — Advanced Cleanup.
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

from core.selection import identify_master_copy
from data.db import Database

# ---------------------------------------------------------------------------
# Custom data roles
# ---------------------------------------------------------------------------

ROLE_PIXEL_HASH = Qt.ItemDataRole.UserRole + 1
ROLE_IS_MASTER = Qt.ItemDataRole.UserRole + 2
ROLE_CLUSTER_INDEX = Qt.ItemDataRole.UserRole + 3
ROLE_FILE_PATH = Qt.ItemDataRole.UserRole + 4
ROLE_FILE_SIZE = Qt.ItemDataRole.UserRole + 5
ROLE_FILE_ID = Qt.ItemDataRole.UserRole + 6
ROLE_MODIFIED_AT = Qt.ItemDataRole.UserRole + 7
ROLE_THUMBNAIL_PATH = Qt.ItemDataRole.UserRole + 8
ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 9  # "cluster" or "file"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FileData:
    """One file within a duplicate cluster."""
    file_id: int
    path: str
    size: int
    modified_at: str
    thumbnail_path: str
    is_master: bool = False


@dataclass
class ClusterData:
    """A group of duplicate files sharing the same pixel_hash."""
    pixel_hash: str
    files: list[FileData] = field(default_factory=list)
    total_size: int = 0
    file_count: int = 0
    master_file_id: int = 0
    representative_name: str = ""
    oldest_date: str = ""
    newest_date: str = ""


def _tr(source: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate("ClusterModel", source, disambiguation)


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

COLUMNS = [
    _tr("Name"),
    _tr("Copies"),
    _tr("Size"),
    _tr("Modified"),
]
COL_NAME = 0
COL_COPIES = 1
COL_SIZE = 2
COL_MODIFIED = 3


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ---------------------------------------------------------------------------
# Cluster model
# ---------------------------------------------------------------------------

class ClusterModel(QAbstractItemModel):
    """Two-level tree model grouping duplicates by pixel_hash.

    Parent rows are cluster summaries; child rows are individual files.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clusters: list[ClusterData] = []
        self._page: int = 0
        self._page_size: int = 50
        self._total_groups: int = 0

    # ── Loading ───────────────────────────────────────────────────────

    def load_from_db(
        self,
        db: Database,
        session_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
        extensions: list[str] | None = None,
        min_copies: int = 2,
        sort_by: str = "waste",
        sort_desc: bool = True,
        search_text: str | None = None,
        page: int = 0,
        page_size: int = 50,
    ) -> None:
        """Reload cluster data from the database with optional filters."""
        self.beginResetModel()
        self._clusters.clear()

        self._total_groups = db.get_duplicate_group_count(
            session_id,
            date_from=date_from,
            date_to=date_to,
            extensions=extensions,
            min_copies=min_copies,
        )
        self._page = page
        self._page_size = page_size

        groups = db.get_filtered_duplicate_groups(
            session_id,
            date_from=date_from,
            date_to=date_to,
            extensions=extensions,
            min_copies=min_copies,
            sort_by=sort_by,
            sort_desc=sort_desc,
            limit=page_size,
            offset=page * page_size,
        )

        for g in groups:
            pixel_hash = g["pixel_hash"]
            file_rows = db.get_cluster_files(session_id, pixel_hash)
            file_dicts = [dict(r) for r in file_rows]

            # Apply search filter (filename fragment)
            if search_text:
                needle = search_text.lower()
                file_dicts = [
                    f for f in file_dicts
                    if needle in os.path.basename(f["path"]).lower()
                ]
                if not file_dicts:
                    continue

            master_id = identify_master_copy(file_dicts) or 0

            files = []
            for f in file_dicts:
                files.append(FileData(
                    file_id=f["id"],
                    path=f["path"],
                    size=f.get("size") or 0,
                    modified_at=f.get("modified_at") or "",
                    thumbnail_path=f.get("thumbnail_path") or "",
                    is_master=(f["id"] == master_id),
                ))

            if not files:
                continue

            # Representative name: shortest filename in cluster
            rep_name = min(
                (os.path.basename(f.path) for f in files),
                key=len,
            )

            cluster = ClusterData(
                pixel_hash=pixel_hash,
                files=files,
                total_size=sum(f.size for f in files),
                file_count=len(files),
                master_file_id=master_id,
                representative_name=rep_name,
                oldest_date=g["oldest_date"] or "",
                newest_date=g["newest_date"] or "",
            )
            self._clusters.append(cluster)

        self.endResetModel()

    # ── Accessors ─────────────────────────────────────────────────────

    @property
    def clusters(self) -> list[ClusterData]:
        return self._clusters

    def cluster_count(self) -> int:
        return len(self._clusters)

    def total_files(self) -> int:
        return sum(c.file_count for c in self._clusters)

    def total_waste_bytes(self) -> int:
        """Total bytes across all clusters minus one copy per cluster (potential savings)."""
        waste = 0
        for c in self._clusters:
            if c.files:
                # Waste = total - largest file (the one we'd keep)
                largest = max(f.size for f in c.files)
                waste += c.total_size - largest
        return waste

    # ── Pagination ────────────────────────────────────────────────────

    @property
    def page(self) -> int:
        return self._page

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def total_groups(self) -> int:
        return self._total_groups

    @property
    def total_pages(self) -> int:
        if self._total_groups == 0:
            return 1
        return (self._total_groups + self._page_size - 1) // self._page_size

    @property
    def has_next_page(self) -> bool:
        return self._page < self.total_pages - 1

    @property
    def has_previous_page(self) -> bool:
        return self._page > 0

    # ── QAbstractItemModel interface ──────────────────────────────────

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            # Root level: number of clusters
            return len(self._clusters)
        # Cluster level: number of files in this cluster
        if parent.internalId() == 0 and not parent.parent().isValid():
            cluster_idx = parent.row()
            if 0 <= cluster_idx < len(self._clusters):
                return self._clusters[cluster_idx].file_count
        return 0

    def index(
        self, row: int, column: int, parent: QModelIndex = QModelIndex()
    ) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            # Top level: cluster row. Internal ID = 0 means "cluster level".
            return self.createIndex(row, column, 0)

        if not parent.parent().isValid():
            # Child level: file row. Internal ID = cluster_index + 1.
            return self.createIndex(row, column, parent.row() + 1)

        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        internal_id = index.internalId()
        if internal_id == 0:
            # Cluster-level item: parent is root
            return QModelIndex()

        # File-level item: parent is the cluster at (internal_id - 1)
        cluster_row = internal_id - 1
        return self.createIndex(cluster_row, 0, 0)

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
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
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
            # ── Cluster-level data ──
            if row < 0 or row >= len(self._clusters):
                return None
            cluster = self._clusters[row]
            return self._cluster_data(cluster, row, col, role)
        else:
            # ── File-level data ──
            cluster_idx = internal_id - 1
            if cluster_idx < 0 or cluster_idx >= len(self._clusters):
                return None
            cluster = self._clusters[cluster_idx]
            if row < 0 or row >= len(cluster.files):
                return None
            file_data = cluster.files[row]
            return self._file_data(file_data, cluster, col, role)

    def _cluster_data(
        self, cluster: ClusterData, cluster_idx: int, col: int, role: int
    ):
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:
                return cluster.representative_name
            if col == COL_COPIES:
                return str(cluster.file_count)
            if col == COL_SIZE:
                return _format_size(cluster.total_size)
            if col == COL_MODIFIED:
                return cluster.newest_date[:10] if cluster.newest_date else ""
        elif role == ROLE_PIXEL_HASH:
            return cluster.pixel_hash
        elif role == ROLE_NODE_TYPE:
            return "cluster"
        elif role == ROLE_CLUSTER_INDEX:
            return cluster_idx
        elif role == ROLE_FILE_SIZE:
            return cluster.total_size
        elif role == ROLE_THUMBNAIL_PATH:
            # Use master file's thumbnail for cluster icon
            for f in cluster.files:
                if f.is_master and f.thumbnail_path:
                    return f.thumbnail_path
            # Fallback to first file with thumbnail
            for f in cluster.files:
                if f.thumbnail_path:
                    return f.thumbnail_path
            return ""
        elif role == Qt.ItemDataRole.ToolTipRole:
            return _tr("{0} copies \u00b7 {1} total").format(
                cluster.file_count, _format_size(cluster.total_size)
            )
        return None

    def _file_data(
        self, file_data: FileData, cluster: ClusterData, col: int, role: int
    ):
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:
                if file_data.is_master:
                    return "\u2605 " + os.path.basename(file_data.path)
                return os.path.basename(file_data.path)
            if col == COL_COPIES:
                return os.path.dirname(file_data.path)
            if col == COL_SIZE:
                return _format_size(file_data.size)
            if col == COL_MODIFIED:
                return file_data.modified_at[:10] if file_data.modified_at else ""
        elif role == ROLE_FILE_ID:
            return file_data.file_id
        elif role == ROLE_FILE_PATH:
            return file_data.path
        elif role == ROLE_FILE_SIZE:
            return file_data.size
        elif role == ROLE_IS_MASTER:
            return file_data.is_master
        elif role == ROLE_PIXEL_HASH:
            return cluster.pixel_hash
        elif role == ROLE_NODE_TYPE:
            return "file"
        elif role == ROLE_MODIFIED_AT:
            return file_data.modified_at
        elif role == ROLE_THUMBNAIL_PATH:
            return file_data.thumbnail_path
        elif role == Qt.ItemDataRole.ToolTipRole:
            tip = file_data.path
            if file_data.is_master:
                tip = _tr("\u2605 Master Copy") + "\n" + tip
            return tip
        return None
