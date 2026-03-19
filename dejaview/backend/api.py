"""
backend/api.py — DejaView API class.

Exposes Python backend functions to the Tauri frontend via JSON-RPC IPC.
Each public method is callable from the sidecar dispatch loop in
sidecar/sidecar_main.py.

This module owns the API class and its shared infrastructure (_emit,
__init__). Domain logic is split into backend/commands/ modules:

  scan_commands.py       — scan, session, progress
  file_action_commands.py — group actions, presets, custom selection
  similarity_commands.py  — similarity groups and selection
  bin_commands.py         — soft-delete, restore, purge
  sync_commands.py        — export, import, Drive sync, peers, requests
  config_commands.py      — app config, thumbnail URLs
  migration_commands.py   — version, migration status, confirm
"""

import logging
from pathlib import Path

from data.db import Database, MigrationResult

from backend.commands.bin_commands import BinCommandsMixin
from backend.commands.config_commands import ConfigCommandsMixin
from backend.commands.file_action_commands import FileActionCommandsMixin
from backend.commands.migration_commands import MigrationCommandsMixin
from backend.commands.scan_commands import ScanCommandsMixin
from backend.commands.similarity_commands import SimilarityCommandsMixin
from backend.commands.sync_commands import SyncCommandsMixin

log = logging.getLogger(__name__)

ALLOWED_EVENTS: frozenset[str] = frozenset({
    "scan:progress",
    "scan:discovery_progress",
    "scan:status",
    "scan:duplicate_found",
    "scan:similarity_progress",
    "scan:error",
    "exec:progress",
    "exec:complete",
    "exec:error",
    "selection:progress",
    "selection:complete",
})


class DejaViewAPI(
    MigrationCommandsMixin,
    ScanCommandsMixin,
    FileActionCommandsMixin,
    SimilarityCommandsMixin,
    BinCommandsMixin,
    SyncCommandsMixin,
    ConfigCommandsMixin,
):
    """API class exposed to the Tauri sidecar. All public methods are callable via JSON-RPC."""

    def __init__(
        self,
        db: Database,
        thumb_dir: Path,
        trash_root: Path,
        app_dir: Path,
        drive_sync=None,
        migration_result: MigrationResult | None = None,
    ):
        self._db = db
        self._thumb_dir = thumb_dir
        self._trash_root = trash_root
        self._app_dir = app_dir
        self._drive_sync = drive_sync
        self._migration_result = migration_result
        self._scanner = None
        self._executor = None
        self._window = None
        self._emit_callback = None

        # Scan progress state (updated by signal handlers, read by polling)
        self._scan_phase = "idle"
        self._scan_current = 0
        self._scan_total = 0
        self._scan_discovered = 0
        self._scan_duplicates = 0
        self._scan_message = ""

    def set_emit_callback(self, cb) -> None:
        """Register a callback for event forwarding: cb(event_name, detail)."""
        self._emit_callback = cb

    def _emit(self, event_name: str, detail: dict) -> None:
        if self._emit_callback:
            self._emit_callback(event_name, detail)
