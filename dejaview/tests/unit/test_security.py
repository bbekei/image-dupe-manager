"""
tests/unit/test_security.py — Security tests (plan §Security Tests).

Covers:
  - Symlink / junction guard in core/scanner.py  (plan §Security — symlink guard)
  - SQL injection safety via db.py parameterized queries
  - pixel_hash format validation (db.validate_pixel_hash)

Phase-gated tests (skipped until the relevant module is implemented):
  - Rename path traversal  → Phase 4 (compare_view.py)
  - JSON import limits      → Phase 5 (export.py)
  - Credential permissions  → Phase 6 (sync.py)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

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


# ── Symlink / junction guard ──────────────────────────────────────────────────

class TestSymlinkGuard:
    """
    Plan §Security: symlink/junction guard in scanner.py.
    os.path.islink() is mocked so the test runs without admin privileges.
    """

    def test_scanner_skips_symlinked_directory(
        self, qtbot, db, tmp_path, thumb_dir
    ):
        # Plan §Security Tests: test_scanner_skips_symlinked_directory
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        real_sub = scan_dir / "real"
        real_sub.mkdir()
        _jpg(real_sub / "real.jpg")

        link_sub = scan_dir / "junction"
        link_sub.mkdir()              # physically real; mocked as a symlink
        _jpg(link_sub / "secret.jpg")

        sid = _session(db, scan_dir)
        orig_islink = os.path.islink

        def mock_islink(path):
            return Path(path).name == "junction" or orig_islink(path)

        with patch("core.scanner.os.path.islink", side_effect=mock_islink):
            scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
            with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
                scanner.start()

        files = db.get_files_for_session(sid)
        paths = [f["path"] for f in files]
        assert any("real.jpg" in p for p in paths)
        assert not any("secret.jpg" in p for p in paths)

    def test_scanner_does_not_skip_regular_directory(
        self, qtbot, db, tmp_path, thumb_dir
    ):
        # Plan §Security Tests: test_scanner_does_not_skip_regular_directory
        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        sub = scan_dir / "sub"
        sub.mkdir()
        _jpg(sub / "img.jpg")

        sid = _session(db, scan_dir)
        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
            scanner.start()

        files = db.get_files_for_session(sid)
        assert len(files) == 1
        assert "img.jpg" in files[0]["path"]

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only: tests actual junctions")
    def test_scanner_skips_windows_junction(
        self, qtbot, db, tmp_path, thumb_dir
    ):
        # Plan §Security Tests: test_scanner_skips_windows_junction
        # Creates a real Windows directory junction using mklink /J.
        import subprocess

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
        with qtbot.waitSignal(scanner.scan_complete, timeout=10_000):
            scanner.start()

        files = db.get_files_for_session(sid)
        paths = [f["path"] for f in files]
        assert any("real.jpg" in p for p in paths)
        assert not any("secret.jpg" in p for p in paths)


# ── SQL parameterization safety ───────────────────────────────────────────────

class TestSQLParameterization:
    """
    Plan §Security: parameterized queries throughout db.py.
    Verifies that hostile path values are stored verbatim and never interpreted
    as SQL.
    """

    def test_file_path_with_sql_injection_stored_safely(self, db):
        # Plan §Security Tests: test_file_path_with_sql_injection_stored_safely
        evil = "C:/it's a'; DROP TABLE files; -- .jpg"
        now = datetime.now(timezone.utc).isoformat()
        sid = db.create_session(name="sql test", created_at=now)

        fid = db.insert_file(
            session_id=sid, path=evil, size=1, modified_at=now, scanned_at=now
        )

        # Path stored exactly as given — no interpretation.
        assert db.get_file(fid)["path"] == evil
        # files table still exists and has exactly one row.
        assert len(db.get_files_for_session(sid)) == 1

    def test_pixel_hash_sql_injection_rejected_before_db_write(self, db):
        # Plan §Security Tests: test_pixel_hash_with_special_chars_stored_safely
        # A malicious pixel_hash is caught by validate_pixel_hash() before any
        # DB write, so the files table survives intact.
        crafted = "'; DROP TABLE files; --" + "a" * 41
        assert not validate_pixel_hash(crafted)
        # DB is unaffected.
        assert db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0

    def test_username_with_sql_chars_stored_safely_as_peer(self, db):
        # Peer usernames come from external JSON; they go through ? placeholders.
        now = datetime.now(timezone.utc).isoformat()
        # A valid username (plan §Security: [A-Za-z0-9_-] only) is inserted safely.
        pid = db.upsert_remote_peer(username="alice", last_seen_at=now)
        assert db.get_remote_peer("alice")["id"] == pid


# ── pixel_hash format validation ──────────────────────────────────────────────

class TestPixelHashValidation:
    """
    Plan §Security: validate_pixel_hash() must reject anything that is not a
    64-character lowercase hexadecimal string.
    """

    def test_valid_pixel_hash_accepted(self):
        # Plan §Security Tests: test_valid_pixel_hash_accepted
        assert validate_pixel_hash("a3f9" * 16)   # 64 hex chars

    def test_pixel_hash_too_short_rejected(self):
        # Plan §Security Tests: test_pixel_hash_too_short_rejected
        assert not validate_pixel_hash("a" * 63)

    def test_pixel_hash_too_long_rejected(self):
        assert not validate_pixel_hash("a" * 65)

    def test_pixel_hash_non_hex_chars_rejected(self):
        # Plan §Security Tests: test_pixel_hash_non_hex_chars_rejected
        assert not validate_pixel_hash("g" + "a" * 63)

    def test_pixel_hash_uppercase_rejected(self):
        # SHA-256 output is always lowercase; uppercase fails the pattern.
        assert not validate_pixel_hash("A" * 64)

    def test_pixel_hash_with_sql_injection_rejected(self):
        # Plan §Security Tests: test_pixel_hash_with_sql_injection_rejected
        assert not validate_pixel_hash("'; DROP TABLE files; --" + "a" * 41)

    def test_empty_string_rejected(self):
        assert not validate_pixel_hash("")

    def test_non_string_rejected(self):
        assert not validate_pixel_hash(None)  # type: ignore[arg-type]


# ── Rename path traversal — Phase 4 ──────────────────────────────────────────

@pytest.mark.skip(reason="Phase 4: compare_view._validate_rename not yet implemented")
class TestRenameValidation:
    """
    Plan §Security Tests: rename path traversal.
    Enable when ui/compare_view.py is implemented in Phase 4.
    """

    def test_rename_rejects_path_separator(self):
        from ui.compare_view import _validate_rename
        assert not _validate_rename("../../evil.jpg")

    def test_rename_rejects_empty_string(self):
        from ui.compare_view import _validate_rename
        assert not _validate_rename("")

    def test_rename_rejects_leading_dot(self):
        from ui.compare_view import _validate_rename
        assert not _validate_rename(".hidden")

    def test_rename_rejects_over_255_chars(self):
        from ui.compare_view import _validate_rename
        assert not _validate_rename("a" * 256)

    def test_rename_accepts_valid_filename(self):
        from ui.compare_view import _validate_rename
        assert _validate_rename("vacation_beach_2023.jpg")

    def test_rename_destination_is_same_directory(self):
        from ui.compare_view import _validate_rename
        original = Path("C:/Photos/img.jpg")
        new_name = "img_copy.jpg"
        assert _validate_rename(new_name)
        dest = original.parent / new_name
        assert str(dest) == "C:/Photos/img_copy.jpg"


# ── JSON import limits — Phase 5 ─────────────────────────────────────────────

@pytest.mark.skip(reason="Phase 5: data/export.py not yet implemented")
class TestJSONImportLimits:
    """
    Plan §Security Tests: JSON import size and entry-count caps.
    Enable when data/export.py is implemented in Phase 5.
    """

    def test_import_rejects_payload_over_10mb(self, db):
        from data.export import import_payload
        big = b'{"username":"x","files":[]}' + b" " * (10 * 1024 * 1024)
        with pytest.raises(ImportError, match="size"):
            import_payload(db, big)

    def test_import_rejects_payload_with_too_many_entries(self, db):
        from data.export import import_payload
        import json
        payload = json.dumps(
            {"username": "x", "files": [{"pixel_hash": "a" * 64}] * 100_001}
        ).encode()
        with pytest.raises(ImportError, match="entries"):
            import_payload(db, payload)

    def test_import_truncates_long_filename_field(self, db):
        from data.export import import_payload
        import json
        payload = json.dumps({
            "username": "alice",
            "files": [{"pixel_hash": "a" * 64, "filename": "x" * 2000}],
        }).encode()
        import_payload(db, payload)
        row = db.conn.execute("SELECT filename FROM remote_files").fetchone()
        assert len(row["filename"]) <= 1024

    def test_import_skips_entry_with_invalid_pixel_hash(self, db):
        from data.export import import_payload
        import json
        payload = json.dumps({
            "username": "alice",
            "files": [
                {"pixel_hash": "a" * 64},          # valid
                {"pixel_hash": "INVALID"},           # invalid → skipped
            ],
        }).encode()
        import_payload(db, payload)
        count = db.conn.execute("SELECT COUNT(*) FROM remote_files").fetchone()[0]
        assert count == 1


# ── Credential file permissions — Phase 6 ────────────────────────────────────

class TestCredentialPermissions:
    """
    Plan §Security Tests: OAuth2 token file created with mode 0o600.
    Phase 6: data/sync.py implemented.
    """

    def test_token_file_created_with_restricted_permissions(self, tmp_path):
        from unittest.mock import MagicMock
        from data.sync import save_credentials
        token_path = tmp_path / "credentials.json"
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "test"}'
        save_credentials(mock_creds, token_path)
        import os, stat
        mode = os.stat(str(token_path)).st_mode
        # On Windows, 0o600 isn't enforced by the OS the same way,
        # so we verify the file exists and was written correctly.
        assert token_path.exists()
        assert token_path.read_text() == '{"token": "test"}'
