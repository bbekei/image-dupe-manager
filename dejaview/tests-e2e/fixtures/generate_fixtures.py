#!/usr/bin/env python3
"""
Generate synthetic E2E test fixtures.

Creates a small image library with known duplicates:
  - image_a_1.jpg, image_a_2.jpg, image_a_3.jpg  — identical (one duplicate group)
  - image_b.jpg                                    — unique
  - image_c.jpg                                    — unique
  - image_near_a.jpg                               — near-duplicate of image_a (for similarity)

Output directory is printed to stdout so the caller can use it.
Usage:
    python generate_fixtures.py [output_dir]
If output_dir is omitted a temp directory is created.
"""

import sys
import os
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow is required: pip install Pillow", file=sys.stderr)
    sys.exit(1)


def _solid(color: tuple[int, int, int], size: tuple[int, int] = (200, 200)) -> Image.Image:
    img = Image.new("RGB", size, color)
    return img


def _gradient(size: tuple[int, int] = (200, 200)) -> Image.Image:
    img = Image.new("RGB", size)
    pixels = img.load()
    w, h = size
    for y in range(h):
        for x in range(w):
            pixels[x, y] = (int(255 * x / w), int(255 * y / h), 128)
    return img


def generate(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Identical images (will form one duplicate group)
    base = _solid((220, 80, 80))
    base.save(output_dir / "image_a_1.jpg", quality=95)
    base.save(output_dir / "image_a_2.jpg", quality=95)
    base.save(output_dir / "image_a_3.jpg", quality=95)

    # Unique images
    _solid((80, 160, 220)).save(output_dir / "image_b.jpg", quality=95)
    _gradient().save(output_dir / "image_c.jpg", quality=95)

    # Near-duplicate (slightly brighter — triggers similarity detection)
    from PIL import ImageEnhance
    near = ImageEnhance.Brightness(base).enhance(1.15)
    near.save(output_dir / "image_near_a.jpg", quality=95)

    return output_dir


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    else:
        out = Path(tempfile.mkdtemp(prefix="dejaview_e2e_"))

    result = generate(out)
    print(str(result))
