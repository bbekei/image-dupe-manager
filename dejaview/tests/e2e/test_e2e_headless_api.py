"""
tests/e2e/test_e2e_headless_api.py — Headless integration tests through the API bridge.

Exercises the full Browse → Plan → Execute → Bin pipeline through DejaViewAPI,
the same interface the React frontend uses. No GUI, no pywebview, no browser.

Uses direct DB inserts to set up known duplicate groups, then calls API methods
exactly as the frontend would, verifying return shapes, data integrity, and
signal delivery.

Run with:
    cd dejaview
    python -m pytest tests/e2e/test_e2e_headless_api.py -m headless_e2e --no-cov -v
"""

import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.api import DejaViewAPI
from data.db import Database

pytestmark = [pytest.mark.headless_e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_file(
    db: Database, session_id: int, path: str, size: int = 1000
) -> int:
    return db.insert_file(session_id, path, size, _now(), _now())


def _set_pixel_hash(db: Database, file_id: int, pixel_hash: str) -> None:
    db.update_pixel_hash(file_id, pixel_hash, "")


def _create_real_file(path: str, size: int = 1000) -> None:
    """Create a real file on disk so executor can soft-delete it."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00" * size)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_env(db: Database, tmp_path: Path):
    """Full API environment: DejaViewAPI + mock window + temp dirs."""
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    trash_root = tmp_path / "trash"
    trash_root.mkdir()
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()

    api = DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=trash_root,
        app_dir=app_dir,
    )
    mock_window = MagicMock()
    api.set_window(mock_window)

    return api, db, scan_dir, trash_root


@pytest.fixture
def populated_session(api_env):
    """Create a session with 2 duplicate groups (3 files each) and 1 unique file.

    Group A (hash_aaa): file1, file2, file3 — sizes 3000, 2000, 1000
    Group B (hash_bbb): file4, file5, file6 — sizes 500, 1500, 1000
    Unique:             file7                — size 5000

    Returns (api, db, session_id, scan_dir, file_ids_by_group).
    """
    api, db, scan_dir, trash_root = api_env
    sid = db.create_session("Integration Test", _now())
    db.add_session_folder(sid, str(scan_dir))

    file_ids = {}

    # Group A: 3 files with the same pixel hash
    for i, (name, size) in enumerate([
        ("photos/img1.jpg", 3000),
        ("photos/img2.jpg", 2000),
        ("backup/img1_copy.jpg", 1000),
    ], start=1):
        path = str(scan_dir / name)
        _create_real_file(path, size)
        fid = _insert_file(db, sid, path, size)
        _set_pixel_hash(db, fid, "hash_aaa")
        file_ids[f"a{i}"] = fid

    # Group B: 3 files with a different pixel hash
    for i, (name, size) in enumerate([
        ("vacation/beach.jpg", 500),
        ("vacation/beach_hd.jpg", 1500),
        ("shared/beach_copy.jpg", 1000),
    ], start=1):
        path = str(scan_dir / name)
        _create_real_file(path, size)
        fid = _insert_file(db, sid, path, size)
        _set_pixel_hash(db, fid, "hash_bbb")
        file_ids[f"b{i}"] = fid

    # Unique file (no duplicates)
    path = str(scan_dir / "unique/landscape.jpg")
    _create_real_file(path, 5000)
    fid = _insert_file(db, sid, path, 5000)
    _set_pixel_hash(db, fid, "hash_unique")
    file_ids["unique"] = fid

    return api, db, sid, scan_dir, trash_root, file_ids


# ═══════════════════════════════════════════════════════════════════════════
# Browse flow — get_duplicate_groups, get_group_detail
# ═══════════════════════════════════════════════════════════════════════════


class TestBrowseFlow:
    """Frontend calls get_duplicate_groups → get_group_detail → set_file_action."""

    def test_get_duplicate_groups_returns_correct_groups(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        groups = api.get_duplicate_groups(sid)

        assert len(groups) == 2
        hashes = {g["pixel_hash"] for g in groups}
        assert hashes == {"hash_aaa", "hash_bbb"}
        for g in groups:
            assert g["file_count"] == 3
            assert len(g["files"]) == 3

    def test_get_duplicate_groups_pagination(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        page1 = api.get_duplicate_groups(sid, offset=0, limit=1)
        page2 = api.get_duplicate_groups(sid, offset=1, limit=1)

        assert len(page1) == 1
        assert len(page2) == 1
        assert page1[0]["pixel_hash"] != page2[0]["pixel_hash"]

    def test_get_group_detail_returns_file_metadata(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        files = api.get_group_detail(sid, "hash_aaa")

        assert len(files) == 3
        for f in files:
            assert "id" in f
            assert "path" in f
            assert "size" in f
            assert "pixel_hash" in f
            assert f["pixel_hash"] == "hash_aaa"
            # thumbnail_data should be present (empty string since no real thumbs)
            assert "thumbnail_data" in f

    def test_set_file_action_persists(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        api.set_file_action(fids["a1"], "keep", "file")
        api.set_file_action(fids["a2"], "delete", "file")
        api.set_file_action(fids["a3"], "delete", "file")

        actions = db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}
        assert action_map[fids["a1"]] == "keep"
        assert action_map[fids["a2"]] == "delete"
        assert action_map[fids["a3"]] == "delete"

    def test_keep_and_delete_others(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        group_ids = [fids["a1"], fids["a2"], fids["a3"]]
        result = api.keep_and_delete_others(fids["a2"], group_ids)

        assert "actions" in result
        action_map = {int(k): v for k, v in result["actions"].items()}
        assert action_map[fids["a2"]] == "keep"
        assert action_map[fids["a1"]] == "delete"
        assert action_map[fids["a3"]] == "delete"

        # Verify persistence in DB
        db_actions = db.get_file_actions_for_session(sid)
        db_map = {a["file_id"]: a["action"] for a in db_actions}
        assert db_map[fids["a2"]] == "keep"
        assert db_map[fids["a1"]] == "delete"
        assert db_map[fids["a3"]] == "delete"


# ═══════════════════════════════════════════════════════════════════════════
# Selection presets — apply_selection_preset
# ═══════════════════════════════════════════════════════════════════════════


class TestSelectionPresets:
    """Frontend calls apply_selection_preset with various strategies."""

    def test_keep_largest_marks_correct_files(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        result = api.apply_selection_preset(sid, "KEEP_LARGEST_FILE")

        assert "keep_count" in result
        assert "delete_count" in result
        assert result["keep_count"] >= 2  # one keeper per group
        assert result["delete_count"] >= 4  # rest are deletes

        # Verify the largest file in each group is kept
        actions = db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}

        # Group A: file a1 (3000 bytes) should be kept
        assert action_map.get(fids["a1"]) == "keep"
        assert action_map.get(fids["a2"]) == "delete"
        assert action_map.get(fids["a3"]) == "delete"

        # Group B: file b2 (1500 bytes) should be kept
        assert action_map.get(fids["b2"]) == "keep"

    def test_preset_on_specific_group(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        result = api.apply_selection_preset(
            sid, "KEEP_LARGEST_FILE", group_ids=["hash_aaa"]
        )

        actions = db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}

        # Only group A should have actions
        assert fids["a1"] in action_map
        assert fids["b1"] not in action_map

    def test_clear_all_actions_resets(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        api.apply_selection_preset(sid, "KEEP_LARGEST_FILE")
        actions_before = db.get_file_actions_for_session(sid)
        assert len(actions_before) > 0

        api.clear_all_actions(sid)

        actions_after = db.get_file_actions_for_session(sid)
        assert len(actions_after) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Plan review — get_plan_summary
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanReview:
    """Frontend displays plan summary before execution."""

    def test_plan_summary_matches_actions(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        # Set up specific actions
        api.set_file_action(fids["a1"], "keep", "file")
        api.set_file_action(fids["a2"], "delete", "file")
        api.set_file_action(fids["a3"], "delete", "file")
        api.set_file_action(fids["b1"], "ignore", "file")
        api.set_file_action(fids["b2"], "keep", "file")
        api.set_file_action(fids["b3"], "delete", "file")

        summary = api.get_plan_summary(sid)

        assert summary["keep_count"] == 2
        assert summary["delete_count"] == 3
        assert summary["ignore_count"] == 1
        assert summary["total_size_bytes"] > 0
        assert isinstance(summary["actions"], list)
        assert len(summary["actions"]) == 3  # 3 deletes

        # Each action has the expected shape
        for action in summary["actions"]:
            assert "file_id" in action
            assert "path" in action
            assert "size" in action
            assert "action" in action
            assert action["action"] == "delete"

    def test_empty_plan_summary(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        summary = api.get_plan_summary(sid)

        assert summary["keep_count"] == 0
        assert summary["delete_count"] == 0
        assert summary["actions"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Execution — execute_plan with signal verification
# ═══════════════════════════════════════════════════════════════════════════


class TestExecution:
    """Full execution pipeline: plan → execute → verify files moved + signals."""

    def test_execute_plan_soft_deletes_files(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        # Mark 2 files for deletion
        api.set_file_action(fids["a1"], "keep", "file")
        api.set_file_action(fids["a2"], "delete", "file")
        api.set_file_action(fids["a3"], "delete", "file")

        # Get paths before execution
        f2 = db.get_file(fids["a2"])
        f3 = db.get_file(fids["a3"])
        path2, path3 = Path(f2["path"]), Path(f3["path"])
        assert path2.exists()
        assert path3.exists()

        # Execute synchronously via executor.run() to avoid QThread complexity
        from core.executor import PlanExecutor

        executor = PlanExecutor(
            db=db, session_id=sid, trash_root=trash_root,
        )

        results = []
        executor.execution_complete.connect(lambda s, e: results.append((s, e)))
        executor.run()  # synchronous

        assert len(results) == 1
        success, errors = results[0]
        assert success == 2
        assert errors == 0

        # Original files should be gone
        assert not path2.exists()
        assert not path3.exists()

    def test_execute_plan_emits_events_via_api(self, populated_session):
        """Verify the API bridge emits events when execution runs."""
        api, db, sid, scan_dir, trash_root, fids = populated_session

        api.set_file_action(fids["a1"], "keep", "file")
        api.set_file_action(fids["a2"], "delete", "file")

        # Capture emitted events
        emitted_events = []
        original_emit = api._emit

        def capture_emit(event_name, detail):
            emitted_events.append((event_name, detail))
            original_emit(event_name, detail)

        api._emit = capture_emit

        # Run executor synchronously but through an approach that
        # uses the same signal wiring as execute_plan
        from PyQt6.QtCore import Qt
        from core.executor import PlanExecutor

        DC = Qt.ConnectionType.DirectConnection
        executor = PlanExecutor(
            db=db, session_id=sid, trash_root=trash_root,
        )
        executor.progress_updated.connect(
            lambda c, t: api._emit("exec:progress", {
                "current": c, "total": t, "action": "cleanup", "file_path": "",
            }),
            DC,
        )
        executor.execution_complete.connect(
            lambda s, e: api._emit("exec:complete", {
                "success": s, "errors": e,
                "summary": f"{s} succeeded, {e} failed",
            }),
            DC,
        )
        executor.execution_error.connect(
            lambda path, msg: api._emit("exec:error", {
                "message": msg, "file_path": path,
            }),
            DC,
        )
        executor.stage_changed.connect(
            lambda stage: api._emit("exec:progress", {
                "current": 0, "total": 0, "action": stage, "file_path": "",
            }),
            DC,
        )

        executor.run()

        # Should have received progress and complete events
        event_names = [e[0] for e in emitted_events]
        assert "exec:progress" in event_names
        assert "exec:complete" in event_names

        # Find the complete event and verify its payload
        complete_events = [e for e in emitted_events if e[0] == "exec:complete"]
        assert len(complete_events) == 1
        detail = complete_events[0][1]
        assert detail["success"] == 1
        assert detail["errors"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# Bin flow — get_bin_items, restore_from_bin, permanent_delete
# ═══════════════════════════════════════════════════════════════════════════


class TestBinFlow:
    """After execution, files appear in the bin and can be restored or purged."""

    def test_bin_items_appear_after_execution(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        api.set_file_action(fids["a1"], "keep", "file")
        api.set_file_action(fids["a2"], "delete", "file")
        api.set_file_action(fids["a3"], "delete", "file")

        from core.executor import PlanExecutor
        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash_root)
        executor.run()

        bin_items = api.get_bin_items(sid)
        assert len(bin_items) == 2

        for item in bin_items:
            assert "id" in item
            assert "original_path" in item
            assert "trash_path" in item
            assert "deleted_at" in item

    def test_restore_from_bin_recovers_file(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        api.set_file_action(fids["a1"], "keep", "file")
        api.set_file_action(fids["a2"], "delete", "file")

        f2 = db.get_file(fids["a2"])
        original_path = Path(f2["path"])

        from core.executor import PlanExecutor
        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash_root)
        executor.run()

        assert not original_path.exists()

        bin_items = api.get_bin_items(sid)
        assert len(bin_items) == 1

        api.restore_from_bin(bin_items[0]["id"])

        assert original_path.exists()

    def test_permanent_delete_removes_from_trash(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        api.set_file_action(fids["a1"], "keep", "file")
        api.set_file_action(fids["a2"], "delete", "file")

        from core.executor import PlanExecutor
        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash_root)
        executor.run()

        bin_items = api.get_bin_items(sid)
        assert len(bin_items) == 1
        trash_path = Path(bin_items[0]["trash_path"])
        assert trash_path.exists()

        api.permanent_delete([bin_items[0]["id"]])

        assert not trash_path.exists()


# ═══════════════════════════════════════════════════════════════════════════
# Session & summary flow
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionFlow:
    """Dashboard calls get_sessions and get_scan_summary."""

    def test_get_sessions_returns_latest(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        sessions = api.get_sessions()

        assert len(sessions) >= 1
        session = sessions[0]
        assert session["id"] == sid
        assert session["name"] == "Integration Test"
        assert "file_count" in session
        assert session["file_count"] == 7  # 3 + 3 + 1

    def test_scan_summary_counts(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        summary = api.get_scan_summary(sid)

        assert summary["session_id"] == sid
        assert summary["total_files"] == 7
        assert summary["total_groups"] == 2  # hash_aaa, hash_bbb
        assert summary["total_duplicates"] == 6  # 3 + 3
        assert summary["recoverable_bytes"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# Config flow
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigFlow:
    """Settings screen reads and writes config."""

    def test_get_set_config_roundtrip(self, api_env):
        api, db, scan_dir, trash_root = api_env

        config = api.get_app_config()
        assert config["language"] == "en"

        api.set_app_config("language", "hu")

        config2 = api.get_app_config()
        assert config2["language"] == "hu"

    def test_set_config_rejects_unknown_key(self, api_env):
        api, db, scan_dir, trash_root = api_env

        # Should silently ignore unknown keys (no crash)
        api.set_app_config("unknown_key", "value")

        config = api.get_app_config()
        assert "unknown_key" not in config


# ═══════════════════════════════════════════════════════════════════════════
# Full pipeline: Browse → Select → Plan → Execute → Bin → Restore
# ═══════════════════════════════════════════════════════════════════════════


class TestFullPipelineThroughAPI:
    """End-to-end flow exactly as the React frontend would drive it."""

    def test_complete_workflow(self, populated_session):
        api, db, sid, scan_dir, trash_root, fids = populated_session

        # 1. Dashboard: check summary
        summary = api.get_scan_summary(sid)
        assert summary["total_groups"] == 2

        # 2. Browse: load groups
        groups = api.get_duplicate_groups(sid)
        assert len(groups) == 2

        # 3. Browse: inspect group A
        detail = api.get_group_detail(sid, "hash_aaa")
        assert len(detail) == 3

        # 4. Browse: apply preset (keep largest)
        result = api.apply_selection_preset(sid, "KEEP_LARGEST_FILE")
        assert result["delete_count"] >= 4

        # 5. Plan: review
        plan = api.get_plan_summary(sid)
        assert plan["delete_count"] >= 4
        assert len(plan["actions"]) >= 4
        delete_paths = {a["path"] for a in plan["actions"]}

        # 6. Execute
        from core.executor import PlanExecutor
        executor = PlanExecutor(db=db, session_id=sid, trash_root=trash_root)
        results = []
        executor.execution_complete.connect(lambda s, e: results.append((s, e)))
        executor.run()

        success, errors = results[0]
        assert success == plan["delete_count"]
        assert errors == 0

        # 7. Verify: deleted files are gone from disk
        for path in delete_paths:
            assert not Path(path).exists(), f"File should be deleted: {path}"

        # 8. Bin: check items
        bin_items = api.get_bin_items(sid)
        assert len(bin_items) == plan["delete_count"]

        # 9. Bin: restore one file
        restored_item = bin_items[0]
        api.restore_from_bin(restored_item["id"])
        assert Path(restored_item["original_path"]).exists()

        # 10. After execution, deleted files are no longer 'active',
        #     so duplicate groups shrink or disappear
        summary2 = api.get_scan_summary(sid)
        assert summary2["recoverable_bytes"] == 0
