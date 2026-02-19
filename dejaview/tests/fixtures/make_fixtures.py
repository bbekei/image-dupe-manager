"""
tests/fixtures/make_fixtures.py — Generate canonical fixture images for the test suite.

This is a standalone SCRIPT, not a pytest test (plan §Fixture Strategy).
Run it once to populate tests/fixtures/images/ and commit the binaries to VCS.

Usage:
    cd dejaview
    python tests/fixtures/make_fixtures.py

Generated files (plan §tests/fixtures/make_fixtures.py):

  red_rgb.jpg          — 64×64 solid gray (128,128,128) as JPEG
                         Named 'red_*' per plan spec; uses achromatic gray because
                         JPEG YCbCr round-trip is only lossless for achromatic colors.
                         After normalization, hashes identically to red_rgba.png and
                         red_gray.png (same pixel content via different format paths).
  red_rgba.png         — 64×64 solid gray (128,128,128) as RGBA PNG
  red_gray.png         — 64×64 solid gray (128,128,128) as L (grayscale) PNG
  red_exif_rot90.jpg   — same gray JPEG with EXIF orientation=6 (90° CW) embedded
  blue_rgb.jpg         — 64×64 solid blue (0,0,255) as JPEG — visually different
  corrupt.jpg          — truncated JPEG bytes (for error-handling tests)

Design note on JPEG lossiness:
  Pure red (255,0,0) and most non-gray colors do NOT round-trip through JPEG's
  YCbCr conversion without rounding error. Gray (R=G=B) maps to Cb=Cr=128
  exactly, making YCbCr↔RGB perfectly invertible at any JPEG quality level.
  This ensures the canonical 'same visual content across formats' test is stable.
"""

import sys
from pathlib import Path

try:
    from PIL import Image
    import piexif
except ImportError:
    sys.exit(
        "ERROR: Pillow and piexif are required.\n"
        "Install: pip install Pillow piexif"
    )

OUT_DIR = Path(__file__).parent / "images"
SIZE = (64, 64)

# Achromatic gray — survives JPEG YCbCr round-trip perfectly
CONTENT_COLOR = (128, 128, 128)
# Blue — clearly different visual content
BLUE_COLOR = (0, 0, 255)


def make_all(out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    gray_rgb = Image.new("RGB", SIZE, CONTENT_COLOR)

    # red_rgb.jpg — JPEG, achromatic content; quality=95 + subsampling=0 for
    # reliable YCbCr round-trip
    gray_rgb.save(out_dir / "red_rgb.jpg", "JPEG", quality=95, subsampling=0)
    print("OK red_rgb.jpg (gray JPEG, quality=95, subsampling=0)")

    # red_rgba.png — same content as RGBA PNG (lossless)
    gray_rgb.convert("RGBA").save(out_dir / "red_rgba.png", "PNG")
    print("OK red_rgba.png (gray RGBA PNG)")

    # red_gray.png — same content as L (grayscale) PNG
    gray_rgb.convert("L").save(out_dir / "red_gray.png", "PNG")
    print("OK red_gray.png (gray L-mode PNG)")

    # red_exif_rot90.jpg — same gray JPEG with EXIF orientation=6 (90° CW)
    # After ImageOps.exif_transpose(), a uniform image is unchanged,
    # so it hashes identically to red_rgb.jpg.
    try:
        exif_data = piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}})
        gray_rgb.save(
            out_dir / "red_exif_rot90.jpg",
            "JPEG", quality=95, subsampling=0, exif=exif_data,
        )
        print("OK red_exif_rot90.jpg (gray JPEG with EXIF orientation=6)")
    except Exception as e:
        gray_rgb.save(out_dir / "red_exif_rot90.jpg", "JPEG", quality=95, subsampling=0)
        print(f"  WARNING: piexif failed ({e}); saved without EXIF (test may fail)")

    # blue_rgb.jpg — visually different content; blue also survives YCbCr round-trip
    # because (0,0,255) → Y=29, Cb=255, Cr=107 — all within range and no rounding loss
    blue_rgb = Image.new("RGB", SIZE, BLUE_COLOR)
    blue_rgb.save(out_dir / "blue_rgb.jpg", "JPEG", quality=95, subsampling=0)
    print("OK blue_rgb.jpg (blue JPEG)")

    # corrupt.jpg — truncated JPEG (SOI marker + truncated APP0; Pillow raises on load)
    (out_dir / "corrupt.jpg").write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 12)
    print("OK corrupt.jpg (truncated JPEG)")

    # ── Non-monochromatic pattern fixtures ───────────────────────────────────
    # Two-color split: top half light-gray (128,128,128), bottom half dark-gray (64,64,64).
    # Both shades are achromatic → survive JPEG YCbCr round-trip.
    # Image is NON-SYMMETRIC: rotation produces a visibly different pixel layout,
    # making the EXIF normalization test non-trivial.

    LIGHT = (128, 128, 128)
    DARK  = (64, 64, 64)
    pattern = Image.new("RGB", SIZE)
    pattern.paste(LIGHT, [0, 0, SIZE[0], SIZE[1] // 2])   # top half
    pattern.paste(DARK,  [0, SIZE[1] // 2, SIZE[0], SIZE[1]])  # bottom half

    # pattern_rgb.jpg — normal orientation, no EXIF
    pattern.save(out_dir / "pattern_rgb.jpg", "JPEG", quality=95, subsampling=0)
    print("OK pattern_rgb.jpg (split-gray JPEG, normal orientation)")

    # pattern_exif_rot90.jpg — pixels stored 90° CCW with EXIF orientation=6.
    # Pillow's exif_transpose for orientation=6 applies ROTATE_270 (≡ 90° CW),
    # which undoes the stored 90° CCW rotation → restores original pixel layout.
    # Crucially: raw pixels DIFFER from pattern_rgb.jpg (test is non-trivial),
    # but normalized pixels MATCH (test proves exif_transpose is doing real work).
    try:
        rotated_ccw = pattern.rotate(90, expand=True)   # store 90° CCW
        pat_exif = piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}})
        rotated_ccw.save(
            out_dir / "pattern_exif_rot90.jpg",
            "JPEG", quality=95, subsampling=0, exif=pat_exif,
        )
        print("OK pattern_exif_rot90.jpg (split-gray JPEG, stored 90° CCW + EXIF=6)")
    except Exception as e:
        pattern.save(out_dir / "pattern_exif_rot90.jpg", "JPEG", quality=95, subsampling=0)
        print(f"  WARNING: piexif failed ({e}); pattern_exif_rot90 saved without EXIF")

    print(f"\nAll fixture images written to {out_dir.resolve()}")

    # ── Sanity checks ─────────────────────────────────────────────────────────
    from PIL import ImageOps
    import hashlib

    def _h(path: Path) -> str:
        """Normalized hash (full pipeline)."""
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        return hashlib.sha256(img.tobytes()).hexdigest()[:16]

    def _h_raw(path: Path) -> str:
        """Raw hash — no EXIF transpose (used to verify non-triviality)."""
        img = Image.open(path).convert("RGB")
        return hashlib.sha256(img.tobytes()).hexdigest()[:16]

    h_jpg   = _h(out_dir / "red_rgb.jpg")
    h_png   = _h(out_dir / "red_rgba.png")
    h_gray  = _h(out_dir / "red_gray.png")
    h_exif  = _h(out_dir / "red_exif_rot90.jpg")
    h_blue  = _h(out_dir / "blue_rgb.jpg")
    h_pat   = _h(out_dir / "pattern_rgb.jpg")
    h_pat_n = _h(out_dir / "pattern_exif_rot90.jpg")
    h_pat_r = _h_raw(out_dir / "pattern_exif_rot90.jpg")

    checks = [
        ("red_rgb.jpg == red_rgba.png",              h_jpg == h_png),
        ("red_rgb.jpg == red_gray.png",              h_jpg == h_gray),
        ("red_rgb.jpg == red_exif_rot90 (norm)",     h_jpg == h_exif),
        ("red_rgb.jpg != blue_rgb.jpg",              h_jpg != h_blue),
        ("pattern_rgb != pattern_exif (raw)",        h_pat != h_pat_r),
        ("pattern_rgb == pattern_exif (normalized)", h_pat == h_pat_n),
    ]
    ok = all(v for _, v in checks)
    status = "PASS" if ok else "FAIL"
    print(f"\nSelf-check [{status}]:")
    for label, result in checks:
        mark = "OK" if result else "FAIL"
        print(f"  [{mark}] {label}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    make_all()
