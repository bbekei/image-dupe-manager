"""Migration and version commands."""

import logging

from version import APP_VERSION

log = logging.getLogger(__name__)


class MigrationCommandsMixin:
    def get_app_version(self) -> str:
        """Return the application version string."""
        return APP_VERSION

    def get_migration_status(self) -> dict:
        """Return migration status for the frontend to act on."""
        mr = self._migration_result
        if mr is None:
            return {"needed": False, "app_version": APP_VERSION}
        return {
            "needed": mr.needs_user_confirmation,
            "from_version": mr.from_version,
            "to_version": mr.to_version,
            "breaking_changes": [
                {
                    "version": m.version,
                    "description": m.description,
                    "reason_key": m.breaking_reason,
                }
                for m in mr.breaking_migrations
            ],
            "backup_path": mr.backup_path,
            "app_version": APP_VERSION,
        }

    def confirm_migration(self) -> dict:
        """User confirmed breaking changes — run pending migrations now."""
        try:
            result = self._db.confirm_breaking_migrations()
            self._migration_result = result
            return {
                "ok": True,
                "validation_errors": result.validation_errors,
            }
        except Exception as exc:
            log.error("confirm_migration failed: %s", exc)
            return {"ok": False, "error": str(exc)}
