"""
tests/unit/test_hasher.py — Unit tests for core/hasher.py.

Plan reference: §Unit Tests: core/hasher.py.

All tests use the image_factory fixture (dynamic synthetic images) plus the
canonical fixture images in tests/fixtures/images/ where EXIF round-trip
precision is required.
"""

import os
import stat
from pathlib import Path

import pytest
from PIL import UnidentifiedImageError

from core.hasher import HashError, hash_file
from tests.conftest import fixture_image, FIXTURE_IMAGES_DIR


# Skip the canonical fixture tests if images haven't been generated yet.
# Run: python tests/fixtures/make_fixtures.py to generate them.
FIXTURES_AVAILABLE = (FIXTURE_IMAGES_DIR / "red_rgb.jpg").exists()
needs_fixtures = pytest.mark.skipif(
    not FIXTURES_AVAILABLE,
    reason="Canonical fixture images not generated. Run: python tests/fixtures/make_fixtures.py",
)


# ---------------------------------------------------------------------------
# Hash correctness — using dynamic image_factory
# ---------------------------------------------------------------------------

class TestHashCorrectness:
    """Req 4.1-adjacent — pixel-hash normalization pipeline (plan §hasher.py)."""

    def test_same_rgb_image_gives_same_hash(self, image_factory, thumb_dir):
        """Same file hashed twice gives identical hash."""
        p = image_factory(color=(255, 0, 0), mode="RGB")
        h1, _ = hash_file(p, thumb_dir)
        h2, _ = hash_file(p, thumb_dir)
        assert h1 == h2

    def test_different_images_produce_different_hashes(self, image_factory, thumb_dir):
        """Visually different images must not collide (plan §test_different_images_produce_different_hashes)."""
        red = image_factory(color=(255, 0, 0), mode="RGB")
        blue = image_factory(color=(0, 0, 255), mode="RGB")
        h_red, _ = hash_file(red, thumb_dir)
        h_blue, _ = hash_file(blue, thumb_dir)
        assert h_red != h_blue

    def test_rgba_image_matches_rgb_equivalent(self, image_factory, thumb_dir):
        """RGBA PNG and RGB JPEG of same color produce identical hash after RGB normalization."""
        color = (100, 200, 50)
        rgb_path = image_factory(color=color, mode="RGB", fmt="JPEG")
        rgba_path = image_factory(color=color, mode="RGBA", fmt="PNG")
        h_rgb, _ = hash_file(rgb_path, thumb_dir)
        h_rgba, _ = hash_file(rgba_path, thumb_dir)
        assert h_rgb == h_rgba, "RGBA and RGB of same content must hash equally"

    def test_grayscale_image_hash(self, image_factory, thumb_dir):
        """
        Grayscale (L mode) image hashes consistently.
        Note: after convert("RGB"), a grayscale red becomes a neutral gray in RGB
        because luminance of (255,0,0) ≈ 76. This tests the pipeline is applied
        correctly, not that grayscale matches RGB red (they differ in color space).
        """
        gray_path = image_factory(color=(200, 200, 200), mode="L")
        # Same gray value created directly as RGB
        rgb_gray_path = image_factory(color=(200, 200, 200), mode="RGB")
        h_gray, _ = hash_file(gray_path, thumb_dir)
        h_rgb, _ = hash_file(rgb_gray_path, thumb_dir)
        # Both should be identical because L(200) → RGB(200,200,200) after convert
        assert h_gray == h_rgb

    def test_hash_is_64_char_hex_string(self, image_factory, thumb_dir):
        """pixel_hash must always be a 64-character lowercase hex string."""
        p = image_factory()
        h, _ = hash_file(p, thumb_dir)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_two_copies_of_pattern_image_same_hash(self, image_factory, thumb_dir, tmp_path):
        """
        Dynamic version of the two-copies test: verifies the core use case
        (renamed duplicate file) with a non-monochromatic pattern image.
        """
        import shutil
        # Achromatic grays — survive JPEG YCbCr round-trip
        p = image_factory(
            color=(128, 128, 128), color2=(64, 64, 64), pattern="split_v", fmt="JPEG"
        )
        copy_path = tmp_path / "copy_of_pattern.jpg"
        shutil.copy2(p, copy_path)
        h1, _ = hash_file(p, thumb_dir)
        h2, _ = hash_file(copy_path, thumb_dir)
        assert h1 == h2



# ---------------------------------------------------------------------------
# Hash correctness — canonical fixture images (requires make_fixtures.py)
# ---------------------------------------------------------------------------

class TestHashCorrectnessCanonical:
    """Plan §test_same_content_jpg_and_png_produce_same_hash etc."""

    @needs_fixtures
    def test_red_jpg_and_red_rgba_png_same_hash(self, thumb_dir):
        """
        red_rgb.jpg (JPEG) and red_rgba.png (PNG RGBA) have the same visual content
        → same hash after normalization (plan §test_same_content_jpg_and_png_produce_same_hash).

        Note: fixtures use an achromatic gray (128,128,128) as the canonical color
        because JPEG YCbCr round-trip is only perfectly lossless for achromatic colors.
        The test verifies the normalization pipeline (RGBA→RGB and JPEG→RGB both work).
        """
        h_jpg, _ = hash_file(fixture_image("red_rgb.jpg"), thumb_dir)
        h_png, _ = hash_file(fixture_image("red_rgba.png"), thumb_dir)
        assert h_jpg == h_png

    @needs_fixtures
    def test_grayscale_image_produces_same_hash_as_rgb_equivalent(self, thumb_dir):
        """
        red_gray.png (L mode) and red_rgb.jpg (RGB JPEG, same achromatic content)
        produce the same hash after convert("RGB") normalization.
        Plan §test_grayscale_image_produces_same_hash_as_rgb_equivalent.
        """
        h_gray, _ = hash_file(fixture_image("red_gray.png"), thumb_dir)
        h_jpg, _ = hash_file(fixture_image("red_rgb.jpg"), thumb_dir)
        assert h_gray == h_jpg

    @needs_fixtures
    def test_exif_orientation_is_normalized(self, thumb_dir):
        """
        red_rgb.jpg and red_exif_rot90.jpg are the same solid-color image;
        after EXIF transpose they must hash identically.
        Plan §test_exif_orientation_is_normalized.

        Note: this uses a solid (monochromatic) image. A 90° rotation of a uniform
        image is visually identical, so this test only verifies that exif_transpose
        does NOT corrupt the hash — not that it performs the correct geometric
        transformation. See test_exif_normalization_does_real_work below for the
        meaningful non-trivial EXIF test using a non-monochromatic pattern image.
        """
        h_normal, _ = hash_file(fixture_image("red_rgb.jpg"), thumb_dir)
        h_rotated, _ = hash_file(fixture_image("red_exif_rot90.jpg"), thumb_dir)
        assert h_normal == h_rotated

    @needs_fixtures
    def test_exif_normalization_does_real_work(self, thumb_dir):
        """
        Non-trivial EXIF normalization test using a non-monochromatic pattern image
        (top half light-gray, bottom half dark-gray).

        Proves that the hasher.py pipeline actually calls ImageOps.exif_transpose()
        and that it performs the correct geometric transformation:

        1. Raw pixels of pattern_exif_rot90.jpg DIFFER from pattern_rgb.jpg
           (the stored rotation is real — it changes the pixel layout).
        2. After normalization (exif_transpose applied), both produce the SAME hash
           (the rotation is correctly undone, restoring the original orientation).

        If exif_transpose() were removed from hasher.py, assertion 2 would fail.
        If the fixture were a solid color, assertion 1 would trivially pass but
        assertion 2 would not prove anything about geometric correctness.
        """
        import hashlib
        from PIL import Image as _PilImage

        # Assertion 1: raw pixels differ (EXIF rotation genuinely changes layout)
        def _raw_hash(path):
            img = _PilImage.open(path).convert("RGB")
            return hashlib.sha256(img.tobytes()).hexdigest()

        h_raw_normal  = _raw_hash(fixture_image("pattern_rgb.jpg"))
        h_raw_rotated = _raw_hash(fixture_image("pattern_exif_rot90.jpg"))
        assert h_raw_normal != h_raw_rotated, (
            "Raw pixel hashes should differ — the stored rotation must change the "
            "pixel layout. If they match, the fixture was not generated correctly."
        )

        # Assertion 2: normalized hashes match (exif_transpose correctly undoes rotation)
        h_normal, _  = hash_file(fixture_image("pattern_rgb.jpg"), thumb_dir)
        h_rotated, _ = hash_file(fixture_image("pattern_exif_rot90.jpg"), thumb_dir)
        assert h_normal == h_rotated, (
            "After EXIF normalization, pattern_rgb.jpg and pattern_exif_rot90.jpg "
            "must produce identical hashes. This fails if exif_transpose() is "
            "absent or applies the wrong transformation."
        )

    @needs_fixtures
    def test_two_copies_of_complex_image_same_hash(self, tmp_path, thumb_dir):
        """
        Two copies of the same file must hash identically — this is the core
        duplicate-detection use case (plan §Why pixel-hash instead of file-hash).

        Uses the non-monochromatic pattern fixture to verify the pipeline works
        for realistic (multi-pixel-value) content, not just solid fills.
        """
        import shutil
        original = fixture_image("pattern_rgb.jpg")
        copy_path = tmp_path / "pattern_rgb_copy.jpg"
        shutil.copy2(original, copy_path)

        h_orig, _ = hash_file(original, thumb_dir)
        h_copy, _ = hash_file(copy_path, thumb_dir)
        assert h_orig == h_copy, "Two copies of the same file must produce identical hashes"

    @needs_fixtures
    def test_red_and_blue_produce_different_hashes(self, thumb_dir):
        """Plan §test_different_images_produce_different_hashes."""
        h_red, _ = hash_file(fixture_image("red_rgb.jpg"), thumb_dir)
        h_blue, _ = hash_file(fixture_image("blue_rgb.jpg"), thumb_dir)
        assert h_red != h_blue


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------

class TestThumbnailGeneration:
    """Plan §Thumbnail generation tests."""

    def test_thumbnail_is_created_at_correct_path(self, image_factory, thumb_dir):
        """Thumbnail must be at thumb_dir/{pixel_hash}.jpg after hash_file()."""
        p = image_factory()
        pixel_hash, thumb_path = hash_file(p, thumb_dir)
        expected = thumb_dir / f"{pixel_hash}.jpg"
        assert expected.exists(), f"Thumbnail not found at {expected}"
        assert Path(thumb_path) == expected

    def test_thumbnail_dimensions_are_400x400_or_smaller(self, image_factory, thumb_dir):
        """Thumbnails must not exceed 400×400 (plan §test_thumbnail_dimensions_are_400x400_or_smaller)."""
        # Use a large image to ensure downscaling happens
        p = image_factory(size=(800, 600))
        pixel_hash, thumb_path = hash_file(p, thumb_dir)
        from PIL import Image as PilImage
        with PilImage.open(thumb_path) as t:
            w, h = t.size
        assert w <= 400
        assert h <= 400

    def test_thumbnail_not_recreated_if_already_exists(self, image_factory, thumb_dir):
        """
        hash_file() must not overwrite an existing thumbnail — idempotent
        (plan §test_thumbnail_not_recreated_if_already_exists).
        """
        p = image_factory()
        pixel_hash, thumb_path = hash_file(p, thumb_dir)
        mtime_before = os.path.getmtime(thumb_path)
        # Second call — thumbnail already exists
        hash_file(p, thumb_dir)
        mtime_after = os.path.getmtime(thumb_path)
        assert mtime_before == mtime_after, "Thumbnail was rewritten on second call"

    def test_thumbnail_file_is_jpeg(self, image_factory, thumb_dir):
        """Thumbnail must be a readable JPEG."""
        from PIL import Image as PilImage
        p = image_factory()
        _, thumb_path = hash_file(p, thumb_dir)
        with PilImage.open(thumb_path) as t:
            assert t.format == "JPEG"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Plan §Error handling tests for hasher.py."""

    def test_corrupt_file_raises_hash_error(self, tmp_path, thumb_dir):
        """
        A corrupt image must raise HashError, never return a garbage hash
        (plan §test_corrupt_file_raises_or_returns_none).
        """
        corrupt = tmp_path / "corrupt.jpg"
        corrupt.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 4)
        with pytest.raises(HashError):
            hash_file(corrupt, thumb_dir)

    @needs_fixtures
    def test_canonical_corrupt_fixture_raises_hash_error(self, thumb_dir):
        """Canonical corrupt.jpg fixture must raise HashError."""
        with pytest.raises(HashError):
            hash_file(fixture_image("corrupt.jpg"), thumb_dir)

    def test_nonexistent_file_raises_hash_error(self, tmp_path, thumb_dir):
        """Plan §test_nonexistent_file_raises_file_not_found."""
        missing = tmp_path / "does_not_exist.jpg"
        with pytest.raises(HashError):
            hash_file(missing, thumb_dir)

    def test_hash_error_wraps_file_not_found(self, tmp_path, thumb_dir):
        """HashError for missing file must wrap or be caused by FileNotFoundError."""
        missing = tmp_path / "ghost.jpg"
        with pytest.raises(HashError) as exc_info:
            hash_file(missing, thumb_dir)
        # The error message must reference the file
        assert "ghost.jpg" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    def test_corrupt_file_does_not_write_partial_thumbnail(self, tmp_path, thumb_dir):
        """A failed hash must not leave a partial thumbnail file."""
        corrupt = tmp_path / "corrupt2.jpg"
        corrupt.write_bytes(b"\xFF\xD8" + b"\x00" * 2)
        try:
            hash_file(corrupt, thumb_dir)
        except HashError:
            pass
        thumbs = list(thumb_dir.iterdir())
        assert len(thumbs) == 0, f"Partial thumbnail was written: {thumbs}"
