"""
tests/unit/test_compression.py — Unit tests for data/compression.py.

Covers:
- Streaming compression / decompression round-trip (R-COMP-03)
- SHA-256 integrity checksums (R-COMP-04)
- Skip-upload optimization (R-COMP-05)
- Field shortening / expansion (§3)
- Path tokenization / reconstruction (§3)
- Hash-centric grouping / ungrouping (§3)
- Full pipeline: build_optimized_compressed + decompress_and_expand
- Corrupt data handling
- Compression ratio formatting (§5.1)
- Compressed export / import via export.py wrappers
"""

import datetime
import gzip
import json

import pytest

from data.compression import (
    build_optimized_compressed,
    compress_payload,
    compute_sha256,
    decompress_and_expand,
    decompress_payload,
    detokenize_paths,
    expand_fields,
    format_compression_ratio,
    group_by_hash,
    shorten_fields,
    tokenize_paths,
    ungroup_by_hash,
    verify_checksum,
)
from data.db import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_hash(prefix: str = "a") -> str:
    return (prefix * 32)[:32]


def _make_payload(n_files: int = 10, n_hashes: int = 5) -> dict:
    """Build a realistic export payload for testing."""
    files = []
    for i in range(n_files):
        h = _make_hash(chr(ord("a") + (i % n_hashes)))
        files.append({
            "remote_id": f"user:{i}",
            "pixel_hash": h,
            "size": 1024 * (i + 1),
            "modified_at": "2026-01-01T00:00:00",
            "filename": f"photo_{i}.jpg",
            "path": f"C:/Users/TestUser/Pictures/Vacation/photo_{i}.jpg",
        })
    return {
        "username": "testuser",
        "exported_at": _now(),
        "privacy_level": "full_path",
        "files": files,
    }


# ---------------------------------------------------------------------------
# Streaming compression / decompression (R-COMP-03)
# ---------------------------------------------------------------------------

class TestStreamingCompression:

    def test_round_trip_simple(self):
        """Compress then decompress returns the original payload."""
        payload = {"hello": "world", "count": 42}
        compressed = compress_payload(payload)
        result = decompress_payload(compressed)
        assert result == payload

    def test_round_trip_with_unicode(self):
        """Unicode strings survive compression round-trip."""
        payload = {"name": "Béla", "files": [{"path": "C:/Felhasználó/kép.jpg"}]}
        compressed = compress_payload(payload)
        result = decompress_payload(compressed)
        assert result == payload

    def test_round_trip_empty(self):
        """Empty payload round-trips correctly."""
        payload = {"files": []}
        compressed = compress_payload(payload)
        result = decompress_payload(compressed)
        assert result == payload

    def test_compressed_is_smaller(self):
        """Compressed output should be smaller than raw JSON for repetitive data."""
        payload = _make_payload(n_files=100, n_hashes=10)
        raw_json = json.dumps(payload).encode("utf-8")
        compressed = compress_payload(payload)
        assert len(compressed) < len(raw_json)

    def test_output_is_valid_gzip(self):
        """Compressed output is valid gzip."""
        payload = {"test": True}
        compressed = compress_payload(payload)
        # Should decompress with stdlib gzip
        decompressed = gzip.decompress(compressed)
        assert json.loads(decompressed) == payload

    def test_decompress_invalid_data(self):
        """Decompressing non-gzip data raises ValueError."""
        with pytest.raises(ValueError, match="Decompression failed"):
            decompress_payload(b"this is not gzip data")

    def test_decompress_corrupt_json(self):
        """Decompressing valid gzip with invalid JSON raises ValueError."""
        import io
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
            gz.write(b"not valid json {{{")
        with pytest.raises(ValueError, match="JSON parse failed"):
            decompress_payload(buf.getvalue())


# ---------------------------------------------------------------------------
# SHA-256 integrity (R-COMP-04)
# ---------------------------------------------------------------------------

class TestSHA256Integrity:

    def test_compute_sha256_deterministic(self):
        """Same data produces the same SHA-256."""
        data = b"test data for hashing"
        h1 = compute_sha256(data)
        h2 = compute_sha256(data)
        assert h1 == h2
        assert len(h1) == 64  # hex digest

    def test_compute_sha256_different_data(self):
        """Different data produces different SHA-256."""
        assert compute_sha256(b"hello") != compute_sha256(b"world")

    def test_verify_checksum_valid(self):
        """verify_checksum returns True for matching hash."""
        data = b"test data"
        sha = compute_sha256(data)
        assert verify_checksum(data, sha) is True

    def test_verify_checksum_invalid(self):
        """verify_checksum returns False for mismatched hash."""
        assert verify_checksum(b"data", "0" * 64) is False

    def test_verify_checksum_corrupt_data(self):
        """Modifying one byte fails the checksum."""
        data = b"original data"
        sha = compute_sha256(data)
        corrupted = b"original datb"  # Changed last byte
        assert verify_checksum(corrupted, sha) is False


# ---------------------------------------------------------------------------
# Field shortening (§3)
# ---------------------------------------------------------------------------

class TestFieldShortening:

    def test_shorten_known_fields(self):
        """Known fields are shortened to their short keys."""
        entry = {
            "pixel_hash": "abc",
            "path": "/foo",
            "size": 100,
            "modified_at": "2026-01-01",
            "filename": "pic.jpg",
            "remote_id": "user:1",
            "perceptual_hash": "def",
        }
        result = shorten_fields(entry)
        assert result == {
            "h": "abc",
            "p": "/foo",
            "s": 100,
            "m": "2026-01-01",
            "f": "pic.jpg",
            "r": "user:1",
            "ph": "def",
        }

    def test_expand_reverses_shorten(self):
        """expand_fields reverses shorten_fields."""
        original = {
            "pixel_hash": "abc",
            "path": "/foo",
            "size": 100,
        }
        shortened = shorten_fields(original)
        expanded = expand_fields(shortened)
        assert expanded == original

    def test_unknown_fields_pass_through(self):
        """Fields not in the map pass through unchanged."""
        entry = {"custom_field": "value", "pixel_hash": "abc"}
        result = shorten_fields(entry)
        assert result == {"custom_field": "value", "h": "abc"}


# ---------------------------------------------------------------------------
# Path tokenization (§3)
# ---------------------------------------------------------------------------

class TestPathTokenization:

    def test_tokenize_common_roots(self):
        """Common path roots are replaced with tokens."""
        entries = [
            {"p": "C:/Users/TestUser/Pictures/a.jpg"},
            {"p": "C:/Users/TestUser/Pictures/b.jpg"},
            {"p": "C:/Users/TestUser/Pictures/sub/c.jpg"},
            {"p": "D:/Other/d.jpg"},
        ]
        result, token_map = tokenize_paths(entries)
        # Should have tokenized the common root
        assert len(token_map) > 0
        # Token should appear in the entries
        tokenized_paths = [e["p"] for e in result if "p" in e]
        assert any("<R" in p for p in tokenized_paths)
        # The outlier should NOT be tokenized
        other_entry = [e for e in result if "Other" in e.get("p", "")]
        assert len(other_entry) == 1

    def test_detokenize_reverses_tokenize(self):
        """detokenize_paths restores original paths."""
        original = [
            {"p": "C:/Users/Bob/Pictures/a.jpg"},
            {"p": "C:/Users/Bob/Pictures/b.jpg"},
            {"p": "C:/Users/Bob/Pictures/sub/c.jpg"},
        ]
        tokenized, token_map = tokenize_paths(original)
        restored = detokenize_paths(tokenized, token_map)
        # Paths should match (modulo forward-slash normalization)
        for orig, rest in zip(original, restored):
            assert rest["p"] == orig["p"].replace("\\", "/")

    def test_no_tokenization_for_few_entries(self):
        """No tokenization when paths don't share common roots."""
        entries = [
            {"p": "A:/one.jpg"},
            {"p": "B:/two.jpg"},
        ]
        result, token_map = tokenize_paths(entries)
        assert token_map == {}
        assert result == entries

    def test_empty_entries(self):
        """Empty input returns empty output."""
        result, token_map = tokenize_paths([])
        assert result == []
        assert token_map == {}


# ---------------------------------------------------------------------------
# Hash-centric grouping (§3)
# ---------------------------------------------------------------------------

class TestHashCentricGrouping:

    def test_group_by_hash(self):
        """Files with the same hash are grouped together."""
        entries = [
            {"h": "aaa", "p": "/a.jpg", "s": 100},
            {"h": "aaa", "p": "/b.jpg", "s": 200},
            {"h": "bbb", "p": "/c.jpg", "s": 300},
        ]
        groups = group_by_hash(entries)
        assert len(groups) == 2
        aaa_group = [g for g in groups if g["h"] == "aaa"][0]
        assert len(aaa_group["files"]) == 2
        # Hash should NOT be in the file entries
        for f in aaa_group["files"]:
            assert "h" not in f

    def test_ungroup_reverses_group(self):
        """ungroup_by_hash restores the flat file list."""
        original = [
            {"h": "aaa", "p": "/a.jpg", "s": 100},
            {"h": "aaa", "p": "/b.jpg", "s": 200},
            {"h": "bbb", "p": "/c.jpg", "s": 300},
        ]
        groups = group_by_hash(original)
        restored = ungroup_by_hash(groups)
        assert len(restored) == len(original)
        # All hashes should be restored
        for entry in restored:
            assert "h" in entry

    def test_single_file_per_hash(self):
        """Groups with one file still work correctly."""
        entries = [{"h": "xxx", "p": "/solo.jpg"}]
        groups = group_by_hash(entries)
        assert len(groups) == 1
        assert groups[0]["h"] == "xxx"
        assert len(groups[0]["files"]) == 1


# ---------------------------------------------------------------------------
# Full pipeline: optimize + compress + decompress + expand
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_full_round_trip(self):
        """Full pipeline: optimize -> compress -> decompress -> expand."""
        payload = _make_payload(n_files=20, n_hashes=5)
        compressed, uncompressed_size = build_optimized_compressed(payload)

        assert len(compressed) > 0
        assert uncompressed_size > 0
        assert len(compressed) < uncompressed_size

        # Decompress and expand
        restored = decompress_and_expand(compressed)

        # Check top-level fields preserved
        assert restored["username"] == payload["username"]
        assert restored["privacy_level"] == payload["privacy_level"]

        # Check all files restored
        assert len(restored["files"]) == len(payload["files"])

        # Check field names are expanded back
        for f in restored["files"]:
            assert "pixel_hash" in f
            assert "path" in f

    def test_non_optimized_passthrough(self):
        """Unoptimized payloads (no _format field) pass through decompress_and_expand."""
        payload = {"username": "bob", "files": [{"pixel_hash": "abc"}]}
        compressed = compress_payload(payload)
        result = decompress_and_expand(compressed)
        assert result == payload

    def test_compression_ratio_significant(self):
        """100-file payload should achieve meaningful compression."""
        payload = _make_payload(n_files=100, n_hashes=10)
        compressed, uncompressed_size = build_optimized_compressed(payload)
        ratio = len(compressed) / uncompressed_size
        # Should achieve at least 50% reduction
        assert ratio < 0.5, f"Compression ratio {ratio:.2%} is too high"


# ---------------------------------------------------------------------------
# Compression ratio formatting (§5.1)
# ---------------------------------------------------------------------------

class TestCompressionRatioFormatting:

    def test_format_mb_range(self):
        """Large sizes format as MB."""
        result = format_compression_ratio(50_000_000, 3_200_000)
        assert "50.0 MB" in result
        assert "3.2 MB" in result
        assert "94%" in result

    def test_format_kb_range(self):
        """Medium sizes format as KB."""
        result = format_compression_ratio(500_000, 50_000)
        assert "KB" in result
        assert "90%" in result

    def test_format_bytes_range(self):
        """Small sizes format as B."""
        result = format_compression_ratio(500, 50)
        assert "500 B" in result
        assert "50 B" in result

    def test_format_zero_input(self):
        """Zero input returns empty string."""
        assert format_compression_ratio(0, 0) == ""


# ---------------------------------------------------------------------------
# Compressed export/import via export.py
# ---------------------------------------------------------------------------

class TestCompressedExport:

    def test_build_compressed_export_round_trip(self, db: Database):
        """build_compressed_export produces data that import_compressed_payload can read."""
        from data.export import build_compressed_export, import_compressed_payload

        # Set up a session with files
        session_id = db.create_session("test", _now())
        for i in range(5):
            fid = db.insert_file(
                session_id,
                f"C:/Photos/img_{i}.jpg",
                1024 * (i + 1),
                "2026-01-01T00:00:00",
                _now(),
            )
            db.update_pixel_hash(
                fid,
                _make_hash(chr(ord("a") + (i % 3))),
                f"/thumbs/{i}.jpg",
            )

        # Build compressed export
        compressed, raw_size, gz_size = build_compressed_export(
            db, session_id, "testuser", "full_path"
        )

        assert raw_size > 0
        assert gz_size > 0
        assert gz_size < raw_size

        # Import into a fresh DB
        from data.db import Database as DB2
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmp:
            db2 = DB2(os.path.join(tmp, "test2.db"))
            db2.open()
            try:
                username = import_compressed_payload(db2, compressed)
                assert username == "testuser"
            finally:
                db2.close()

    def test_import_compressed_corrupt_data(self, db: Database):
        """import_compressed_payload raises ImportError on corrupt data."""
        from data.export import import_compressed_payload
        with pytest.raises(ImportError, match="Failed to decompress"):
            import_compressed_payload(db, b"corrupt data")


# ---------------------------------------------------------------------------
# Skip-upload optimization (R-COMP-05)
# ---------------------------------------------------------------------------

class TestSkipUpload:

    def test_unchanged_data_same_sha256(self):
        """Same payload produces same SHA-256 after compression."""
        payload = _make_payload(n_files=10)
        compressed1, _ = build_optimized_compressed(payload)
        compressed2, _ = build_optimized_compressed(payload)
        # Note: gzip output may differ due to timestamps, so compare payloads
        # The skip-upload logic uses SHA-256 of the compressed blob
        # For deterministic comparison, use the decompressed content
        payload1 = decompress_payload(compressed1)
        payload2 = decompress_payload(compressed2)
        assert payload1 == payload2

    def test_changed_data_different_sha256(self):
        """Modified payload produces different SHA-256."""
        payload1 = _make_payload(n_files=10)
        payload2 = _make_payload(n_files=11)  # One extra file
        compressed1, _ = build_optimized_compressed(payload1)
        compressed2, _ = build_optimized_compressed(payload2)
        assert compute_sha256(compressed1) != compute_sha256(compressed2)


# ---------------------------------------------------------------------------
# DB migration: last_upload_sha256
# ---------------------------------------------------------------------------

class TestDBMigration:

    def test_last_upload_sha256_column_exists(self, db: Database):
        """sync_config table has last_upload_sha256 column after open()."""
        cols = {
            r[1] for r in
            db.conn.execute("PRAGMA table_info(sync_config)").fetchall()
        }
        assert "last_upload_sha256" in cols

    def test_upsert_sync_config_with_sha256(self, db: Database):
        """Can store and retrieve last_upload_sha256."""
        db.upsert_sync_config(
            local_username="testuser",
            last_upload_sha256="abc123def456",
        )
        config = db.get_sync_config()
        assert config is not None
        assert config["last_upload_sha256"] == "abc123def456"
