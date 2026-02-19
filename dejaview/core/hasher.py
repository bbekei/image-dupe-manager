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
  4. hashlib.sha256(img.tobytes()).hexdigest()

Thumbnail: 400×400 JPEG written to thumb_dir/{pixel_hash}.jpg.
If the thumbnail already exists it is NOT rewritten (idempotent — plan §Thumbnail caching).
"""

import hashlib
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

THUMB_SIZE = (400, 400)


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
        img = Image.open(path)

        # Step 2: normalize EXIF orientation (plan §Pixel hash normalization spec)
        img = ImageOps.exif_transpose(img)

        # Step 3: unify to RGB (handles RGBA, palette, grayscale, etc.)
        img = img.convert("RGB")

        # Step 4: SHA-256 of raw pixel bytes
        pixel_hash: str = hashlib.sha256(img.tobytes()).hexdigest()

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
