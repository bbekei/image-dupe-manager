"""
tests/integration/test_cross_library.py — Cross-library round-trip tests.

Plan §Test Framework — tests/integration/test_cross_library.py.

These tests exercise the export → import → cross-library JOIN query pipeline
without mocking, against real (tmp_path) DB and filesystem.
"""

import json
import datetime

import pytest

from data.db import Database
from data.export import build_export_payload, import_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_UNSHARED = "f" * 64


def _setup_local_files(db, session_id):
    """Insert local files with known hashes for cross-library testing."""
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.insert_file(session_id, r"C:\Photos\beach.jpg", 2048000, ts, ts)
    db.insert_file(session_id, r"C:\Photos\sunset.jpg", 1500000, ts, ts)
    db.insert_file(session_id, r"C:\Photos\unique.jpg", 999000, ts, ts)

    files = db.get_files_for_session(session_id)
    db.update_pixel_hash(files[0]["id"], HASH_A, "/thumbs/a.jpg")
    db.update_pixel_hash(files[1]["id"], HASH_B, "/thumbs/b.jpg")
    db.update_pixel_hash(files[2]["id"], HASH_UNSHARED, "/thumbs/f.jpg")
    return files


def _make_peer_export(username, pixel_hashes, privacy="filename"):
    """Build a peer export payload with the given hashes."""
    files = []
    for i, h in enumerate(pixel_hashes):
        entry = {
            "remote_id": f"{username}:{i + 1}",
            "pixel_hash": h,
            "size": 1000 + i,
            "modified_at": "2024-01-01T00:00:00Z",
        }
        if privacy in ("filename", "full_path"):
            entry["filename"] = f"peer_img_{i + 1}.jpg"
        if privacy == "full_path":
            entry["path"] = f"/home/{username}/pics/peer_img_{i + 1}.jpg"
        files.append(entry)
    return {
        "username": username,
        "exported_at": "2024-06-01T00:00:00Z",
        "privacy_level": privacy,
        "files": files,
    }


# ---------------------------------------------------------------------------
# Tests (plan §integration/test_cross_library.py)
# ---------------------------------------------------------------------------


class TestExportThenImport:
    """test_export_then_import_produces_cross_library_match"""

    def test_cross_library_match_found(self, db, session_factory):
        """Given local file with HASH_A and peer export containing HASH_A,
        cross-library JOIN returns one result."""
        sid = session_factory()
        _setup_local_files(db, sid)

        peer_payload = _make_peer_export("alice", [HASH_A])
        import_payload(db, json.dumps(peer_payload))

        matches = db.get_cross_library_matches(sid)
        assert len(matches) >= 1
        matched_hashes = {m["pixel_hash"] for m in matches}
        assert HASH_A in matched_hashes
        # Result includes peer username
        assert any(m["username"] == "alice" for m in matches)

    def test_cross_library_match_includes_local_metadata(self, db, session_factory):
        """Result row includes local file path."""
        sid = session_factory()
        _setup_local_files(db, sid)

        import_payload(db, json.dumps(_make_peer_export("alice", [HASH_A])))

        matches = db.get_cross_library_matches(sid)
        local_paths = {m["local_path"] for m in matches}
        assert r"C:\Photos\beach.jpg" in local_paths


class TestHashOnlyPrivacy:
    """test_hash_only_import_does_not_expose_peer_filenames"""

    def test_hash_only_no_filename(self, db, session_factory):
        sid = session_factory()
        _setup_local_files(db, sid)

        peer_payload = _make_peer_export("alice", [HASH_A], privacy="hash_only")
        import_payload(db, json.dumps(peer_payload))

        matches = db.get_cross_library_matches(sid)
        assert len(matches) >= 1
        for m in matches:
            assert m["remote_filename"] is None


class TestNoMatch:
    """test_no_cross_library_match_for_unshared_hash"""

    def test_different_hash_no_match(self, db, session_factory):
        sid = session_factory()
        _setup_local_files(db, sid)

        # Peer has a completely different hash
        peer_payload = _make_peer_export("carol", ["d" * 64])
        import_payload(db, json.dumps(peer_payload))

        matches = db.get_cross_library_matches(sid)
        usernames = {m["username"] for m in matches}
        assert "carol" not in usernames


class TestMultiplePeers:
    """test_multiple_peers_both_matched"""

    def test_two_peers_same_hash(self, db, session_factory):
        sid = session_factory()
        _setup_local_files(db, sid)

        for peer in ("alice", "dave"):
            payload = _make_peer_export(peer, [HASH_A])
            import_payload(db, json.dumps(payload))

        matches = db.get_cross_library_matches(sid)
        usernames = {m["username"] for m in matches}
        assert "alice" in usernames
        assert "dave" in usernames


class TestRemovePeer:
    """test_removing_peer_removes_their_cross_library_results"""

    def test_remove_peer_clears_matches(self, db, session_factory):
        sid = session_factory()
        _setup_local_files(db, sid)

        import_payload(db, json.dumps(_make_peer_export("alice", [HASH_A])))
        assert len(db.get_cross_library_matches(sid)) >= 1

        db.delete_remote_peer("alice")

        matches = db.get_cross_library_matches(sid)
        usernames = {m["username"] for m in matches}
        assert "alice" not in usernames


class TestFullRoundTrip:
    """End-to-end: local scan → export → import by another 'user' → match."""

    @pytest.mark.parametrize("privacy", ["hash_only", "filename", "full_path"])
    def test_round_trip_all_privacy_levels(self, db, session_factory, privacy):
        """Plan §Workflow 6 — manual export/import round trip."""
        sid = session_factory()
        _setup_local_files(db, sid)

        # Export local scan as "bob"
        payload = build_export_payload(db, sid, "bob", privacy)
        raw = json.dumps(payload)

        # Import as if another user received it
        import_payload(db, raw)

        matches = db.get_cross_library_matches(sid)
        # local files with HASH_A and HASH_B should match bob's export
        matched_hashes = {m["pixel_hash"] for m in matches}
        assert HASH_A in matched_hashes
        assert HASH_B in matched_hashes
        # HASH_UNSHARED should also match (bob exported it too)
        assert HASH_UNSHARED in matched_hashes

    def test_round_trip_skips_deleted_files(self, db, session_factory):
        """Deleted files should not appear in export or cross-library matches."""
        sid = session_factory()
        files = _setup_local_files(db, sid)
        # Delete the third file
        db.update_file_status(files[2]["id"], "deleted")

        payload = build_export_payload(db, sid, "bob", "hash_only")
        assert len(payload["files"]) == 2  # Only active files

        import_payload(db, json.dumps(payload))

        matches = db.get_cross_library_matches(sid)
        matched_hashes = {m["pixel_hash"] for m in matches}
        assert HASH_UNSHARED not in matched_hashes
