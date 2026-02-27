"""
core/hasher.py — Pixel-hash and thumbnail generator for DejaView.

Module ownership rules (from plan):
- Pure function: one file path in, (pixel_hash, thumbnail_path) out.
- No DB access.
- Closes the Pillow Image immediately after use (plan §Resource Usage — memory discipline).

Hash pipeline (plan §Pixel hash normalization spec):
  1. Image.open(path)
  2. ImageOps.exif_transpose()   — normalize EXIF orientation
  3. img.convert("RGB")          — unify RGBA / palette / grayscale to one mode
  4. xxhash.xxh128(pixel_bytes).hexdigest()  — 60× faster than SHA-256;
     uses numpy zero-copy view when available to halve peak memory.

Thumbnail: 400×400 JPEG written to thumb_dir/{pixel_hash}.jpg.
If the thumbnail already exists it is NOT rewritten (idempotent — plan §Thumbnail caching).
"""

import os
import sys
from pathlib import Path

import xxhash
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

THUMB_SIZE = (400, 400)

# Extensions that hash_file will accept — must match scanner._IMAGE_EXTENSIONS.
_SAFE_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".heic", ".heif"})


def _strip_zone_identifier(path: Path) -> None:
    """Remove the Windows Mark-of-the-Web alternate data stream if present.

    Files downloaded from the internet carry a :Zone.Identifier ADS that can
    cause security software to block reads, resulting in PIL
    ``UnidentifiedImageError``.  Only applied to known image extensions.
    Silently ignored on non-Windows platforms or if the stream does not exist.
    """
    if sys.platform != "win32":
        return
    if path.suffix.lower() not in _SAFE_IMAGE_EXTENSIONS:
        return
    ads = str(path) + ":Zone.Identifier"
    try:
        os.remove(ads)
    except OSError:
        pass


class HashError(Exception):
    """Raised when a file cannot be hashed (corrupt, unreadable, unsupported format)."""


def hash_file(path: str | Path, thumb_dir: str | Path) -> tuple[str, str]:
    """
    Hash a single image file and generate its thumbnail.

    Args:
        path:     Absolute path to the image file.
        thumb_dir: Directory in which to store the 400×400 thumbnail.

    Returns:
        (pixel_hash, thumbnail_path) — both as strings.

    Raises:
        HashError: Wraps FileNotFoundError, UnidentifiedImageError, or any
                   other Pillow/IO exception so callers get a typed error
                   without the scanner crashing (plan §Unit Tests: core/hasher.py).
    """
    path = Path(path)
    thumb_dir = Path(thumb_dir)

    if not path.exists():
        raise HashError(f"File not found: {path}") from FileNotFoundError(path)

    img = None
    try:
        _strip_zone_identifier(path)
        img = Image.open(path)

        # Step 2: normalize EXIF orientation (plan §Pixel hash normalization spec)
        img = ImageOps.exif_transpose(img)

        # Step 3: unify to RGB (handles RGBA, palette, grayscale, etc.)
        img = img.convert("RGB")

        # Step 4: xxHash-128 of raw pixel bytes (R3 — 60× faster than SHA-256).
        # numpy zero-copy view avoids a full tobytes() allocation (~69 MB for
        # 24 MP), halving per-worker peak memory.
        if _HAS_NUMPY:
            arr = np.asarray(img)
            pixel_hash: str = xxhash.xxh128_hexdigest(arr.data)
            del arr
        else:
            pixel_hash: str = xxhash.xxh128_hexdigest(img.tobytes())

        # Thumbnail generation — idempotent
        thumb_path = thumb_dir / f"{pixel_hash}.jpg"
        if not thumb_path.exists():
            thumb = img.copy()
            thumb.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb.save(str(thumb_path), "JPEG", quality=85)

        return pixel_hash, str(thumb_path)

    except (UnidentifiedImageError, OSError, SyntaxError, Exception) as exc:
        if isinstance(exc, HashError):
            raise
        raise HashError(f"Cannot hash {path}: {exc}") from exc
    finally:
        # Close the Image immediately — no decoded image kept in memory
        # across files (plan §Resource Usage — memory discipline).
        if img is not None:
            try:
                img.close()
            except Exception:
                pass
