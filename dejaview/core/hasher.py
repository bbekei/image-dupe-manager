"""
core/hasher.py — Pixel-hash, perceptual-hash, and thumbnail generator for DejaView.

Module ownership rules (from plan):
- Pure function: one file path in, (pixel_hash, thumbnail_path, ...) out.
- No DB access.
- Closes the Pillow Image immediately after use (plan §Resource Usage — memory discipline).

Hash pipeline (plan §Pixel hash normalization spec):
  1. Image.open(path)
  2. ImageOps.exif_transpose()   — normalize EXIF orientation
  3. img.convert("RGB")          — unify RGBA / palette / grayscale to one mode
  4. xxhash.xxh128(pixel_bytes).hexdigest()  — 60× faster than SHA-256;
     uses numpy zero-copy view when available to halve peak memory.

Perceptual hash (plan §Similar Image Detection — Phase S1):
  5. imagehash.phash(img)        — 64-bit DCT-based perceptual hash
     Only computed when compute_phash=True (opt-in).

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


def _open_normalized(path: Path) -> Image.Image:
    """Open an image file and normalize to EXIF-transposed RGB.

    Args:
        path: Absolute path to the image file (must exist).

    Returns:
        Pillow Image in RGB mode with EXIF orientation applied.
        Caller is responsible for closing the Image.

    Raises:
        HashError: If the file cannot be opened or decoded.
    """
    _strip_zone_identifier(path)
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    return img


def compute_perceptual_hash(img: Image.Image) -> str:
    """Compute pHash of an already-opened, EXIF-transposed RGB image.

    Args:
        img: Pillow Image, already in RGB mode and EXIF-transposed.

    Returns:
        Hex string of the 64-bit perceptual hash (16 characters).
    """
    import imagehash

    return str(imagehash.phash(img))


def compute_phash_only(
    path: str | Path,
) -> tuple[str, int, int]:
    """Compute only the perceptual hash and dimensions for an image.

    Lightweight alternative to hash_file() for files that already have a
    pixel_hash and thumbnail from Pass 2.  Skips xxHash and thumbnail
    generation entirely.

    Args:
        path: Absolute path to the image file.

    Returns:
        (perceptual_hash, width, height).

    Raises:
        HashError: If the file cannot be opened or decoded.
    """
    path = Path(path)
    if not path.exists():
        raise HashError(f"File not found: {path}") from FileNotFoundError(path)

    img = None
    try:
        img = _open_normalized(path)
        width, height = img.size
        perceptual_hash = compute_perceptual_hash(img)
        return perceptual_hash, width, height
    except (UnidentifiedImageError, OSError, SyntaxError, Exception) as exc:
        if isinstance(exc, HashError):
            raise
        raise HashError(f"Cannot hash {path}: {exc}") from exc
    finally:
        if img is not None:
            try:
                img.close()
            except Exception:
                pass


def hash_file(
    path: str | Path,
    thumb_dir: str | Path,
    compute_phash: bool = False,
) -> tuple[str, str, str | None, int | None, int | None]:
    """
    Hash a single image file and generate its thumbnail.

    Args:
        path:          Absolute path to the image file.
        thumb_dir:     Directory in which to store the 400×400 thumbnail.
        compute_phash: If True, also compute perceptual hash and capture
                       image dimensions.  Default False for backward
                       compatibility with Pass 2.

    Returns:
        (pixel_hash, thumbnail_path, perceptual_hash, width, height).
        perceptual_hash, width, height are None when compute_phash=False.

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
        img = _open_normalized(path)

        # Capture dimensions before hashing (cheap — already decoded).
        width, height = img.size

        # Step 4: xxHash-128 of raw pixel bytes (R3 — 60× faster than SHA-256).
        # numpy zero-copy view avoids a full tobytes() allocation (~69 MB for
        # 24 MP), halving per-worker peak memory.
        if _HAS_NUMPY:
            arr = np.asarray(img)
            pixel_hash: str = xxhash.xxh128_hexdigest(arr.data)
            del arr
        else:
            pixel_hash: str = xxhash.xxh128_hexdigest(img.tobytes())

        # Step 5: perceptual hash (opt-in, plan §Similar Image Detection).
        perceptual_hash: str | None = None
        if compute_phash:
            perceptual_hash = compute_perceptual_hash(img)

        # Thumbnail generation — idempotent
        thumb_path = thumb_dir / f"{pixel_hash}.jpg"
        if not thumb_path.exists():
            thumb = img.copy()
            thumb.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb.save(str(thumb_path), "JPEG", quality=85)

        if compute_phash:
            return pixel_hash, str(thumb_path), perceptual_hash, width, height
        return pixel_hash, str(thumb_path), None, None, None

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
