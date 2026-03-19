"""App configuration and thumbnail URL commands."""

import logging

log = logging.getLogger(__name__)


class ConfigCommandsMixin:
    def get_thumbnail_url(self, thumb_path: str) -> str:
        """Return a file:// URL for the thumbnail.

        Only returns URLs for paths that resolve inside the thumbnail
        directory to prevent referencing arbitrary files.
        """
        if not thumb_path:
            return ""
        if not self._is_safe_thumb_path(thumb_path):
            log.warning("Blocked thumbnail URL outside thumb_dir: %s", thumb_path)
            return ""
        normalized = thumb_path.replace("\\", "/")
        return f"file:///{normalized}"

    def get_app_config(self) -> dict:
        config = self._db.get_app_config()
        if not config:
            return {
                "language": "en",
                "theme": "dark",
                "max_scan_workers": 4,
                "perf_logging": False,
                "scan_delay_ms": 0,
            }
        return {
            "language": config["language"],
            "theme": config["theme"],
            "max_scan_workers": config["max_scan_workers"],
            "perf_logging": bool(config["perf_logging"]),
            "scan_delay_ms": self._db.get_scan_delay_ms(),
        }

    def set_app_config(self, key: str, value) -> None:
        """Update a single configuration value.

        Validates key membership and value types before writing to DB.
        """
        if not isinstance(key, str):
            return
        ALLOWED_TYPES: dict[str, type | tuple[type, ...]] = {
            "language": str,
            "theme": str,
            "max_scan_workers": (int, float),
            "perf_logging": (bool, int),
            "scan_delay_ms": (int, float),
        }
        if key not in ALLOWED_TYPES:
            return
        if not isinstance(value, ALLOWED_TYPES[key]):
            log.warning("set_app_config: invalid type for %s: %s", key, type(value).__name__)
            return
        if key == "scan_delay_ms":
            self._db.upsert_sync_config(scan_delay_ms=int(value))
        else:
            self._db.upsert_app_config(**{key: value})

    def select_folders(self) -> list[str]:
        """Open a native folder selection dialog."""
        raise NotImplementedError("select_folders: to be implemented with tauri-plugin-dialog in Step 5")
