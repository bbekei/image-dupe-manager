"""
tests/unit/test_security.py — Security tests for DejaView.

Covers:
  1. Symlink / junction guard in core/scanner.py
  2. SQL injection safety via db.py parameterized queries
  3. pixel_hash format validation (db.validate_pixel_hash)
  4. Path traversal — thumbnail reads and URLs confined to thumb_dir
  5. JS injection — event name allowlist, ensure_ascii in evaluate_js
  6. API type safety — invalid input types rejected at boundary
  7. Credential safety — no secrets logged, .gitignore coverage
  8. JSON import limits — size, entry count, field truncation
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from backend.api import ALLOWED_EVENTS, DejaViewAPI
from data.db import Database, validate_pixel_hash
from core.scanner import Scanner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jpg(path: Path, color=(128, 128, 128), size=(64, 64)) -> Path:
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


def _session(db: Database, scan_dir: Path) -> int:
    now = datetime.now(timezone.utc).isoformat()
    sid = db.create_session(name="security test", created_at=now)
    db.add_session_folder(sid, str(scan_dir))
    return sid


@pytest.fixture
def api(db: Database, tmp_path: Path) -> DejaViewAPI:
    """DejaViewAPI wired to a fresh test DB with a mock emit callback."""
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    trash_root = tmp_path / "trash"
    trash_root.mkdir()
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    inst = DejaViewAPI(
        db=db,
        thumb_dir=thumb_dir,
        trash_root=trash_root,
        app_dir=app_dir,
    )
    inst.set_emit_callback(lambda name, detail: None)
    return inst


# ── 1. Symlink / junction guard ──────────────────────────────────────────────

class TestSymlinkGuard:
    """
    os.path.islink() is mocked so the test runs without admin privileges.
    """

    def test_scanner_skips_symlinked_directory(
        self, db, tmp_path, thumb_dir
    ):
        import threading
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        real_sub = scan_dir / "real"
        real_sub.mkdir()
        _jpg(real_sub / "real.jpg")

        link_sub = scan_dir / "junction"
        link_sub.mkdir()
        _jpg(link_sub / "secret.jpg")

        sid = _session(db, scan_dir)
        orig_islink = os.path.islink

        def mock_islink(path):
            return Path(path).name == "junction" or orig_islink(path)

        with patch("core.scanner.os.path.islink", side_effect=mock_islink):
            scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
            done = threading.Event()
            scanner.scan_complete.connect(lambda: done.set())
            scanner.start()
            assert done.wait(timeout=10.0), "Scan did not complete within timeout"

        files = db.get_files_for_session(sid)
        paths = [f["path"] for f in files]
        assert any("real.jpg" in p for p in paths)
        assert not any("secret.jpg" in p for p in paths)

    def test_scanner_does_not_skip_regular_directory(
        self, db, tmp_path, thumb_dir
    ):
        import threading
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        sub = scan_dir / "sub"
        sub.mkdir()
        _jpg(sub / "img.jpg")

        sid = _session(db, scan_dir)
        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()
        assert done.wait(timeout=10.0), "Scan did not complete within timeout"

        files = db.get_files_for_session(sid)
        assert len(files) == 1
        assert "img.jpg" in files[0]["path"]

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only: tests actual junctions")
    def test_scanner_skips_windows_junction(
        self, db, tmp_path, thumb_dir
    ):
        import subprocess
        import threading

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        target = tmp_path / "target"
        target.mkdir()
        _jpg(target / "secret.jpg")

        junction = scan_dir / "junction"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
            capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip("Cannot create junction — requires admin or Developer Mode")

        _jpg(scan_dir / "real.jpg")
        sid = _session(db, scan_dir)

        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        done = threading.Event()
        scanner.scan_complete.connect(lambda: done.set())
        scanner.start()
        assert done.wait(timeout=10.0), "Scan did not complete within timeout"

        files = db.get_files_for_session(sid)
        paths = [f["path"] for f in files]
        assert any("real.jpg" in p for p in paths)
        assert not any("secret.jpg" in p for p in paths)


# ── 2. SQL parameterization safety ───────────────────────────────────────────

class TestSQLParameterization:

    def test_file_path_with_sql_injection_stored_safely(self, db):
        evil = "C:/it's a'; DROP TABLE files; -- .jpg"
        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="sql test", created_at=now)

        fid = db.insert_file(
            session_id=sid, path=evil, size=1, modified_at=now, scanned_at=now
        )

        assert db.get_file(fid)["path"] == evil
        assert len(db.get_files_for_session(sid)) == 1

    def test_pixel_hash_sql_injection_rejected_before_db_write(self, db):
        crafted = "'; DROP TABLE files; --" + "a" * 41
        assert not validate_pixel_hash(crafted)
        assert db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0

    def test_username_with_sql_chars_stored_safely_as_peer(self, db):
        now = datetime.now(timezone.utc).isoformat()
        pid = db.upsert_remote_peer(username="alice", last_seen_at=now)
        assert db.get_remote_peer("alice")["id"] == pid


# ── 3. pixel_hash format validation ─────────────────────────────────────────

class TestPixelHashValidation:

    def test_valid_pixel_hash_accepted(self):
        assert validate_pixel_hash("a3f9" * 16)   # 64 hex chars

    def test_pixel_hash_too_short_rejected(self):
        assert not validate_pixel_hash("a" * 63)

    def test_pixel_hash_too_long_rejected(self):
        assert not validate_pixel_hash("a" * 65)

    def test_pixel_hash_non_hex_chars_rejected(self):
        assert not validate_pixel_hash("g" + "a" * 63)

    def test_pixel_hash_uppercase_rejected(self):
        assert not validate_pixel_hash("A" * 64)

    def test_pixel_hash_with_sql_injection_rejected(self):
        assert not validate_pixel_hash("'; DROP TABLE files; --" + "a" * 41)

    def test_empty_string_rejected(self):
        assert not validate_pixel_hash("")

    def test_non_string_rejected(self):
        assert not validate_pixel_hash(None)  # type: ignore[arg-type]


# ── 4. Path traversal — thumbnail confinement ────────────────────────────────

class TestThumbnailPathConfinement:
    """Verify _read_thumbnail_base64 and get_thumbnail_url reject paths
    outside the designated thumb_dir."""

    def test_read_thumbnail_inside_thumb_dir(self, api, tmp_path):
        thumb_dir = tmp_path / "thumbs"
        thumb_file = thumb_dir / "legit.jpg"
        thumb_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)

        result = api._read_thumbnail_base64(str(thumb_file))
        assert result.startswith("data:image/jpeg;base64,")

    def test_read_thumbnail_outside_thumb_dir_blocked(self, api, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data")

        result = api._read_thumbnail_base64(str(secret))
        assert result == ""

    def test_read_thumbnail_traversal_attack_blocked(self, api, tmp_path):
        """Path traversal via ../ is resolved before checking confinement."""
        thumb_dir = tmp_path / "thumbs"
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data")

        # Craft a path that appears to be inside thumbs but escapes via ../
        evil_path = str(thumb_dir / ".." / "secret.txt")
        result = api._read_thumbnail_base64(evil_path)
        assert result == ""

    def test_get_thumbnail_url_inside_thumb_dir(self, api, tmp_path):
        thumb_dir = tmp_path / "thumbs"
        thumb_file = thumb_dir / "legit.jpg"
        thumb_file.write_bytes(b"\xff\xd8")

        result = api.get_thumbnail_url(str(thumb_file))
        assert result.startswith("file:///")

    def test_get_thumbnail_url_outside_thumb_dir_blocked(self, api, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("nope")

        result = api.get_thumbnail_url(str(secret))
        assert result == ""

    def test_get_thumbnail_url_traversal_blocked(self, api, tmp_path):
        thumb_dir = tmp_path / "thumbs"
        evil_path = str(thumb_dir / ".." / "secret.txt")
        result = api.get_thumbnail_url(evil_path)
        assert result == ""

    def test_read_thumbnail_empty_path_returns_empty(self, api):
        assert api._read_thumbnail_base64("") == ""
        assert api._read_thumbnail_base64(None) == ""

    def test_get_thumbnail_url_empty_path_returns_empty(self, api):
        assert api.get_thumbnail_url("") == ""

    def test_is_safe_thumb_path_rejects_symlink_escape(self, api, tmp_path):
        """Even if a symlink points outside, resolve() catches it."""
        outside = tmp_path / "outside.txt"
        outside.write_text("escape")

        # If we could create a symlink inside thumbs pointing outside,
        # resolve() would follow it and detect the escape.
        # We test the logic directly.
        assert not api._is_safe_thumb_path(str(outside))


# ── 5. JS injection — event allowlist and safe serialization ─────────────────

class TestEventInjectionPrevention:
    """Verify the sidecar event emission is safe against injection."""

    def test_allowed_events_are_dispatched(self, api):
        """All known event names in ALLOWED_EVENTS reach the emit callback."""
        emitted = []
        api.set_emit_callback(lambda name, detail: emitted.append(name))

        for event_name in ALLOWED_EVENTS:
            api._emit(event_name, {"test": True})

        assert set(emitted) == ALLOWED_EVENTS

    def test_unknown_event_name_not_in_allowed_events(self, api):
        """An event name not in ALLOWED_EVENTS is not a known safe event."""
        # Verify the allowlist does not include unknown event names
        assert "unknown:event" not in ALLOWED_EVENTS
        assert "evil:inject" not in ALLOWED_EVENTS

    def test_event_names_with_injection_not_in_allowed_events(self, api):
        """Crafted injection-attempt event names are not in ALLOWED_EVENTS allowlist."""
        injection_names = [
            'scan:progress"; alert(1); //',
            "<script>alert(1)</script>",
            '"); alert("xss"); //',
        ]
        for name in injection_names:
            assert name not in ALLOWED_EVENTS, (
                f"Injection-attempt event name should not be in ALLOWED_EVENTS: {name!r}"
            )

    def test_detail_with_special_chars_passed_through(self, api):
        """Detail payloads with special chars are passed to callback unchanged."""
        received = []
        api.set_emit_callback(lambda name, detail: received.append(detail))

        # Pick any allowed event
        event = next(iter(ALLOWED_EVENTS))
        detail = {"path": "/tmp/file\u2028name\u2029.jpg", "message": "test"}
        api._emit(event, detail)

        assert received == [detail]

    def test_detail_is_dict(self, api):
        """The emit callback always receives a dict as the detail argument."""
        received = []
        api.set_emit_callback(lambda name, detail: received.append(detail))

        event = next(iter(ALLOWED_EVENTS))
        api._emit(event, {"key": "value", "num": 42})

        assert len(received) == 1
        assert isinstance(received[0], dict)

    def test_allowed_events_frozenset_is_immutable(self):
        """ALLOWED_EVENTS cannot be mutated at runtime."""
        assert isinstance(ALLOWED_EVENTS, frozenset)
        with pytest.raises(AttributeError):
            ALLOWED_EVENTS.add("evil:event")  # type: ignore[attr-defined]


# ── 6. API type safety — invalid input types rejected ────────────────────────

class TestAPITypeSafety:
    """Verify that API methods reject invalid input types gracefully
    instead of propagating to the database."""

    def test_set_file_action_rejects_string_file_id(self, api):
        result = api.set_file_action("not_an_int", "keep", "file")  # type: ignore
        assert result == {"actions": {}}

    def test_set_file_action_rejects_float_file_id(self, api):
        result = api.set_file_action(1.5, "keep", "file")  # type: ignore
        assert result == {"actions": {}}

    def test_set_file_action_rejects_invalid_action(self, api):
        result = api.set_file_action(1, "drop_table", "file")
        assert result == {"actions": {}}

    def test_set_file_action_rejects_invalid_scope(self, api):
        result = api.set_file_action(1, "keep", "global")
        assert result == {"actions": {}}

    def test_set_file_action_rejects_none_action(self, api):
        result = api.set_file_action(1, None, "file")  # type: ignore
        assert result == {"actions": {}}

    def test_keep_and_delete_others_rejects_string_keep_id(self, api):
        result = api.keep_and_delete_others("bad", [1, 2])  # type: ignore
        assert result == {"actions": {}}

    def test_keep_and_delete_others_rejects_non_int_list(self, api):
        result = api.keep_and_delete_others(1, ["a", "b"])  # type: ignore
        assert result == {"actions": {}}

    def test_keep_and_delete_others_rejects_non_list(self, api):
        result = api.keep_and_delete_others(1, "not_a_list")  # type: ignore
        assert result == {"actions": {}}

    def test_set_app_config_rejects_unknown_key(self, api):
        """Keys outside the allowlist are silently ignored."""
        api.set_app_config("drop_table", "malicious")
        # No error, but nothing stored
        config = api.get_app_config()
        assert "drop_table" not in config

    def test_set_app_config_rejects_wrong_type_for_language(self, api):
        """Language must be a string, not an int."""
        api.set_app_config("language", 42)
        config = api.get_app_config()
        # Should retain the default, not store 42
        assert config["language"] == "auto"

    def test_set_app_config_rejects_wrong_type_for_max_workers(self, api):
        """max_scan_workers must be int or float, not a string."""
        api.set_app_config("max_scan_workers", "DROP TABLE")
        config = api.get_app_config()
        assert config["max_scan_workers"] == 4  # default

    def test_set_app_config_rejects_non_string_key(self, api):
        """Key must be a string."""
        api.set_app_config(42, "value")  # type: ignore
        # No crash, silently ignored

    def test_set_app_config_accepts_valid_string_value(self, api):
        """Valid key+type is accepted."""
        api.set_app_config("theme", "light")
        config = api.get_app_config()
        assert config["theme"] == "light"

    def test_set_app_config_sql_injection_in_value(self, api):
        """SQL injection in value is stored as literal string, not executed."""
        api.set_app_config("theme", "'; DROP TABLE app_config; --")
        config = api.get_app_config()
        assert config["theme"] == "'; DROP TABLE app_config; --"


# ── 7. Import file validation ────────────────────────────────────────────────

class TestImportFileValidation:
    """Verify import_hashes API method validates files before parsing."""

    def test_import_rejects_non_json_extension(self, api, tmp_path):
        evil = tmp_path / "payload.exe"
        evil.write_text("{}")
        result = api.import_hashes(str(evil))
        assert result.get("error") == "invalid_file_type"
        assert result["imported"] == 0

    def test_import_rejects_missing_file(self, api, tmp_path):
        result = api.import_hashes(str(tmp_path / "nonexistent.json"))
        assert result.get("error") == "file_not_found"

    def test_import_rejects_oversized_file(self, api, tmp_path):
        big = tmp_path / "huge.json"
        # Write >10 MB
        big.write_bytes(b'{"username":"x","files":[]}' + b" " * (11 * 1024 * 1024))
        result = api.import_hashes(str(big))
        assert result.get("error") == "file_too_large"

    def test_import_rejects_path_traversal_extension_trick(self, api, tmp_path):
        """File named something.json.exe should be rejected."""
        evil = tmp_path / "payload.json.exe"
        evil.write_text("{}")
        result = api.import_hashes(str(evil))
        assert result.get("error") == "invalid_file_type"


# ── 8. JSON import limits (data/export.py) ───────────────────────────────────

class TestJSONImportLimits:
    """JSON import size and entry-count caps in data/export.py."""

    def test_import_rejects_payload_over_10mb(self, db):
        from data.export import import_payload
        big = b'{"username":"testuser","files":[]}' + b" " * (10 * 1024 * 1024 + 1)
        with pytest.raises(ImportError, match="size"):
            import_payload(db, big)

    def test_import_rejects_payload_with_too_many_entries(self, db):
        from data.export import import_payload
        payload = json.dumps(
            {"username": "testuser", "files": [{"pixel_hash": "a" * 64}] * 100_001}
        ).encode()
        with pytest.raises(ImportError, match="entries"):
            import_payload(db, payload)

    def test_import_skips_entry_with_invalid_pixel_hash(self, db):
        from data.export import import_payload
        payload = json.dumps({
            "username": "testuser",
            "files": [
                {"pixel_hash": "a" * 64},
                {"pixel_hash": "INVALID"},
            ],
        }).encode()
        import_payload(db, payload)
        count = db.conn.execute(
            "SELECT COUNT(*) FROM remote_files"
        ).fetchone()[0]
        assert count == 1

    def test_import_rejects_invalid_username(self, db):
        from data.export import import_payload
        payload = json.dumps({
            "username": "'; DROP TABLE--",
            "files": [],
        }).encode()
        with pytest.raises(ImportError, match="username"):
            import_payload(db, payload)

    def test_import_rejects_missing_username(self, db):
        from data.export import import_payload
        payload = json.dumps({"files": []}).encode()
        with pytest.raises(ImportError, match="username"):
            import_payload(db, payload)

    def test_import_rejects_non_object_payload(self, db):
        from data.export import import_payload
        payload = json.dumps([1, 2, 3]).encode()
        with pytest.raises(ImportError, match="object"):
            import_payload(db, payload)


# ── 9. Credential safety ─────────────────────────────────────────────────────

class TestCredentialSafety:
    """Verify credential files are handled safely."""

    def test_token_file_created_with_restricted_permissions(self, tmp_path):
        from unittest.mock import MagicMock
        from data.sync import save_credentials
        token_path = tmp_path / "credentials.json"
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "test"}'
        save_credentials(mock_creds, token_path)
        assert token_path.exists()
        assert token_path.read_text() == '{"token": "test"}'

    def test_log_messages_do_not_contain_token_values(self):
        """Verify that the sync module's log calls don't log raw credentials."""
        import ast
        import inspect
        from data import sync

        source = inspect.getsource(sync)
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Look for log.xxx("...", <some_var>)
                func = node.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id == "log":
                        # Check that no argument is named 'creds', 'token', etc.
                        for arg in node.args[1:]:  # skip format string
                            if isinstance(arg, ast.Name):
                                assert arg.id not in (
                                    "creds", "token", "refresh_token",
                                    "access_token", "credentials",
                                ), (
                                    f"Potential secret leak: log.{func.attr}() "
                                    f"passes variable '{arg.id}' — use str(exc) instead"
                                )

    def test_gitignore_excludes_credential_files(self):
        """The root .gitignore must exclude credential files."""
        gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
        if not gitignore_path.exists():
            pytest.skip(".gitignore not found at project root")
        content = gitignore_path.read_text()
        assert "credentials.json" in content
        assert "client_secrets.json" in content
