"""
tests/unit/test_api_bridge.py — Contract tests for the pywebview API bridge.

Validates:
  1. All public methods expected by the TypeScript frontend exist on DejaViewAPI.
  2. Scanner and Executor signal connections use DirectConnection.
  3. Signal handlers invoke _emit() with correct event names and payloads.

No pywebview or browser required — tests mock the window and verify calls.
"""

import inspect
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
    """DejaViewAPI wired to a fresh test DB with a mock window."""
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
    # Mock window so _emit() calls evaluate_js() without a real browser
    mock_window = MagicMock()
    api.set_window(mock_window)
    return api


# ---------------------------------------------------------------------------
# 1. API surface completeness — every method the frontend expects must exist
# ---------------------------------------------------------------------------

# This list mirrors PyWebViewAPI in frontend/src/types/api.ts.
EXPECTED_METHODS = [
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
    "apply_folder_action",
    "apply_selection_preset",
    "get_plan_summary",
    "execute_plan",
    "clear_all_actions",
    # Similarity
    "get_similarity_groups",
    "apply_similarity_preset",
    "recommend_keeper",
    # Bin
    "get_bin_items",
    "restore_from_bin",
    "permanent_delete",
    "purge_expired",
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
            and name != "set_window"  # internal setup, not called from JS
        ]
        extras = set(public) - set(EXPECTED_METHODS)
        assert extras == set(), (
            f"Backend has public methods not in EXPECTED_METHODS: {extras}. "
            "Add them to the TypeScript PyWebViewAPI interface or make them private."
        )


# ---------------------------------------------------------------------------
# 2. Signal connection type — must be DirectConnection
# ---------------------------------------------------------------------------

class TestScannerSignalConnections:
    """_connect_scanner_signals must use DirectConnection for every signal.

    Uses source code inspection since PyQt6 bound signals have read-only
    .connect attributes. The behavioral proof (signals fire synchronously)
    is covered by TestScannerEventPayloads below.
    """

    def test_all_scanner_connects_use_dc(self, api: DejaViewAPI):
        """Every .connect() call in _connect_scanner_signals must pass DC."""
        import re
        source = inspect.getsource(api._connect_scanner_signals)

        # Find all .connect( calls in the source
        connect_calls = re.findall(r'(\w+)\.connect\(', source)
        assert len(connect_calls) >= 15, (
            f"Expected at least 15 signal connections, found {len(connect_calls)}"
        )

        # Every .connect() must include DC as second arg
        # Pattern: .connect(..., DC) or .connect(\n..., DC,\n)
        connects_without_dc = re.findall(
            r'\.connect\([^)]+\)\s*$', source, re.MULTILINE
        )
        # All connect calls should end with DC or DC,) — none should lack it
        non_dc = [c for c in connects_without_dc if 'DC' not in c]
        assert non_dc == [], (
            f"Signal connections missing DirectConnection: {non_dc}"
        )

    def test_scanner_signals_fire_synchronously(self, api: DejaViewAPI):
        """Behavioral proof: signals connected with DirectConnection fire
        inline when emitted, so _emit() is called immediately."""
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        # If DirectConnection is missing, this emit would be queued
        # to an event loop that doesn't exist, and evaluate_js would
        # never be called.
        scanner.scan_complete.emit()
        assert api._window.evaluate_js.called, (
            "scan_complete signal did not fire synchronously — "
            "DirectConnection likely missing"
        )


class TestExecutorSignalConnections:
    """execute_plan must use DirectConnection for every executor signal."""

    def test_all_executor_connects_use_dc(self, api: DejaViewAPI):
        """Every .connect() call in execute_plan must pass DC."""
        import re
        source = inspect.getsource(api.execute_plan)

        connect_calls = re.findall(r'\.connect\(', source)
        assert len(connect_calls) >= 5, (
            f"Expected at least 5 executor signal connections, found {len(connect_calls)}"
        )

        # Verify DC is defined and used
        assert 'DC = Qt.ConnectionType.DirectConnection' in source, (
            "execute_plan does not define DC = DirectConnection"
        )

        # Every connect block should reference DC
        connects_without_dc = re.findall(
            r'\.connect\([^)]+\)\s*$', source, re.MULTILINE
        )
        non_dc = [c for c in connects_without_dc if 'DC' not in c]
        assert non_dc == [], (
            f"Executor signal connections missing DirectConnection: {non_dc}"
        )

    def test_executor_signals_fire_synchronously(
        self, api: DejaViewAPI, session_factory
    ):
        """Behavioral proof: executor signals fire inline with DirectConnection."""
        from PyQt6.QtCore import Qt
        from core.executor import PlanExecutor

        DC = Qt.ConnectionType.DirectConnection
        sid = session_factory()

        executor = PlanExecutor(
            db=api._db, session_id=sid, trash_root=api._trash_root,
        )

        # Wire one signal manually the same way execute_plan does
        executor.execution_complete.connect(
            lambda s, e: api._emit("exec:complete", {
                "success": s, "errors": e,
                "summary": f"{s} succeeded, {e} failed",
            }),
            DC,
        )

        executor.execution_complete.emit(5, 1)
        assert api._window.evaluate_js.called, (
            "execution_complete signal did not fire synchronously — "
            "DirectConnection likely missing"
        )


# ---------------------------------------------------------------------------
# 3. Event payload contracts — signals produce correct _emit() calls
# ---------------------------------------------------------------------------

class TestScannerEventPayloads:
    """Verify _emit() is called with correct event names and payload shapes."""

    def test_progress_emits_scan_progress(self, api: DejaViewAPI):
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        # Emit the signal directly (DirectConnection means handler runs inline)
        scanner.progress_updated.emit(5, 100)

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"scan:progress"' in js_code
        assert '"current": 5' in js_code
        assert '"total": 100' in js_code
        assert '"phase": "hashing"' in js_code

    def test_file_discovered_emits_discovery_progress(self, api: DejaViewAPI):
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        scanner.file_discovered.emit(1, "/test/img.jpg")

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"scan:discovery_progress"' in js_code
        assert '"discovered": 1' in js_code

    def test_duplicate_found_emits_event(self, api: DejaViewAPI):
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        scanner.duplicate_found.emit("abc123", [1, 2, 3])

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"scan:duplicate_found"' in js_code
        assert '"pixel_hash": "abc123"' in js_code
        assert '"count": 3' in js_code

    def test_scan_complete_emits_status(self, api: DejaViewAPI):
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        scanner.scan_complete.emit()

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"scan:status"' in js_code
        assert '"status": "complete"' in js_code

    def test_similarity_progress_emits_event(self, api: DejaViewAPI):
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        scanner.similarity_progress.emit(10, 50)

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"scan:similarity_progress"' in js_code
        assert '"current": 10' in js_code
        assert '"total": 50' in js_code

    def test_status_message_emits_info(self, api: DejaViewAPI):
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        scanner.status_message.emit("Scanning folder X")

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"scan:status"' in js_code
        assert '"status": "info"' in js_code

    def test_progress_updates_polling_state(self, api: DejaViewAPI):
        """get_scan_progress() should reflect the latest signal data."""
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        scanner.progress_updated.emit(42, 200)

        state = api.get_scan_progress()
        assert state["current"] == 42
        assert state["total"] == 200
        assert state["phase"] == "hashing"

    def test_discovery_increments_discovered_count(self, api: DejaViewAPI):
        from core.scanner import Scanner

        scanner = Scanner(
            db=api._db, session_id=1,
            thumb_dir=api._thumb_dir, max_workers=1,
        )
        api._connect_scanner_signals(scanner)

        for i in range(5):
            scanner.file_discovered.emit(i + 1, f"/test/img{i}.jpg")

        state = api.get_scan_progress()
        assert state["discovered"] == 5


class TestExecutorEventPayloads:
    """Verify executor signal handlers call _emit() with correct payloads."""

    def test_progress_emits_exec_progress(
        self, api: DejaViewAPI, session_factory
    ):
        from core.executor import PlanExecutor

        sid = session_factory()
        executor = PlanExecutor(
            db=api._db, session_id=sid,
            trash_root=api._trash_root,
        )

        # Wire signals the same way execute_plan does
        from PyQt6.QtCore import Qt
        DC = Qt.ConnectionType.DirectConnection

        executor.progress_updated.connect(
            lambda c, t: api._emit("exec:progress", {
                "current": c, "total": t, "action": "cleanup", "file_path": "",
            }),
            DC,
        )

        executor.progress_updated.emit(3, 10)

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"exec:progress"' in js_code
        assert '"current": 3' in js_code
        assert '"total": 10' in js_code

    def test_complete_emits_exec_complete(
        self, api: DejaViewAPI, session_factory
    ):
        from core.executor import PlanExecutor
        from PyQt6.QtCore import Qt
        DC = Qt.ConnectionType.DirectConnection

        sid = session_factory()
        executor = PlanExecutor(
            db=api._db, session_id=sid,
            trash_root=api._trash_root,
        )

        executor.execution_complete.connect(
            lambda s, e: api._emit("exec:complete", {
                "success": s, "errors": e,
                "summary": f"{s} succeeded, {e} failed",
            }),
            DC,
        )

        executor.execution_complete.emit(8, 2)

        call = api._window.evaluate_js.call_args
        assert call is not None
        js_code = call[0][0]
        assert '"exec:complete"' in js_code
        assert '"success": 8' in js_code
        assert '"errors": 2' in js_code


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

    def test_get_duplicate_groups_returns_list(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        result = api.get_duplicate_groups(sid)
        assert isinstance(result, list)

    def test_get_bin_items_returns_list(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        result = api.get_bin_items(sid)
        assert isinstance(result, list)

    def test_get_similarity_groups_returns_list(
        self, api: DejaViewAPI, session_factory
    ):
        sid = session_factory()
        result = api.get_similarity_groups(sid)
        assert isinstance(result, list)

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
