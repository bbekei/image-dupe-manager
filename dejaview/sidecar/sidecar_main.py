"""
sidecar/sidecar_main.py — DejaView Python sidecar entrypoint (Tauri v2 migration).

Replaces main.py for the Tauri architecture. Communicates with the Tauri host
via JSON-RPC 2.0 over stdin/stdout (one JSON object per line).

Protocol:
  Requests (Tauri → sidecar):  {"jsonrpc": "2.0", "id": N, "method": "...", "params": {...}}
  Responses (sidecar → Tauri): {"jsonrpc": "2.0", "id": N, "result": ...}
  Error responses:             {"jsonrpc": "2.0", "id": N, "error": {"code": -32xxx, "message": "..."}}
  Notifications (sidecar → Tauri, no id): {"jsonrpc": "2.0", "method": "event", "params": {"name": "...", "detail": {...}}}

Stdout buffering (R4): line_buffering=True + explicit flush() after every write.
Unconsumed events decision (Architect, 2026-03-16): omit scan:hash_complete,
  scan:hash_batch, scan:directory_hashed, scan:similarity_complete from stdout.
  These four events are not consumed by any frontend listener.
"""

import io
import json
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# ── R4: Force line-buffered stdout immediately ────────────────────────────────
# Must happen before any other stdout write. Python may buffer stdout when
# running as a subprocess; line_buffering=True ensures each line is flushed
# as it is written, preventing silent hangs.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)

log = logging.getLogger(__name__)

# ── JSON-RPC error codes ──────────────────────────────────────────────────────
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

# ── Forwarded event set (consumed by frontend) ────────────────────────────────
_FORWARDED_EVENTS = frozenset({
    "scan:discovery_progress",
    "scan:progress",
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


def _write(obj: dict) -> None:
    """Write a JSON object as a single line to stdout and flush."""
    line = json.dumps(obj, ensure_ascii=True)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _ok(req_id, result) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id, code: int, message: str) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def _notify(event_name: str, detail: dict) -> None:
    """Forward a backend event as a JSON-RPC notification (no id)."""
    if event_name not in _FORWARDED_EVENTS:
        return
    _write({"jsonrpc": "2.0", "method": "event", "params": {"name": event_name, "detail": detail}})


def _app_dir() -> Path:
    """Return the platform-appropriate app data directory."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    app_dir = base / "DejaView"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def _base_dir() -> Path:
    """Return the app base directory (handles PyInstaller frozen bundles)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def _read_user_version(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _backup_database(db_path: Path, current_version: int) -> Path:
    backup = db_path.with_suffix(f".v{current_version}.bak")
    if not backup.exists():
        shutil.copy2(str(db_path), str(backup))
    return backup


def main() -> None:
    app_dir = _app_dir()

    log_path = app_dir / "dejaview-sidecar.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(str(log_path), encoding="utf-8")],
    )

    db_path = app_dir / "library.db"
    thumb_dir = app_dir / "thumbs"
    thumb_dir.mkdir(exist_ok=True)
    trash_root = app_dir / ".dejaview_trash"

    # Add dejaview/ to sys.path so imports resolve when running as sidecar
    dejaview_dir = str(Path(__file__).parent.parent)
    if dejaview_dir not in sys.path:
        sys.path.insert(0, dejaview_dir)

    from data.db import Database, LATEST_SCHEMA_VERSION, MigrationError
    from version import APP_VERSION

    # Pre-migration backup
    backup_path = ""
    if db_path.exists():
        current_version = _read_user_version(db_path)
        if current_version < LATEST_SCHEMA_VERSION:
            backup_path = str(_backup_database(db_path, current_version))

    try:
        db = Database(db_path)
        migration_result = db.open()
    except MigrationError as exc:
        log.error("Database migration failed: %s", exc)
        sys.exit(1)

    migration_result.backup_path = backup_path

    # Startup cleanup
    try:
        orphans = db.cleanup_orphaned_thumbnails()
        for p in orphans:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
    except Exception as exc:
        log.warning("Startup thumbnail cleanup failed: %s", exc)

    try:
        from core.trash import purge_expired
        purged = purge_expired(trash_root)
        if purged:
            log.info("Purged %d expired trash files at startup.", len(purged))
    except Exception as exc:
        log.warning("Startup trash purge failed: %s", exc)

    # DriveSync initialisation
    from data.sync import DriveSync
    creds_path = app_dir / "credentials.json"
    secrets_path = _base_dir() / "resources" / "client_secrets.json"
    drive_sync = DriveSync(db=db, credentials_path=creds_path, client_secrets_path=secrets_path)
    try:
        from data.sync import load_credentials, save_credentials
        creds = load_credentials(creds_path)
        if creds and creds.valid:
            drive_sync._build_service(creds)
        elif creds and creds.expired and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                save_credentials(creds, creds_path)
                drive_sync._build_service(creds)
            except Exception as exc:
                log.info("Could not refresh Drive credentials: %s", exc)
    except Exception:
        pass

    from backend.api import DejaViewAPI
    api = DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=trash_root,
        app_dir=app_dir,
        drive_sync=drive_sync,
        migration_result=migration_result,
    )
    api.set_emit_callback(_notify)

    log.info("DejaView sidecar %s ready (schema v%d)", APP_VERSION, LATEST_SCHEMA_VERSION)

    # ── Main dispatch loop ────────────────────────────────────────────────────
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _err(None, _PARSE_ERROR, f"Parse error: {exc}")
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if not method:
            _err(req_id, _INVALID_REQUEST, "Missing method")
            continue

        log.info("Dispatch: %s (id=%s)", method, req_id)

        handler = getattr(api, method, None)
        if handler is None or method.startswith("_"):
            _err(req_id, _METHOD_NOT_FOUND, f"Method not found: {method}")
            continue

        try:
            if isinstance(params, dict):
                result = handler(**params)
            elif isinstance(params, list):
                result = handler(*params)
            else:
                result = handler()
            log.info("Done: %s -> %r", method, result if not isinstance(result, (list, dict)) else type(result).__name__)
            _ok(req_id, result)
        except Exception as exc:
            log.error("Method %s failed: %s", method, exc, exc_info=True)
            _err(req_id, _INTERNAL_ERROR, str(exc))

    db.close()
    log.info("Sidecar exiting cleanly.")


if __name__ == "__main__":
    main()
