"""
main.py — DejaView entry point (pywebview + React UI).

Responsibilities:
  - Open (or create) SQLite database at %APPDATA%\\DejaView\\library.db.
  - Run startup cleanup (orphan thumbnails, expired trash).
  - Create DriveSync if sync is configured.
  - Initialize PyQt6 QCoreApplication (needed for QThread-based Scanner/Executor).
  - Create pywebview window hosting the React frontend.
  - Expose Python backend API to JavaScript via pywebview bridge.
"""

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

import webview

from backend.api import DejaViewAPI
from data.db import Database

log = logging.getLogger(__name__)


def _app_dir() -> Path:
    """Return %APPDATA%\\DejaView, creating it if needed."""
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    app_dir = base / "DejaView"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def _base_dir() -> Path:
    """Return the app base directory (handles PyInstaller frozen bundles)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _startup_thumbnail_cleanup(db: Database, thumb_dir: Path) -> None:
    """Remove orphaned thumbnails left by a previously interrupted session."""
    try:
        orphans = db.cleanup_orphaned_thumbnails()
        for p in orphans:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError as exc:
                log.warning("Could not remove orphan thumbnail %s: %s", p, exc)
    except Exception as exc:
        log.warning("Startup thumbnail cleanup failed: %s", exc)


def _startup_trash_purge(trash_root: Path) -> None:
    """Purge expired soft-deleted files at startup (30-day recovery window)."""
    try:
        from core.trash import purge_expired

        purged = purge_expired(trash_root)
        if purged:
            log.info("Purged %d expired trash files at startup.", len(purged))
    except Exception as exc:
        log.warning("Startup trash purge failed: %s", exc)


def _create_drive_sync(db: Database, app_dir: Path):
    """Create a DriveSync instance if sync is configured."""
    from data.sync import DriveSync, load_credentials, save_credentials

    creds_path = app_dir / "credentials.json"
    secrets_path = _base_dir() / "resources" / "client_secrets.json"

    drive_sync = DriveSync(
        db=db,
        credentials_path=creds_path,
        client_secrets_path=secrets_path,
    )

    creds = None
    try:
        creds = load_credentials(creds_path)
    except Exception:
        pass

    if creds and creds.valid:
        drive_sync._build_service(creds)
    elif creds and creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
            save_credentials(creds, creds_path)
            drive_sync._build_service(creds)
        except Exception as exc:
            log.info("Could not refresh Drive credentials at startup: %s", exc)

    return drive_sync


def _init_qt_app():
    """Initialize a headless QCoreApplication for QThread support.

    Scanner and PlanExecutor are QThread subclasses that require a
    QCoreApplication event loop. We create one and run it in a
    background thread so it doesn't block pywebview's own event loop.
    """
    from PyQt6.QtCore import QCoreApplication

    if QCoreApplication.instance() is None:
        app = QCoreApplication(sys.argv)
        app.setApplicationName("DejaView")
        return app
    return QCoreApplication.instance()


def _get_frontend_url(dev_mode: bool) -> str:
    """Return the URL for the frontend, either dev server or built files."""
    if dev_mode:
        return "http://localhost:5173"

    # Production: serve from frontend/dist/
    dist_dir = _base_dir() / "frontend" / "dist"
    index_html = dist_dir / "index.html"
    if index_html.exists():
        return str(index_html)

    # Fallback: check if we're in a PyInstaller bundle
    bundle_index = _base_dir() / "dist" / "index.html"
    if bundle_index.exists():
        return str(bundle_index)

    log.error("Frontend build not found. Run 'npm run build' in frontend/")
    return str(index_html)


def main() -> None:
    parser = argparse.ArgumentParser(description="DejaView — duplicate image finder")
    parser.add_argument(
        "--perf",
        action="store_true",
        help="Enable performance telemetry CSV (also via DEJAVIEW_PERF=1)",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use Vite dev server (http://localhost:5173) instead of built files",
    )
    args = parser.parse_args()

    if args.perf:
        os.environ["DEJAVIEW_PERF"] = "1"

    app_dir = _app_dir()

    # Log to a file so errors are visible in windowed/frozen builds
    log_path = app_dir / "dejaview.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(str(log_path), encoding="utf-8")],
    )

    # Initialize QCoreApplication for QThread support (Scanner, PlanExecutor)
    qt_app = _init_qt_app()

    db_path = app_dir / "library.db"
    thumb_dir = app_dir / "thumbs"
    thumb_dir.mkdir(exist_ok=True)
    trash_root = app_dir / ".dejaview_trash"

    db = Database(db_path)
    db.open()

    _startup_thumbnail_cleanup(db, thumb_dir)
    _startup_trash_purge(trash_root)

    drive_sync = _create_drive_sync(db, app_dir)

    # Create the API bridge
    api = DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=trash_root,
        app_dir=app_dir,
        drive_sync=drive_sync,
    )

    # Determine frontend URL
    frontend_url = _get_frontend_url(args.dev)

    # Create the pywebview window
    window = webview.create_window(
        "DejaView",
        url=frontend_url,
        js_api=api,
        width=1280,
        height=800,
        min_size=(800, 600),
    )

    # Pass window reference to API for event forwarding
    api.set_window(window)

    def on_closing():
        """Cleanup on window close."""
        db.close()

    window.events.closing += on_closing

    # Start the Qt event loop in a background thread for QThread support
    def run_qt_loop():
        qt_app.exec()

    qt_thread = threading.Thread(target=run_qt_loop, daemon=True)
    qt_thread.start()

    # Start pywebview (blocks until window is closed)
    webview.start(debug=args.dev)

    # Cleanup
    qt_app.quit()


if __name__ == "__main__":
    main()
