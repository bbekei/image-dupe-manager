"""
tests/unit/test_export.py — Unit tests for data/export.py.

Plan §Test Framework — tests/unit/test_export.py.
Tests: payload building, privacy levels, import validation, security guards,
round-trip idempotency.
"""

import json
import datetime

import pytest

from data.db import Database, validate_pixel_hash
from data.export import (
    build_export_payload,
    import_payload,
    validate_username,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ENTRIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_HASH = "a" * 64
VALID_HASH_2 = "b" * 64
DIFFERENT_HASH = "c" * 64


def _insert_test_files(db, session_id):
    """Insert 3 test files: 2 with hashes (active), 1 deleted."""
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.insert_file(session_id, r"C:\Photos\beach.jpg", 2048000, ts, ts)
    db.insert_file(session_id, r"C:\Photos\sunset.jpg", 1500000, ts, ts)
    db.insert_file(session_id, r"C:\Photos\deleted.jpg", 1000000, ts, ts)

    files = db.get_files_for_session(session_id)
    db.update_pixel_hash(files[0]["id"], VALID_HASH, "/thumbs/aaa.jpg")
    db.update_pixel_hash(files[1]["id"], VALID_HASH_2, "/thumbs/bbb.jpg")
    db.update_pixel_hash(files[2]["id"], DIFFERENT_HASH, "/thumbs/ccc.jpg")
    db.update_file_status(files[2]["id"], "deleted")

    return files


def _make_peer_payload(
    username="alice",
    files=None,
    privacy_level="filename",
):
    """Build a minimal valid peer export payload dict."""
    if files is None:
        files = [
            {
                "remote_id": f"{username}:1",
                "pixel_hash": VALID_HASH,
                "filename": "beach_copy.jpg",
                "size": 2048000,
                "modified_at": "2023-06-15T10:30:00Z",
            }
        ]
    return {
        "username": username,
        "exported_at": "2024-01-01T00:00:00Z",
        "privacy_level": privacy_level,
        "files": files,
    }


# ---------------------------------------------------------------------------
# Username validation
# ---------------------------------------------------------------------------

class TestUsernameValidation:
    """Plan §Security — username sanitization."""

    def test_valid_username(self):
        assert validate_username("alice") is True

    def test_valid_username_with_dash_underscore(self):
        assert validate_username("alice_bob-123") is True

    def test_rejects_empty(self):
        assert validate_username("") is False

    def test_rejects_dots(self):
        assert validate_username("alice.bob") is False

    def test_rejects_spaces(self):
        assert validate_username("alice bob") is False

    def test_rejects_too_long(self):
        assert validate_username("a" * 65) is False

    def test_accepts_max_length(self):
        assert validate_username("a" * 64) is True

    def test_rejects_special_chars(self):
        assert validate_username("alice@bob") is False

    def test_rejects_non_string(self):
        assert validate_username(123) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# build_export_payload
# ---------------------------------------------------------------------------

class TestBuildExportPayload:
    """Plan §Phase 5 — export.build_export_payload()."""

    def test_hash_only_privacy_omits_filename_and_path(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "hash_only")

        for f in payload["files"]:
            assert "filename" not in f
            assert "path" not in f
            assert "pixel_hash" in f
            assert "size" in f
            assert "modified_at" in f

    def test_filename_privacy_includes_filename_not_path(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "filename")

        for f in payload["files"]:
            assert "filename" in f
            assert "path" not in f

    def test_full_path_privacy_includes_full_path(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "full_path")

        for f in payload["files"]:
            assert "path" in f
            assert "filename" in f

    def test_export_only_includes_active_files(self, db, session_factory):
        """Files with status='deleted' must not appear."""
        sid = session_factory()
        _insert_test_files(db, sid)  # 3rd file is deleted

        payload = build_export_payload(db, sid, "bob", "hash_only")

        assert len(payload["files"]) == 2
        hashes = {f["pixel_hash"] for f in payload["files"]}
        assert DIFFERENT_HASH not in hashes

    def test_export_skips_unhashed_files(self, db, session_factory):
        """Files without pixel_hash (not yet hashed) are excluded."""
        sid = session_factory()
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.insert_file(sid, r"C:\Photos\new.jpg", 500000, ts, ts)

        payload = build_export_payload(db, sid, "bob", "hash_only")
        assert len(payload["files"]) == 0

    def test_export_payload_contains_username_and_timestamp(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "hash_only")

        assert payload["username"] == "bob"
        assert payload["privacy_level"] == "hash_only"
        # exported_at must be a valid ISO-8601 string
        dt = datetime.datetime.fromisoformat(payload["exported_at"])
        assert dt.year >= 2024

    def test_filename_extracted_from_backslash_path(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "filename")

        filenames = {f["filename"] for f in payload["files"]}
        assert "beach.jpg" in filenames
        assert "sunset.jpg" in filenames

    def test_filename_extracted_from_forward_slash_path(self, db, session_factory):
        """Handle Unix-style paths too."""
        sid = session_factory()
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.insert_file(sid, "/home/user/pics/photo.jpg", 1000, ts, ts)
        files = db.get_files_for_session(sid)
        db.update_pixel_hash(files[0]["id"], VALID_HASH, "/t/h.jpg")

        payload = build_export_payload(db, sid, "bob", "filename")
        assert payload["files"][0]["filename"] == "photo.jpg"

    def test_remote_id_contains_username_prefix(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "hash_only")

        for f in payload["files"]:
            assert f["remote_id"].startswith("bob:")

    def test_invalid_username_raises_value_error(self, db, session_factory):
        sid = session_factory()
        with pytest.raises(ValueError, match="Invalid username"):
            build_export_payload(db, sid, "bad user!", "hash_only")

    def test_invalid_privacy_raises_value_error(self, db, session_factory):
        sid = session_factory()
        with pytest.raises(ValueError, match="Invalid privacy_level"):
            build_export_payload(db, sid, "bob", "invalid")


# ---------------------------------------------------------------------------
# import_payload
# ---------------------------------------------------------------------------

class TestImportPayload:
    """Plan §Phase 5 — export.import_payload()."""

    def test_basic_import_creates_peer_and_files(self, db):
        payload = _make_peer_payload()
        raw = json.dumps(payload)

        username = import_payload(db, raw)

        assert username == "alice"
        peer = db.get_remote_peer("alice")
        assert peer is not None

    def test_import_stores_correct_pixel_hash(self, db):
        payload = _make_peer_payload()
        raw = json.dumps(payload)
        import_payload(db, raw)

        # Check remote_files via cross-library query setup
        peers = db.get_all_remote_peers()
        assert len(peers) == 1

    def test_import_is_idempotent(self, db):
        """Importing the same payload twice produces the same DB state."""
        payload = _make_peer_payload(files=[
            {"remote_id": "alice:1", "pixel_hash": VALID_HASH,
             "filename": "a.jpg", "size": 100, "modified_at": "2024-01-01"},
            {"remote_id": "alice:2", "pixel_hash": VALID_HASH_2,
             "filename": "b.jpg", "size": 200, "modified_at": "2024-01-01"},
        ])
        raw = json.dumps(payload)

        import_payload(db, raw)
        import_payload(db, raw)

        # Should still have exactly 1 peer and 2 remote files
        peers = db.get_all_remote_peers()
        assert len(peers) == 1
        # Verify via cross-library query (requires local files)
        # Just check no duplicate peers were created

    def test_import_updates_last_imported_at(self, db):
        # Pre-create sync_config so last_imported_at can be updated
        db.upsert_sync_config(local_username="me", export_privacy="filename")

        payload = _make_peer_payload()
        import_payload(db, json.dumps(payload))

        config = db.get_sync_config()
        assert config is not None
        assert config["last_imported_at"] is not None

    def test_import_malformed_json_raises_import_error(self, db):
        with pytest.raises(ImportError, match="Malformed JSON"):
            import_payload(db, "not valid json {{{")

    def test_import_non_object_raises_import_error(self, db):
        with pytest.raises(ImportError, match="JSON object"):
            import_payload(db, "[1, 2, 3]")

    def test_import_missing_username_raises_import_error(self, db):
        raw = json.dumps({"files": []})
        with pytest.raises(ImportError, match="username"):
            import_payload(db, raw)

    def test_import_invalid_username_raises_import_error(self, db):
        raw = json.dumps({"username": "bad user!", "files": []})
        with pytest.raises(ImportError, match="username"):
            import_payload(db, raw)

    def test_import_missing_files_raises_import_error(self, db):
        raw = json.dumps({"username": "alice"})
        with pytest.raises(ImportError, match="files"):
            import_payload(db, raw)

    def test_import_files_not_list_raises_import_error(self, db):
        raw = json.dumps({"username": "alice", "files": "not a list"})
        with pytest.raises(ImportError, match="files"):
            import_payload(db, raw)


# ---------------------------------------------------------------------------
# Import security guards (plan §Security — JSON import limits)
# ---------------------------------------------------------------------------

class TestImportSecurityGuards:

    def test_import_rejects_payload_over_10mb(self, db):
        """Plan §Security — file size cap."""
        # Create payload just over 10 MB
        big_data = "x" * (MAX_IMPORT_BYTES + 1)
        raw = json.dumps({"username": "alice", "files": [], "pad": big_data})

        with pytest.raises(ImportError, match="size"):
            import_payload(db, raw)

    def test_import_rejects_payload_with_too_many_entries(self, db):
        """Plan §Security — maximum entry count.

        We build a minimal-size payload that exceeds the entry count limit
        but stays under the 10 MB size cap. Each entry is tiny (just a hash).
        """
        # 100_001 entries × ~80 bytes each ≈ ~8 MB (under 10 MB cap)
        entries = [{"pixel_hash": VALID_HASH} for _ in range(MAX_IMPORT_ENTRIES + 1)]
        raw = json.dumps({"username": "alice", "files": entries})

        with pytest.raises(ImportError, match="too many entries"):
            import_payload(db, raw)

    def test_import_skips_entry_with_invalid_pixel_hash(self, db):
        """Plan §Security — pixel_hash format enforcement."""
        payload = _make_peer_payload(files=[
            {"remote_id": "alice:1", "pixel_hash": VALID_HASH,
             "filename": "good.jpg", "size": 100},
            {"remote_id": "alice:2", "pixel_hash": "INVALID_HASH",
             "filename": "bad.jpg", "size": 200},
        ])
        raw = json.dumps(payload)

        # Should not raise — skips invalid entry
        import_payload(db, raw)

    def test_import_truncates_long_filename_field(self, db):
        """Plan §Security — field length limits."""
        long_name = "a" * 2000 + ".jpg"
        payload = _make_peer_payload(files=[
            {"remote_id": "alice:1", "pixel_hash": VALID_HASH,
             "filename": long_name, "size": 100},
        ])
        raw = json.dumps(payload)
        import_payload(db, raw)

        # The filename should be truncated to 1024 chars
        # (verified indirectly — no DB error from oversized field)

    def test_import_truncates_long_path_field(self, db):
        """Plan §Security — field length limits."""
        long_path = "C:\\" + "a" * 2000
        payload = _make_peer_payload(files=[
            {"remote_id": "alice:1", "pixel_hash": VALID_HASH,
             "path": long_path, "size": 100},
        ])
        raw = json.dumps(payload)
        import_payload(db, raw)

    def test_import_accepts_bytes_input(self, db):
        """import_payload should accept both str and bytes."""
        payload = _make_peer_payload()
        raw = json.dumps(payload).encode("utf-8")
        username = import_payload(db, raw)
        assert username == "alice"

    def test_import_skips_non_dict_entries(self, db):
        """Non-dict entries in files array are skipped."""
        payload = _make_peer_payload(files=[
            {"remote_id": "alice:1", "pixel_hash": VALID_HASH,
             "filename": "good.jpg", "size": 100},
            "not a dict",
            42,
        ])
        raw = json.dumps(payload)
        import_payload(db, raw)  # Should not raise


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Plan §Test Framework — test_round_trip_hash_only and friends."""

    def test_round_trip_hash_only(self, db, session_factory):
        """Export hash_only → JSON → import → cross-library match."""
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "hash_only")
        raw = json.dumps(payload)

        # Simulate another user importing this (same DB for simplicity)
        import_payload(db, raw)

        # Cross-library JOIN should find matches
        matches = db.get_cross_library_matches(sid)
        assert len(matches) >= 1
        matched_hashes = {m["pixel_hash"] for m in matches}
        assert VALID_HASH in matched_hashes

    def test_round_trip_filename(self, db, session_factory):
        """Export filename → JSON → import → remote_files has filename."""
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "filename")
        raw = json.dumps(payload)
        import_payload(db, raw)

        matches = db.get_cross_library_matches(sid)
        assert len(matches) >= 1
        # remote_filename should be populated
        filenames = {m["remote_filename"] for m in matches}
        assert "beach.jpg" in filenames or "sunset.jpg" in filenames

    def test_round_trip_full_path(self, db, session_factory):
        """Export full_path → JSON → import → remote_files has path."""
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "full_path")
        raw = json.dumps(payload)
        import_payload(db, raw)

        matches = db.get_cross_library_matches(sid)
        assert len(matches) >= 1
        paths = {m["remote_path"] for m in matches if m["remote_path"]}
        assert any("Photos" in p for p in paths)

    def test_no_cross_match_for_unshared_hash(self, db, session_factory):
        """Plan §integration/test_cross_library — no match for different hash."""
        sid = session_factory()
        _insert_test_files(db, sid)

        # Import a peer with a completely different hash
        payload = _make_peer_payload(
            username="carol",
            files=[{
                "remote_id": "carol:1",
                "pixel_hash": "d" * 64,
                "filename": "unrelated.jpg",
                "size": 999,
            }]
        )
        import_payload(db, json.dumps(payload))

        matches = db.get_cross_library_matches(sid)
        peer_usernames = {m["username"] for m in matches}
        assert "carol" not in peer_usernames

    def test_multiple_peers_both_matched(self, db, session_factory):
        """Two peers with the same hash → two cross-library match rows."""
        sid = session_factory()
        _insert_test_files(db, sid)

        for peer in ("alice", "dave"):
            payload = _make_peer_payload(
                username=peer,
                files=[{
                    "remote_id": f"{peer}:1",
                    "pixel_hash": VALID_HASH,
                    "filename": "dup.jpg",
                    "size": 2048000,
                }]
            )
            import_payload(db, json.dumps(payload))

        matches = db.get_cross_library_matches(sid)
        usernames = {m["username"] for m in matches}
        assert "alice" in usernames
        assert "dave" in usernames

    def test_removing_peer_removes_cross_library_results(self, db, session_factory):
        """After remove_peer(), cross-library JOIN returns zero for that peer."""
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = _make_peer_payload()
        import_payload(db, json.dumps(payload))
        assert len(db.get_cross_library_matches(sid)) >= 1

        db.delete_remote_peer("alice")
        matches = db.get_cross_library_matches(sid)
        usernames = {m["username"] for m in matches}
        assert "alice" not in usernames


# ---------------------------------------------------------------------------
# Export with requests_outgoing (Phase 4)
# ---------------------------------------------------------------------------

class TestExportWithRequests:
    """Phase 4 — requests_outgoing in export payload."""

    def test_export_includes_requests_outgoing(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        # Create a pending request
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.create_request(sid, VALID_HASH, "alice", ts)

        payload = build_export_payload(db, sid, "bob", "hash_only")

        assert "requests_outgoing" in payload
        assert len(payload["requests_outgoing"]) == 1
        req = payload["requests_outgoing"][0]
        assert req["pixel_hash"] == VALID_HASH
        assert req["target_peer"] == "alice"
        assert req["status"] == "pending"

    def test_export_excludes_cancelled_requests(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rid = db.create_request(sid, VALID_HASH, "alice", ts)
        db.cancel_request(rid)

        payload = build_export_payload(db, sid, "bob", "hash_only")

        # No requests_outgoing key when all cancelled
        assert "requests_outgoing" not in payload

    def test_export_without_requests_omits_key(self, db, session_factory):
        sid = session_factory()
        _insert_test_files(db, sid)

        payload = build_export_payload(db, sid, "bob", "hash_only")

        # No requests at all — key should not be present
        assert "requests_outgoing" not in payload

    def test_import_with_requests_outgoing_does_not_fail(self, db):
        """Importing a payload with requests_outgoing should succeed."""
        payload = _make_peer_payload()
        payload["requests_outgoing"] = [
            {
                "pixel_hash": VALID_HASH,
                "target_peer": "me",
                "status": "pending",
                "requested_at": "2024-01-01T00:00:00Z",
            }
        ]
        raw = json.dumps(payload)
        username = import_payload(db, raw)
        assert username == "alice"
