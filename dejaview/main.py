"""
main.py — DejaView entry point (plan §Architecture).

Responsibilities:
  - Auto-detect Windows system locale; load Hungarian (hu) or English (en).
  - Open (or create) SQLite database at %APPDATA%\\DejaView\\library.db.
  - Run startup orphan-thumbnail cleanup (plan §Session cleanup).
  - Create DriveSync if sync is configured (plan §Phase 6).
  - Create and show MainWindow.
  - Trigger sync-on-start (plan §Workflow 5 — On app start).
"""

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QLocale, QTranslator, QLibraryInfo
from PyQt6.QtWidgets import QApplication

from data.db import Database
from data.sync import DriveSync
from ui.main_window import MainWindow

log = logging.getLogger(__name__)


def _app_dir() -> Path:
    """Return %APPDATA%\\DejaView, creating it if needed."""
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    app_dir = base / "DejaView"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def _base_dir() -> Path:
    """Return the app base directory (handles PyInstaller frozen bundles)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _load_translators(app: QApplication, db_path: Path | None = None) -> None:
    """
    Load Hungarian translation based on user preference or system locale.
    Falls back to English (built-in source strings) for any other locale.
    Plan §Language / Localization.
    """
    # Read user's language preference from app_config (if DB exists).
    lang_pref = "auto"
    if db_path and db_path.exists():
        try:
            db = Database(db_path)
            db.open()
            config = db.get_app_config()
            if config:
                lang_pref = config["language"]
            db.close()
        except Exception as exc:
            log.warning("Could not read language preference: %s", exc)

    if lang_pref == "auto":
        lang = QLocale.system().name()[:2]   # 'hu', 'en', 'de', …
    else:
        lang = lang_pref

    if lang != "hu":
        return

    i18n_dir = str(_base_dir() / "resources" / "i18n")

    # Qt base strings (standard button labels, dialogs).
    # Try bundled copy first (PyInstaller), fall back to Qt installation path.
    qt_tr = QTranslator(app)
    if not qt_tr.load("qt_hu", i18n_dir):
        qt_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        qt_tr.load("qt_hu", qt_path)
    if not qt_tr.isEmpty():
        app.installTranslator(qt_tr)

    # App strings (compiled from resources/i18n/app_hu.ts -> app_hu.qm).
    app_tr = QTranslator(app)
    if app_tr.load("app_hu", i18n_dir):
        app.installTranslator(app_tr)
    else:
        log.warning("Hungarian QM not found in %s — using English strings.", i18n_dir)


def _startup_thumbnail_cleanup(db: Database, thumb_dir: Path) -> None:
    """
    Remove orphaned thumbnails left by a previously interrupted session.
    Plan §Session cleanup — runs once at startup before the window opens.
    """
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


def _create_drive_sync(db: Database, app_dir: Path) -> DriveSync | None:
    """Create a DriveSync instance if sync is configured.

    Plan §Phase 6 — DriveSync is created at startup and passed to MainWindow.
    Returns None if sync is not configured or client_secrets.json is missing.
    """
    creds_path = app_dir / "credentials.json"
    secrets_path = _base_dir() / "resources" / "client_secrets.json"

    drive_sync = DriveSync(
        db=db,
        credentials_path=creds_path,
        client_secrets_path=secrets_path,
    )

    # Try to load existing credentials (silent — no browser popup at startup).
    creds = None
    try:
        from data.sync import load_credentials
        creds = load_credentials(creds_path)
    except Exception:
        pass

    if creds and creds.valid:
        drive_sync._build_service(creds)
    elif creds and creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            from data.sync import save_credentials
            save_credentials(creds, creds_path)
            drive_sync._build_service(creds)
        except Exception as exc:
            log.info("Could not refresh Drive credentials at startup: %s", exc)

    return drive_sync


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="DejaView — duplicate image finder")
    parser.add_argument(
        "--perf", action="store_true",
        help="Enable performance telemetry CSV (also via DEJAVIEW_PERF=1)",
    )
    args = parser.parse_args()

    if args.perf:
        os.environ["DEJAVIEW_PERF"] = "1"

    app_dir = _app_dir()

    # Log to a file so errors are visible even in windowed/frozen builds
    # where sys.stderr is None.
    log_path = app_dir / "dejaview.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(str(log_path), encoding="utf-8")],
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DejaView")
    app.setOrganizationName("DejaView")

    db_path = app_dir / "library.db"
    _load_translators(app, db_path=db_path)
    thumb_dir = app_dir / "thumbs"
    thumb_dir.mkdir(exist_ok=True)

    db = Database(db_path)
    db.open()

    _startup_thumbnail_cleanup(db, thumb_dir)

    # UX Redesign Phase 3 — purge expired soft-deleted files (30-day window).
    _startup_trash_purge(app_dir / ".dejaview_trash")

    # Plan §Phase 6 — create DriveSync if configured.
    drive_sync = _create_drive_sync(db, app_dir)

    window = MainWindow(db=db, thumb_dir=thumb_dir, drive_sync=drive_sync)

    # Performance telemetry (--perf flag or DEJAVIEW_PERF=1 env var).
    if os.environ.get("DEJAVIEW_PERF"):
        from core.perf_monitor import PerformanceMonitor
        perf = PerformanceMonitor(output_dir=app_dir, enabled=True)
        window.set_perf_monitor(perf)
        log.info("Performance telemetry enabled")

    window.show()

    # Plan §Workflow 5 — On app start: silently download peer exports.
    window.sync_on_start()

    exit_code = app.exec()
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
