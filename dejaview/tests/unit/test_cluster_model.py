"""
Tests for ui/cluster_model.py — Hash-grouped cluster model.

UX Redesign Phase 5 — Advanced Cleanup.
"""

import datetime

import pytest

from ui.cluster_model import (
    ClusterModel,
    ROLE_FILE_ID,
    ROLE_FILE_PATH,
    ROLE_FILE_SIZE,
    ROLE_IS_MASTER,
    ROLE_NODE_TYPE,
    ROLE_PIXEL_HASH,
)

from PyQt6.QtCore import QModelIndex, Qt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _insert_file(db, session_id, path, size, modified_at, pixel_hash):
    fid = db.insert_file(session_id, path, size, modified_at, _now())
    if pixel_hash:
        db.update_pixel_hash(fid, pixel_hash, f"/thumbs/{pixel_hash}.jpg")
    return fid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestClusterModel:
    """Tests for ClusterModel QAbstractItemModel."""

    def test_empty_load(self, db, session_factory):
        sid = session_factory()
        model = ClusterModel()
        model.load_from_db(db, sid)
        assert model.rowCount() == 0
        assert model.cluster_count() == 0

    def test_single_group(self, db, session_factory):
        sid = session_factory()
        h = "a" * 32
        _insert_file(db, sid, "/photos/img1.jpg", 1000, "2024-01-01", h)
        _insert_file(db, sid, "/backup/img1.jpg", 800, "2024-01-01", h)

        model = ClusterModel()
        model.load_from_db(db, sid)

        assert model.cluster_count() == 1
        assert model.total_files() == 2
        assert model.rowCount() == 1

        # Cluster row
        idx = model.index(0, 0)
        assert idx.isValid()
        assert model.data(idx, ROLE_NODE_TYPE) == "cluster"
        assert model.data(idx, ROLE_PIXEL_HASH) == h

        # File children
        child_count = model.rowCount(idx)
        assert child_count == 2

        child0 = model.index(0, 0, idx)
        assert child0.isValid()
        assert model.data(child0, ROLE_NODE_TYPE) == "file"
        assert model.data(child0, ROLE_FILE_ID) is not None

    def test_master_copy_identified(self, db, session_factory):
        sid = session_factory()
        h = "b" * 32
        _insert_file(db, sid, "/small.jpg", 500, "2024-01-01", h)
        f2 = _insert_file(db, sid, "/large.jpg", 2000, "2024-01-01", h)

        model = ClusterModel()
        model.load_from_db(db, sid)

        idx = model.index(0, 0)
        # Check that master is identified
        master_found = False
        for row in range(model.rowCount(idx)):
            child = model.index(row, 0, idx)
            if model.data(child, ROLE_IS_MASTER):
                assert model.data(child, ROLE_FILE_ID) == f2
                master_found = True
        assert master_found

    def test_multiple_groups(self, db, session_factory):
        sid = session_factory()
        h1 = "c" * 32
        h2 = "d" * 32
        _insert_file(db, sid, "/a1.jpg", 100, "2024-01-01", h1)
        _insert_file(db, sid, "/a2.jpg", 200, "2024-01-01", h1)
        _insert_file(db, sid, "/b1.jpg", 300, "2024-01-01", h2)
        _insert_file(db, sid, "/b2.jpg", 400, "2024-01-01", h2)

        model = ClusterModel()
        model.load_from_db(db, sid)

        assert model.cluster_count() == 2
        assert model.total_files() == 4

    def test_waste_calculation(self, db, session_factory):
        sid = session_factory()
        h = "e" * 32
        _insert_file(db, sid, "/big.jpg", 1000, "2024-01-01", h)
        _insert_file(db, sid, "/small.jpg", 200, "2024-01-01", h)

        model = ClusterModel()
        model.load_from_db(db, sid)

        # Waste = total - largest = 1200 - 1000 = 200
        assert model.total_waste_bytes() == 200

    def test_search_filter(self, db, session_factory):
        sid = session_factory()
        h = "f" * 32
        _insert_file(db, sid, "/photos/vacation.jpg", 1000, "2024-01-01", h)
        _insert_file(db, sid, "/backup/vacation.jpg", 800, "2024-01-01", h)

        model = ClusterModel()
        model.load_from_db(db, sid, search_text="vacation")
        assert model.cluster_count() == 1

        model.load_from_db(db, sid, search_text="nonexistent")
        assert model.cluster_count() == 0

    def test_min_copies_filter(self, db, session_factory):
        sid = session_factory()
        h1 = "a" * 32  # 2 copies
        h2 = "b" * 32  # 3 copies
        _insert_file(db, sid, "/a1.jpg", 100, "2024-01-01", h1)
        _insert_file(db, sid, "/a2.jpg", 200, "2024-01-01", h1)
        _insert_file(db, sid, "/b1.jpg", 300, "2024-01-01", h2)
        _insert_file(db, sid, "/b2.jpg", 400, "2024-01-01", h2)
        _insert_file(db, sid, "/b3.jpg", 500, "2024-01-01", h2)

        model = ClusterModel()
        model.load_from_db(db, sid, min_copies=3)
        assert model.cluster_count() == 1  # Only h2 has 3+ copies

    def test_parent_index(self, db, session_factory):
        sid = session_factory()
        h = "a" * 32
        _insert_file(db, sid, "/a.jpg", 100, "2024-01-01", h)
        _insert_file(db, sid, "/b.jpg", 200, "2024-01-01", h)

        model = ClusterModel()
        model.load_from_db(db, sid)

        # Root parent
        cluster_idx = model.index(0, 0)
        assert not model.parent(cluster_idx).isValid()

        # File parent
        file_idx = model.index(0, 0, cluster_idx)
        parent = model.parent(file_idx)
        assert parent.isValid()
        assert parent.row() == 0

    def test_column_count(self, db, session_factory):
        model = ClusterModel()
        assert model.columnCount() == 4

    def test_display_data(self, db, session_factory):
        sid = session_factory()
        h = "a" * 32
        _insert_file(db, sid, "/photos/test.jpg", 1048576, "2024-06-15", h)
        _insert_file(db, sid, "/backup/test.jpg", 524288, "2024-01-01", h)

        model = ClusterModel()
        model.load_from_db(db, sid)

        # Cluster display data
        idx = model.index(0, 0)
        name = model.data(idx, Qt.ItemDataRole.DisplayRole)
        assert name is not None  # Representative filename

        copies_idx = model.index(0, 1)
        copies = model.data(copies_idx, Qt.ItemDataRole.DisplayRole)
        assert copies == "2"
