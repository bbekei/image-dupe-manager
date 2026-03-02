"""
tests/unit/test_planning_panel.py — Unit tests for PlanningPanel and PlanningFilterProxy.

Pluggable Views feature — planning workflow tests.
"""

import datetime

import pytest

from data.db import Database
from ui.results_model import (
    ROLE_FILE_ID,
    ROLE_IS_CROSS_LIBRARY,
    ROLE_IS_DUPLICATE,
    ROLE_NODE_TYPE,
    ROLE_PEER_USERNAMES,
    PlanningFilterProxy,
    ResultsTreeModel,
    SCOPE_ALL,
    SCOPE_CROSS_LIBRARY,
    SCOPE_LOCAL_DUPLICATES,
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_hash(prefix: str = "a") -> str:
    return (prefix * 32)[:32]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_with_dupes(db: Database):
    """Create a session with 4 files: 2 duplicates (hash_a), 1 cross-lib, 1 unique."""
    sid = db.create_session("test", _now())

    hash_a = _make_hash("a")
    hash_b = _make_hash("b")
    hash_c = _make_hash("c")

    fid1 = db.insert_file(sid, "/photos/img1.jpg", 100, _now(), _now())
    fid2 = db.insert_file(sid, "/photos/img2.jpg", 100, _now(), _now())
    fid3 = db.insert_file(sid, "/photos/img3.jpg", 200, _now(), _now())
    fid4 = db.insert_file(sid, "/photos/img4.jpg", 300, _now(), _now())

    # Make fid1 and fid2 duplicates (same hash).
    db.update_pixel_hash(fid1, hash_a, "/thumbs/1.jpg")
    db.update_pixel_hash(fid2, hash_a, "/thumbs/2.jpg")
    # fid3 has a unique hash.
    db.update_pixel_hash(fid3, hash_b, "/thumbs/3.jpg")
    # fid4 gets hash_c which we'll make cross-library.
    db.update_pixel_hash(fid4, hash_c, "/thumbs/4.jpg")

    # Create a remote peer with hash_c to make fid4 cross-library.
    peer_id = db.upsert_remote_peer("bob", _now())
    db.insert_remote_files(peer_id, [{"pixel_hash": hash_c, "filename": "remote.jpg"}])

    return sid, [fid1, fid2, fid3, fid4], [hash_a, hash_b, hash_c]


@pytest.fixture
def tree_model(db, session_with_dupes):
    """Build a ResultsTreeModel from the test session."""
    sid = session_with_dupes[0]
    tm = ResultsTreeModel()
    tm.load_from_db(db, sid)
    return tm


# ---------------------------------------------------------------------------
# PlanningFilterProxy tests
# ---------------------------------------------------------------------------

class TestPlanningFilterProxy:
    """PlanningFilterProxy: scope filtering + hiding decided items."""

    def test_local_duplicates_scope_shows_only_dupes(self, tree_model):
        proxy = PlanningFilterProxy()
        proxy.setSourceModel(tree_model.model)
        proxy.set_scope(SCOPE_LOCAL_DUPLICATES)

        visible = self._visible_files(proxy)
        # Only fid1 and fid2 (duplicates) should be visible.
        assert len(visible) == 2
        for item in visible:
            assert item["is_duplicate"] is True

    def test_cross_library_scope_shows_only_cross_lib(self, tree_model):
        proxy = PlanningFilterProxy()
        proxy.setSourceModel(tree_model.model)
        proxy.set_scope(SCOPE_CROSS_LIBRARY)

        visible = self._visible_files(proxy)
        # Only fid4 (cross-library) should be visible.
        assert len(visible) == 1
        assert visible[0]["is_cross_library"] is True

    def test_all_scope_shows_dupes_and_cross_lib(self, tree_model):
        proxy = PlanningFilterProxy()
        proxy.setSourceModel(tree_model.model)
        proxy.set_scope(SCOPE_ALL)

        visible = self._visible_files(proxy)
        # fid1, fid2 (dupes) + fid4 (cross-lib) = 3
        assert len(visible) == 3

    def test_decided_files_are_hidden(self, tree_model, session_with_dupes):
        _sid, file_ids, _hashes = session_with_dupes
        fid1 = file_ids[0]

        proxy = PlanningFilterProxy()
        proxy.setSourceModel(tree_model.model)
        proxy.set_scope(SCOPE_LOCAL_DUPLICATES)

        # Before: 2 visible.
        assert len(self._visible_files(proxy)) == 2

        # Mark fid1 as decided.
        proxy.set_decided_file_ids({fid1})
        assert len(self._visible_files(proxy)) == 1

    def test_add_decided_file_id(self, tree_model, session_with_dupes):
        _sid, file_ids, _hashes = session_with_dupes

        proxy = PlanningFilterProxy()
        proxy.setSourceModel(tree_model.model)
        proxy.set_scope(SCOPE_LOCAL_DUPLICATES)

        proxy.add_decided_file_id(file_ids[0])
        assert len(self._visible_files(proxy)) == 1

        proxy.add_decided_file_id(file_ids[1])
        assert len(self._visible_files(proxy)) == 0

    def test_empty_folders_hidden_when_all_decided(self, tree_model, session_with_dupes):
        _sid, file_ids, _hashes = session_with_dupes

        proxy = PlanningFilterProxy()
        proxy.setSourceModel(tree_model.model)
        proxy.set_scope(SCOPE_ALL)

        # Mark all actionable files as decided.
        proxy.set_decided_file_ids({file_ids[0], file_ids[1], file_ids[3]})

        # No files visible, and no folders either.
        visible = self._visible_files(proxy)
        assert len(visible) == 0

        # Check folder count too.
        folder_count = self._visible_folders(proxy)
        assert folder_count == 0

    # ── Helpers ────────────────────────────────────────────────────────

    def _visible_files(self, proxy, parent=None):
        from PyQt6.QtCore import QModelIndex
        if parent is None:
            parent = QModelIndex()
        result = []
        for row in range(proxy.rowCount(parent)):
            idx = proxy.index(row, 0, parent)
            node_type = idx.data(ROLE_NODE_TYPE)
            if node_type == "file":
                result.append({
                    "file_id": idx.data(ROLE_FILE_ID),
                    "is_duplicate": bool(idx.data(ROLE_IS_DUPLICATE)),
                    "is_cross_library": bool(idx.data(ROLE_IS_CROSS_LIBRARY)),
                })
            elif node_type == "folder":
                result.extend(self._visible_files(proxy, idx))
        return result

    def _visible_folders(self, proxy, parent=None):
        from PyQt6.QtCore import QModelIndex
        if parent is None:
            parent = QModelIndex()
        count = 0
        for row in range(proxy.rowCount(parent)):
            idx = proxy.index(row, 0, parent)
            if idx.data(ROLE_NODE_TYPE) == "folder":
                count += 1
                count += self._visible_folders(proxy, idx)
        return count


# ---------------------------------------------------------------------------
# DB action integration tests (no QWidget needed)
# ---------------------------------------------------------------------------

class TestActionPersistence:
    """Verify file_actions DB round-trip for planning use cases."""

    def test_set_action_and_get_decided(self, db, session_with_dupes):
        sid, file_ids, _ = session_with_dupes
        db.set_file_action(sid, file_ids[0], "delete")
        decided = db.get_decided_file_ids(sid)
        assert file_ids[0] in decided
        assert file_ids[1] not in decided

    def test_batch_folder_action(self, db, session_with_dupes):
        sid, file_ids, _ = session_with_dupes
        ts = _now()
        batch = [
            (sid, fid, "delete", "folder", ts)
            for fid in file_ids[:2]
        ]
        db.set_file_actions_batch(batch)
        decided = db.get_decided_file_ids(sid)
        assert decided == {file_ids[0], file_ids[1]}

    def test_clear_action_undo(self, db, session_with_dupes):
        sid, file_ids, _ = session_with_dupes
        db.set_file_action(sid, file_ids[0], "delete")
        db.clear_file_action(sid, file_ids[0])
        decided = db.get_decided_file_ids(sid)
        assert file_ids[0] not in decided

    def test_clear_all_actions(self, db, session_with_dupes):
        sid, file_ids, _ = session_with_dupes
        for fid in file_ids:
            db.set_file_action(sid, fid, "keep")
        db.clear_all_actions(sid)
        assert db.get_decided_file_ids(sid) == set()


# ---------------------------------------------------------------------------
# Brave mode logic tests (no QWidget needed — tests the DB/algorithm layer)
# ---------------------------------------------------------------------------

class TestBraveModeLogic:
    """UC3 — Keep Newest Only algorithm validation."""

    def test_newest_file_identified_correctly(self, db, session_with_dupes):
        sid, file_ids, hashes = session_with_dupes
        hash_a = hashes[0]

        # Set distinct timestamps for the two duplicates.
        db.conn.execute(
            "UPDATE files SET modified_at = ? WHERE id = ?",
            ("2024-01-01T00:00:00", file_ids[0]),
        )
        db.conn.execute(
            "UPDATE files SET modified_at = ? WHERE id = ?",
            ("2024-06-15T12:00:00", file_ids[1]),
        )
        db.conn.commit()

        # Simulate brave mode: find newest per group.
        groups = db.get_all_duplicate_file_ids(sid)
        assert hash_a in groups

        for _hash, fids in groups.items():
            files = [db.get_file(fid) for fid in fids]
            files.sort(key=lambda f: f["modified_at"] or "", reverse=True)
            newest = files[0]
            # fid2 (2024-06-15) should be newest.
            assert newest["id"] == file_ids[1]


# ---------------------------------------------------------------------------
# Cross-library peer info badge tests
# ---------------------------------------------------------------------------

class TestCrossLibraryPeerBadges:
    """Task 5.5 — verify peer usernames appear on cross-library tree items."""

    def test_cross_lib_file_has_peer_usernames(self, tree_model, session_with_dupes):
        """Cross-library file items carry ROLE_PEER_USERNAMES with the peer name."""
        _sid, file_ids, _hashes = session_with_dupes
        fid4 = file_ids[3]  # cross-library file
        item = tree_model.file_id_to_item[fid4]
        peers = item.data(ROLE_PEER_USERNAMES)
        assert peers == ["bob"]

    def test_local_duplicate_has_empty_peers(self, tree_model, session_with_dupes):
        """Local-only duplicates have an empty peer list."""
        _sid, file_ids, _hashes = session_with_dupes
        fid1 = file_ids[0]  # local duplicate
        item = tree_model.file_id_to_item[fid1]
        peers = item.data(ROLE_PEER_USERNAMES)
        assert peers == []

    def test_cross_lib_badge_text_contains_peer_name(self, tree_model, session_with_dupes):
        """Badge column for a cross-library file includes the peer username."""
        _sid, file_ids, _hashes = session_with_dupes
        fid4 = file_ids[3]
        item = tree_model.file_id_to_item[fid4]
        parent = item.parent() or tree_model.model.invisibleRootItem()
        badge_item = parent.child(item.row(), 1)
        text = badge_item.text()
        assert "bob" in text
        assert "\u2726" in text  # ✦ symbol

    def test_local_dup_badge_text_no_peer(self, tree_model, session_with_dupes):
        """Badge for local-only duplicates shows DUPLICATE without peer info."""
        _sid, file_ids, _hashes = session_with_dupes
        fid1 = file_ids[0]
        item = tree_model.file_id_to_item[fid1]
        parent = item.parent() or tree_model.model.invisibleRootItem()
        badge_item = parent.child(item.row(), 1)
        text = badge_item.text()
        assert "DUPLICATE" in text
        assert "bob" not in text

    def test_combined_dup_and_cross_lib_badge(self, db, session_with_dupes):
        """A file that is BOTH a local duplicate AND cross-library shows combined badge."""
        sid, file_ids, hashes = session_with_dupes
        hash_a = hashes[0]  # used by fid1 and fid2 (local duplicates)

        # Make hash_a also match a remote peer → fid1 and fid2 become cross-library too.
        peer_id = db.upsert_remote_peer("alice", _now())
        db.insert_remote_files(peer_id, [{"pixel_hash": hash_a, "filename": "alice_img.jpg"}])

        tm = ResultsTreeModel()
        tm.load_from_db(db, sid)

        fid1 = file_ids[0]
        item = tm.file_id_to_item[fid1]
        assert item.data(ROLE_IS_DUPLICATE) is True
        assert item.data(ROLE_IS_CROSS_LIBRARY) is True
        assert item.data(ROLE_PEER_USERNAMES) == ["alice"]

        parent = item.parent() or tm.model.invisibleRootItem()
        badge_item = parent.child(item.row(), 1)
        text = badge_item.text()
        # Combined badge: "● DUPLICATE ✦ alice"
        assert "DUPLICATE" in text
        assert "alice" in text
        assert "\u2726" in text

    def test_multiple_peers_for_same_hash(self, db, session_with_dupes):
        """When multiple peers share the same hash, all names appear in badge."""
        sid, file_ids, hashes = session_with_dupes
        hash_c = hashes[2]  # used by fid4, already matched by "bob"

        # Add a second peer with the same hash.
        peer_id = db.upsert_remote_peer("carol", _now())
        db.insert_remote_files(peer_id, [{"pixel_hash": hash_c, "filename": "carol_img.jpg"}])

        tm = ResultsTreeModel()
        tm.load_from_db(db, sid)

        fid4 = file_ids[3]
        item = tm.file_id_to_item[fid4]
        peers = item.data(ROLE_PEER_USERNAMES)
        assert sorted(peers) == ["bob", "carol"]

        parent = item.parent() or tm.model.invisibleRootItem()
        badge_item = parent.child(item.row(), 1)
        text = badge_item.text()
        assert "bob" in text
        assert "carol" in text

    def test_update_file_badge_sets_cross_lib_info(self, db, session_with_dupes):
        """update_file_badge() refreshes cross-library badge and peer data."""
        sid, file_ids, hashes = session_with_dupes
        hash_c = hashes[2]

        tm = ResultsTreeModel()
        tm.load_from_db(db, sid)

        fid4 = file_ids[3]
        tm.update_file_badge(fid4, hash_c)

        item = tm.file_id_to_item[fid4]
        assert item.data(ROLE_IS_CROSS_LIBRARY) is True
        assert item.data(ROLE_PEER_USERNAMES) == ["bob"]

        parent = item.parent() or tm.model.invisibleRootItem()
        badge_item = parent.child(item.row(), 1)
        assert "bob" in badge_item.text()


# ---------------------------------------------------------------------------
# Sibling auto-action tests (Issues 6 + 7 — DB-layer logic, no QWidget)
# ---------------------------------------------------------------------------

class TestSiblingAutoActions:
    """Verify sibling auto-mark logic for duplicate groups."""

    def _make_hash(self, prefix: str = "d") -> str:
        return (prefix * 32)[:32]

    def _insert(self, db, sid, path, size, modified, pixel_hash):
        fid = db.insert_file(sid, path, size, modified, modified)
        db.update_pixel_hash(fid, pixel_hash, f"/thumbs/{fid}.jpg")
        return fid

    def test_delete_one_of_two_auto_keeps_sibling(self, db):
        """Issue 6: deleting one of two copies should auto-keep the other."""
        sid = db.create_session("test", _now())
        h = self._make_hash("d")
        fid1 = self._insert(db, sid, "/a/img.jpg", 100, "2024-01-01", h)
        fid2 = self._insert(db, sid, "/b/img.jpg", 100, "2024-06-01", h)

        ts = _now()
        # User marks fid1 for deletion.
        db.set_file_action(sid, fid1, "delete", scope="file", decided_at=ts)

        # Simulate sibling logic: look up cluster, auto-keep undecided sibling.
        siblings = db.get_cluster_files(sid, h)
        decided = db.get_decided_file_ids(sid)
        assert len(siblings) == 2

        for sib in siblings:
            if sib["id"] != fid1 and sib["id"] not in decided:
                db.set_file_action(sid, sib["id"], "keep", scope="file", decided_at=ts)

        decided_after = db.get_decided_file_ids(sid)
        assert fid1 in decided_after
        assert fid2 in decided_after

        # Verify fid2 is marked as keep.
        actions = db.get_delete_actions_with_paths(sid)
        delete_ids = {r["file_id"] for r in actions}
        assert fid1 in delete_ids
        assert fid2 not in delete_ids

    def test_delete_does_not_auto_keep_when_sibling_already_decided(self, db):
        """If the sibling already has a decision, no auto-keep occurs."""
        sid = db.create_session("test", _now())
        h = self._make_hash("e")
        fid1 = self._insert(db, sid, "/a/img.jpg", 100, "2024-01-01", h)
        fid2 = self._insert(db, sid, "/b/img.jpg", 100, "2024-06-01", h)

        ts = _now()
        # Both already decided before the auto-action logic runs.
        db.set_file_action(sid, fid2, "ignore", scope="file", decided_at=ts)
        db.set_file_action(sid, fid1, "delete", scope="file", decided_at=ts)

        siblings = db.get_cluster_files(sid, h)
        decided = db.get_decided_file_ids(sid)
        undecided = [s for s in siblings if s["id"] != fid1 and s["id"] not in decided]
        assert len(undecided) == 0  # fid2 already decided → no auto-keep

    def test_delete_does_not_auto_keep_in_3plus_group(self, db):
        """Issue 6 only applies to 2-copy groups. 3+ groups should not auto-keep."""
        sid = db.create_session("test", _now())
        h = self._make_hash("f")
        fid1 = self._insert(db, sid, "/a/img.jpg", 100, "2024-01-01", h)
        fid2 = self._insert(db, sid, "/b/img.jpg", 100, "2024-06-01", h)
        fid3 = self._insert(db, sid, "/c/img.jpg", 100, "2024-09-01", h)

        ts = _now()
        db.set_file_action(sid, fid1, "delete", scope="file", decided_at=ts)

        siblings = db.get_cluster_files(sid, h)
        # 3 copies → auto-keep should NOT trigger.
        assert len(siblings) == 3

        decided = db.get_decided_file_ids(sid)
        assert fid2 not in decided
        assert fid3 not in decided

    def test_keep_in_3plus_prompts_batch_delete(self, db):
        """Issue 7: keeping in 3+ group → batch-delete all undecided siblings."""
        sid = db.create_session("test", _now())
        h = self._make_hash("g")
        fid1 = self._insert(db, sid, "/a/img.jpg", 100, "2024-01-01", h)
        fid2 = self._insert(db, sid, "/b/img.jpg", 100, "2024-06-01", h)
        fid3 = self._insert(db, sid, "/c/img.jpg", 100, "2024-09-01", h)

        ts = _now()
        # User marks fid1 as keep.
        db.set_file_action(sid, fid1, "keep", scope="file", decided_at=ts)

        siblings = db.get_cluster_files(sid, h)
        decided = db.get_decided_file_ids(sid)
        undecided = [s for s in siblings if s["id"] != fid1 and s["id"] not in decided]
        assert len(undecided) == 2

        # Simulate "Yes" answer → batch delete undecided siblings.
        batch = [(sid, s["id"], "delete", "file", ts) for s in undecided]
        db.set_file_actions_batch(batch)

        decided_after = db.get_decided_file_ids(sid)
        assert fid1 in decided_after
        assert fid2 in decided_after
        assert fid3 in decided_after

        # Only fid1 should be kept; fid2 and fid3 should be deleted.
        deletes = db.get_delete_actions_with_paths(sid)
        delete_ids = {r["file_id"] for r in deletes}
        assert fid1 not in delete_ids
        assert fid2 in delete_ids
        assert fid3 in delete_ids
