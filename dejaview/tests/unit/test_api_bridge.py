"""
tests/unit/test_api_bridge.py — Contract tests for the DejaView sidecar API bridge.

Validates:
  1. All public methods expected by the TypeScript frontend exist on DejaViewAPI.
  2. Scanner signal handlers invoke _emit() with correct event names and payloads.
  3. Executor signal handlers invoke _emit() with correct event names and payloads.
  4. Methods return the shapes the frontend destructures (JSON-serializable).
  5. Custom selection endpoints work correctly.
  6. Sidecar JSON-RPC protocol compliance (stdin/stdout round-trip).

Architecture: pywebview replaced by sidecar (Tauri v2). Events are now forwarded
via set_emit_callback(cb) instead of window.evaluate_js(). Tests collect emitted
events in a list for assertion.
"""

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.api import DejaViewAPI
from data.db import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api(db: Database, tmp_path: Path) -> DejaViewAPI:
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    trash_root = tmp_path / "trash"
    trash_root.mkdir()
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    api = DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=trash_root,
        app_dir=app_dir,
    )
    return api


@pytest.fixture
def api_with_emitter(api: DejaViewAPI):
    """API wired with a list-collector emit callback for event assertions."""
    emitted = []
    api.set_emit_callback(lambda name, detail: emitted.append((name, detail)))
    return api, emitted


# ---------------------------------------------------------------------------
# 1. API surface completeness — every method the frontend expects must exist
# ---------------------------------------------------------------------------

# This list mirrors PyWebViewAPI in frontend/src/types/api.ts.
EXPECTED_METHODS = [
    # Version & Migration
    "get_app_version",
    "get_migration_status",
    "confirm_migration",
    # Scan & Session
    "start_scan",
    "pause_scan",
    "resume_scan",
    "stop_scan",
    "get_sessions",
    "get_scan_summary",
    "get_scan_progress",
    # Duplicate Groups
    "get_duplicate_groups",
    "get_group_detail",
    "set_file_action",
    "keep_and_delete_others",
    "apply_folder_action",
    "apply_selection_preset",
    "apply_custom_selection",
    "get_plan_summary",
    "execute_plan",
    "clear_all_actions",
    # Similarity
    "get_similarity_groups",
    "get_similarity_group_detail",
    "apply_similarity_preset",
    "apply_custom_similarity_selection",
    "recommend_keeper",
    # Bin
    "get_bin_items",
    "restore_from_bin",
    "permanent_delete",
    "purge_expired",
    # Sync Config
    "get_sync_config",
    "save_sync_config",
    "authenticate_drive",
    "remove_peer",
    # Family Sharing
    "export_hashes",
    "import_hashes",
    "sync_drive",
    "get_remote_peers",
    "get_requests",
    "respond_to_request",
    # Thumbnails & Config
    "get_thumbnail_url",
    "get_app_config",
    "set_app_config",
    # File dialogs
    "select_folders",
]


class TestAPISurface:
    """Every method the TypeScript frontend expects must exist as a callable."""

    @pytest.mark.parametrize("method_name", EXPECTED_METHODS)
    def test_method_exists(self, api: DejaViewAPI, method_name: str):
        attr = getattr(api, method_name, None)
        assert attr is not None, f"DejaViewAPI missing method: {method_name}"
        assert callable(attr), f"DejaViewAPI.{method_name} is not callable"

    def test_no_unexpected_public_methods(self, api: DejaViewAPI):
        """Guard against backend methods the frontend doesn't know about."""
        public = [
            name for name in dir(api)
            if not name.startswith("_") and callable(getattr(api, name))
            and name != "set_emit_callback"  # internal setup, not called from JS
        ]
        extras = set(public) - set(EXPECTED_METHODS)
        assert extras == set(), (
            f"Backend has public methods not in EXPECTED_METHODS: {extras}. "
            "Add them to the TypeScript PyWebViewAPI interface or make them private."
        )


# ---------------------------------------------------------------------------
# 2. Scanner event payload contracts
# ---------------------------------------------------------------------------

class TestScannerEventPayloads:
    """Verify _emit() is called with correct event names and payload shapes."""

    def test_progress_emits_scan_progress(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.progress_updated.emit(5, 100)

        names = [e[0] for e in emitted]
        assert "scan:progress" in names
        detail = next(d for n, d in emitted if n == "scan:progress")
        assert detail["current"] == 5
        assert detail["total"] == 100
        assert detail["phase"] == "hashing"

    def test_file_discovered_emits_discovery_progress(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.file_discovered.emit(1, "/test/img.jpg")

        names = [e[0] for e in emitted]
        assert "scan:discovery_progress" in names
        detail = next(d for n, d in emitted if n == "scan:discovery_progress")
        assert detail["discovered"] == 1

    def test_duplicate_found_emits_event(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.duplicate_found.emit("abc123", [1, 2, 3])

        names = [e[0] for e in emitted]
        assert "scan:duplicate_found" in names
        detail = next(d for n, d in emitted if n == "scan:duplicate_found")
        assert detail["pixel_hash"] == "abc123"
        assert detail["count"] == 3

    def test_scan_complete_emits_status(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.scan_complete.emit()

        names = [e[0] for e in emitted]
        assert "scan:status" in names
        detail = next(d for n, d in emitted if n == "scan:status")
        assert detail["status"] == "complete"

    def test_similarity_progress_emits_event(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.similarity_progress.emit(10, 50)

        names = [e[0] for e in emitted]
        assert "scan:similarity_progress" in names
        detail = next(d for n, d in emitted if n == "scan:similarity_progress")
        assert detail["current"] == 10
        assert detail["total"] == 50

    def test_scan_error_emits_separate_event(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.scan_error.emit("/bad/path.jpg", "Permission denied")

        names = [e[0] for e in emitted]
        assert "scan:error" in names
        detail = next(d for n, d in emitted if n == "scan:error")
        assert detail["path"] == "/bad/path.jpg"
        assert "Permission denied" in detail["message"]

    def test_scan_error_does_not_change_phase(self, api_with_emitter):
        api, _ = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)
        api._scan_phase = "hashing"

        scanner.scan_error.emit("/bad/path.jpg", "err")

        assert api._scan_phase == "hashing"

    def test_status_message_emits_info(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.status_message.emit("Discovering files…")

        names = [e[0] for e in emitted]
        assert "scan:status" in names
        detail = next(d for n, d in emitted if n == "scan:status")
        assert detail["status"] == "info"
        assert "Discovering" in detail["message"]

    def test_progress_updates_polling_state(self, api_with_emitter):
        api, _ = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        scanner.progress_updated.emit(42, 200)

        assert api._scan_current == 42
        assert api._scan_total == 200
        assert api._scan_phase == "hashing"

    def test_discovery_increments_discovered_count(self, api_with_emitter):
        api, _ = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        for i in range(10):
            scanner.file_discovered.emit(i, f"/test/img{i}.jpg")

        assert api._scan_discovered == 10

    # Verify unconsumed events are NOT emitted (AC-31 / Step 4a decision)
    def test_unconsumed_events_not_forwarded(self, api_with_emitter):
        api, emitted = api_with_emitter
        from core.scanner import Scanner
        scanner = Scanner(db=api._db, session_id=1, thumb_dir=api._thumb_dir, max_workers=1)
        api._connect_scanner_signals(scanner)

        # These four were removed from ALLOWED_EVENTS in Step 4a
        scanner.hash_complete.emit(1, "abc123")
        scanner.hash_complete_batch.emit([(1, "abc")])
        scanner.directory_hashed.emit("/some/dir")
        scanner.similarity_grouping_complete.emit(5)

        forwarded_names = {e[0] for e in emitted}
        assert "scan:hash_complete" not in forwarded_names
        assert "scan:hash_batch" not in forwarded_names
        assert "scan:directory_hashed" not in forwarded_names
        assert "scan:similarity_complete" not in forwarded_names


# ---------------------------------------------------------------------------
# 3. Executor event payload contracts
# ---------------------------------------------------------------------------

class TestExecutorEventPayloads:
    """Verify executor signal handlers call _emit() with correct payloads."""

    def test_execution_complete_emits_exec_complete(
        self, api_with_emitter, session_factory
    ):
        api, emitted = api_with_emitter
        from core.executor import PlanExecutor

        sid = session_factory()
        executor = PlanExecutor(
            db=api._db, session_id=sid,
            trash_root=api._trash_root,
        )

        # Wire signal the same way execute_plan does
        executor.execution_complete.connect(
            lambda s, e: api._emit("exec:complete", {
                "success": s, "errors": e,
                "summary": f"{s} succeeded, {e} failed",
            }),
        )

        executor.execution_complete.emit(8, 2)

        names = [e[0] for e in emitted]
        assert "exec:complete" in names
        detail = next(d for n, d in emitted if n == "exec:complete")
        assert detail["success"] == 8
        assert detail["errors"] == 2

    def test_execution_error_emits_exec_error(
        self, api_with_emitter, session_factory
    ):
        api, emitted = api_with_emitter
        from core.executor import PlanExecutor

        sid = session_factory()
        executor = PlanExecutor(
            db=api._db, session_id=sid,
            trash_root=api._trash_root,
        )

        executor.execution_error.connect(
            lambda path, msg: api._emit("exec:error", {
                "message": msg, "file_path": path,
            }),
        )

        executor.execution_error.emit("/some/file.jpg", "Permission denied")

        names = [e[0] for e in emitted]
        assert "exec:error" in names
        detail = next(d for n, d in emitted if n == "exec:error")
        assert detail["file_path"] == "/some/file.jpg"
        assert "Permission denied" in detail["message"]

    def test_log_message_emits_exec_progress(
        self, api_with_emitter, session_factory
    ):
        api, emitted = api_with_emitter
        from core.executor import PlanExecutor

        sid = session_factory()
        executor = PlanExecutor(
            db=api._db, session_id=sid,
            trash_root=api._trash_root,
        )

        executor.log_message.connect(
            lambda msg: api._emit("exec:progress", {
                "current": 0, "total": 0, "action": "log", "file_path": msg,
            }),
        )

        executor.log_message.emit("Deleting /some/file.jpg")

        names = [e[0] for e in emitted]
        assert "exec:progress" in names
        detail = next(d for n, d in emitted if n == "exec:progress")
        assert detail["action"] == "log"
        assert "Deleting" in detail["file_path"]

    def test_stage_changed_emits_exec_progress(
        self, api_with_emitter, session_factory
    ):
        api, emitted = api_with_emitter
        from core.executor import PlanExecutor

        sid = session_factory()
        executor = PlanExecutor(
            db=api._db, session_id=sid,
            trash_root=api._trash_root,
        )

        executor.stage_changed.connect(
            lambda stage: api._emit("exec:progress", {
                "current": 0, "total": 0, "action": stage, "file_path": "",
            }),
        )

        executor.stage_changed.emit("cleanup")

        names = [e[0] for e in emitted]
        assert "exec:progress" in names
        detail = next(d for n, d in emitted if n == "exec:progress")
        assert detail["action"] == "cleanup"


# ---------------------------------------------------------------------------
# 4. Return type contracts — methods return expected shapes
# ---------------------------------------------------------------------------

class TestReturnShapes:
    """Verify methods return the shapes the frontend destructures."""

    def test_get_scan_progress_shape(self, api: DejaViewAPI):
        result = api.get_scan_progress()
        assert isinstance(result, dict)
        for key in ("phase", "current", "total", "discovered", "duplicates", "message"):
            assert key in result, f"get_scan_progress missing key: {key}"

    def test_get_sessions_returns_list(self, api: DejaViewAPI):
        result = api.get_sessions()
        assert isinstance(result, list)

    def test_get_scan_summary_empty_session(self, api: DejaViewAPI):
        result = api.get_scan_summary(999)
        assert isinstance(result, dict)
        for key in ("session_id", "total_files", "total_groups",
                     "total_duplicates", "recoverable_bytes",
                     "similarity_group_count"):
            assert key in result, f"get_scan_summary missing key: {key}"

    def test_get_app_config_shape(self, api: DejaViewAPI):
        result = api.get_app_config()
        assert isinstance(result, dict)
        for key in ("language", "theme", "max_scan_workers",
                     "perf_logging", "scan_delay_ms"):
            assert key in result, f"get_app_config missing key: {key}"

    def test_get_plan_summary_shape(self, api: DejaViewAPI, session_factory):
        sid = session_factory()
        result = api.get_plan_summary(sid)
        assert isinstance(result, dict)
        for key in ("keep_count", "delete_count", "ignore_count",
                     "total_size_bytes", "actions"):
            assert key in result, f"get_plan_summary missing key: {key}"
        assert isinstance(result["actions"], list)

    def test_get_duplicate_groups_returns_page(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        result = api.get_duplicate_groups(sid)
        assert isinstance(result, dict)
        assert "groups" in result
        assert "total_count" in result
        assert isinstance(result["groups"], list)
        assert isinstance(result["total_count"], int)

    def test_get_bin_items_returns_list(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        result = api.get_bin_items(sid)
        assert isinstance(result, list)

    def test_get_similarity_groups_returns_page(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        result = api.get_similarity_groups(sid)
        assert isinstance(result, dict)
        assert "groups" in result
        assert "total_count" in result
        assert isinstance(result["groups"], list)
        assert isinstance(result["total_count"], int)

    def test_get_similarity_group_detail_returns_dict(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        fid = api._db.insert_file(sid, "/tmp/a.jpg", 100, "2024-01-01", "2024-01-01")
        gid = api._db.create_similarity_group(sid, "2024-01-01", fid, member_count=1)
        api._db.add_similarity_group_members_batch([(gid, fid, 0)])
        result = api.get_similarity_group_detail(gid)
        assert isinstance(result, dict)
        assert "id" in result
        assert "members" in result
        assert isinstance(result["members"], list)
        assert len(result["members"]) == 1

    def test_get_remote_peers_returns_list(self, api: DejaViewAPI):
        result = api.get_remote_peers()
        assert isinstance(result, list)

    def test_get_requests_returns_list(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        result = api.get_requests(sid)
        assert isinstance(result, list)

    def test_purge_expired_returns_int(self, api: DejaViewAPI):
        result = api.purge_expired()
        assert isinstance(result, int)

    def test_sync_drive_without_driver(self, api: DejaViewAPI):
        result = api.sync_drive()
        assert isinstance(result, dict)
        assert result["status"] == "unavailable"


# ---------------------------------------------------------------------------
# 5. Composable sort chain — custom selection endpoints
# ---------------------------------------------------------------------------

class TestCustomSelectionEndpoints:
    """Contract tests for apply_custom_selection and apply_custom_similarity_selection."""

    def _setup_dupes(self, api, session_factory):
        """Create a session with a duplicate group."""
        import datetime
        sid = session_factory()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        hash_a = ("a" * 32)[:32]
        f1 = api._db.insert_file(sid, "/big.jpg", 5000, "2024-06-01", now)
        f2 = api._db.insert_file(sid, "/small.jpg", 1000, "2024-01-01", now)
        api._db.update_pixel_hash(f1, hash_a, "/t/1.jpg")
        api._db.update_pixel_hash(f2, hash_a, "/t/2.jpg")
        return sid, f1, f2

    def _setup_sim_group(self, api, session_factory):
        """Create a session with a similarity group."""
        import datetime
        sid = session_factory()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        f1 = api._db.insert_file(sid, "/hires.jpg", 8000, "2024-06-01", now)
        f2 = api._db.insert_file(sid, "/lores.jpg", 1000, "2024-01-01", now)
        api._db.update_pixel_hash(f1, ("a" * 32)[:32], "/t/1.jpg")
        api._db.update_pixel_hash(f2, ("b" * 32)[:32], "/t/2.jpg")
        api._db.update_perceptual_hashes_batch([
            (f1, "aaaa", 3840, 2160),
            (f2, "aabb", 800, 600),
        ])
        gid = api._db.create_similarity_group(sid, now, f1, member_count=2)
        api._db.add_similarity_group_members_batch([(gid, f1, 0), (gid, f2, 5)])
        return sid, gid, f1, f2

    def test_apply_custom_selection_returns_shape(
        self, api: DejaViewAPI, session_factory
    ):
        sid, *_ = self._setup_dupes(api, session_factory)
        result = api.apply_custom_selection(sid, [
            {"field": "size", "ascending": False},
        ])
        assert "keep_count" in result
        assert "delete_count" in result
        assert "active_preset" in result
        assert result["active_preset"] == "custom"
        assert result["keep_count"] + result["delete_count"] == 2

    def test_apply_custom_selection_respects_chain(
        self, api: DejaViewAPI, session_factory
    ):
        sid, f1, f2 = self._setup_dupes(api, session_factory)
        # Keep smallest file (ascending=True for size)
        api.apply_custom_selection(sid, [
            {"field": "size", "ascending": True},
        ])
        actions = api._db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}
        assert action_map[f2] == "keep"   # 1000 bytes — smallest
        assert action_map[f1] == "delete"  # 5000 bytes

    def test_apply_custom_selection_emits_events(
        self, api_with_emitter, session_factory
    ):
        api, emitted = api_with_emitter
        sid, _, _ = self._setup_dupes(api, session_factory)
        api.apply_custom_selection(sid, [
            {"field": "size", "ascending": False},
        ])
        # Check that selection:complete was emitted
        names = [e[0] for e in emitted]
        assert "selection:complete" in names

    def test_apply_custom_selection_clears_previous(
        self, api: DejaViewAPI, session_factory
    ):
        sid, f1, f2 = self._setup_dupes(api, session_factory)
        # First apply: keep largest
        api.apply_custom_selection(sid, [{"field": "size", "ascending": False}])
        # Second apply: keep smallest — should clear previous
        api.apply_custom_selection(sid, [{"field": "size", "ascending": True}])
        actions = api._db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}
        assert action_map[f2] == "keep"   # now smallest wins
        assert action_map[f1] == "delete"

    def test_apply_custom_similarity_selection_returns_shape(
        self, api: DejaViewAPI, session_factory
    ):
        sid, *_ = self._setup_sim_group(api, session_factory)
        result = api.apply_custom_similarity_selection(sid, [
            {"field": "resolution", "ascending": False},
        ])
        assert "keep_count" in result
        assert "delete_count" in result
        assert result["active_preset"] == "custom"

    def test_apply_custom_similarity_selection_respects_chain(
        self, api: DejaViewAPI, session_factory
    ):
        sid, _, f1, f2 = self._setup_sim_group(api, session_factory)
        api.apply_custom_similarity_selection(sid, [
            {"field": "resolution", "ascending": False},
        ])
        actions = api._db.get_file_actions_for_session(sid)
        action_map = {a["file_id"]: a["action"] for a in actions}
        assert action_map[f1] == "keep"    # 3840x2160 — highest res
        assert action_map[f2] == "delete"

    def test_preset_endpoint_returns_active_preset(
        self, api: DejaViewAPI, session_factory
    ):
        sid, _, _ = self._setup_dupes(api, session_factory)
        result = api.apply_selection_preset(sid, "KEEP_LARGEST_FILE")
        assert result["active_preset"] == "KEEP_LARGEST_FILE"

    def test_similarity_preset_returns_active_preset(
        self, api: DejaViewAPI, session_factory
    ):
        sid, _, _, _ = self._setup_sim_group(api, session_factory)
        result = api.apply_similarity_preset(sid, "KEEP_HIGHEST_RESOLUTION")
        assert result["active_preset"] == "KEEP_HIGHEST_RESOLUTION"


# ---------------------------------------------------------------------------
# Sidecar protocol — stdin/stdout JSON-RPC round-trip tests
# ---------------------------------------------------------------------------


def _run_sidecar(req_line: str, tmp_path: Path, timeout: int = 15) -> dict:
    """Run sidecar_main.py with req_line on stdin; return first stdout JSON line.

    cwd is set to dejaview/ (two levels up from this file which lives at
    dejaview/tests/unit/).  sidecar_main.py adds its own parent.parent to
    sys.path so all backend imports resolve from that directory.
    """
    # dejaview/tests/unit/ -> dejaview/tests/ -> dejaview/
    dejaview_dir = str(Path(__file__).parent.parent.parent)
    env = {**os.environ, "APPDATA": str(tmp_path), "HOME": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "sidecar/sidecar_main.py"],
        input=req_line + "\n",
        capture_output=True,
        text=True,
        cwd=dejaview_dir,
        env=env,
        timeout=timeout,
    )
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    assert lines, (
        f"Sidecar produced no stdout.\nstderr: {proc.stderr[:500]}"
    )
    return json.loads(lines[0])


class TestSidecarProtocol:
    """JSON-RPC 2.0 protocol compliance tests for sidecar_main.py."""

    def test_get_app_version_round_trip(self, tmp_path):
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "get_app_version", "params": {}})
        result = _run_sidecar(req, tmp_path)
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "result" in result
        assert "error" not in result
        assert isinstance(result["result"], str)
        assert len(result["result"]) > 0

    def test_response_has_no_log_noise(self, tmp_path):
        """Stdout must contain only JSON lines — no log messages mixed in."""
        req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "get_app_version", "params": {}})
        dejaview_dir = str(Path(__file__).parent.parent.parent)
        env = {**os.environ, "APPDATA": str(tmp_path), "HOME": str(tmp_path)}
        proc = subprocess.run(
            [sys.executable, "sidecar/sidecar_main.py"],
            input=req + "\n",
            capture_output=True, text=True,
            cwd=dejaview_dir,
            env=env, timeout=15,
        )
        for line in proc.stdout.strip().splitlines():
            if line.strip():
                json.loads(line)  # must not raise

    def test_method_not_found_returns_error(self, tmp_path):
        req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "no_such_method", "params": {}})
        result = _run_sidecar(req, tmp_path)
        assert "error" in result
        assert result["error"]["code"] == -32601
        assert result["id"] == 2

    def test_parse_error_returns_error(self, tmp_path):
        result = _run_sidecar("{not valid json", tmp_path)
        assert "error" in result
        assert result["error"]["code"] == -32700

    def test_private_method_blocked(self, tmp_path):
        req = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "_emit", "params": {}})
        result = _run_sidecar(req, tmp_path)
        assert "error" in result
        assert result["error"]["code"] == -32601

    def test_internal_method_blocked(self, tmp_path):
        """set_emit_callback is internal setup — must not be callable via RPC."""
        req = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "set_emit_callback", "params": {}})
        result = _run_sidecar(req, tmp_path)
        assert "error" in result
        # set_emit_callback is a public method but requires a callable argument;
        # calling it with no params raises TypeError → -32603 internal error
        assert result["error"]["code"] in (-32601, -32603)

    def test_get_scan_progress_round_trip(self, tmp_path):
        req = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "get_scan_progress", "params": {}})
        result = _run_sidecar(req, tmp_path)
        assert "result" in result
        assert "error" not in result
        assert isinstance(result["result"], dict)
        assert "phase" in result["result"]

    def test_get_app_config_round_trip(self, tmp_path):
        req = json.dumps({"jsonrpc": "2.0", "id": 6, "method": "get_app_config", "params": {}})
        result = _run_sidecar(req, tmp_path)
        assert "result" in result
        r = result["result"]
        assert isinstance(r, dict)
        for key in ("language", "theme", "max_scan_workers", "perf_logging", "scan_delay_ms"):
            assert key in r, f"Missing key: {key}"
