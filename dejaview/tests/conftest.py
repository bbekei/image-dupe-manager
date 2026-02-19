"""
tests/conftest.py — Shared fixtures for DejaView test suite.

Plan reference: §Test Framework — Fixture Strategy.

Rules (plan §Test Development Rules):
- No test touches real %APPDATA% — DB and thumb dirs use tmp_path.
- Each test gets a fresh db fixture (no shared state).
- QApplication is session-scoped (pytest-qt provides qapp automatically,
  but we also declare it here for clarity in non-Qt tests).
"""

import datetime
import sys
from pathlib import Path
from typing import Callable

import pytest
from PIL import Image

# Ensure dejaview package root is importable when running from the
# dejaview/ directory without installing.
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.db import Database


# ---------------------------------------------------------------------------
# Database fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path: Path) -> "Database":
    """
    Fresh SQLite database with the full DejaView schema applied.
    Uses a tmp_path file (not in-memory) so foreign keys / WAL work correctly.
    Torn down after each test.
    """
    d = Database(tmp_path / "test.db")
    d.open()
    yield d
    d.close()


# ---------------------------------------------------------------------------
# Thumbnail directory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def thumb_dir(tmp_path: Path) -> Path:
    """Isolated thumbnail cache directory (plan §conftest.py)."""
    t = tmp_path / "thumbs"
    t.mkdir()
    return t


# ---------------------------------------------------------------------------
# Image factory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def image_factory(tmp_path: Path) -> Callable:
    """
    Returns a callable: make_image(...) -> Path.

    Creates a synthetic Pillow image, saves it to tmp_path, returns its path.

    Args:
        color:  (R, G, B) tuple — primary fill color.
        color2: (R, G, B) tuple — used only when pattern='split_v'. Defaults to
                a darker variant of color. Must be achromatic (R=G=B) when fmt='JPEG'
                to guarantee lossless YCbCr round-trip.
        mode:   Pillow mode string: 'RGB', 'RGBA', 'L', 'P'.
        exif_orientation: EXIF Orientation tag value 1–8 (written via piexif).
                          None = no EXIF data.
                          NOTE: when pattern='split_v', the pixels are physically
                          stored in whatever orientation the caller provides; the
                          caller is responsible for setting the correct EXIF tag so
                          that exif_transpose() restores the original orientation.
        fmt:    'JPEG' or 'PNG'.
        size:   (width, height) — default 64×64.
        pattern: None = solid fill (default).
                 'split_v' = top half color, bottom half color2. Produces a
                 non-monochromatic image suitable for EXIF normalization tests
                 where rotation changes the visible pixel layout.

    Plan §conftest.py — image_factory fixture.
    """
    counter = [0]

    def _make(
        color: tuple = (128, 128, 128),
        color2: tuple | None = None,
        mode: str = "RGB",
        exif_orientation: int | None = None,
        fmt: str = "JPEG",
        size: tuple = (64, 64),
        pattern: str | None = None,
    ) -> Path:
        counter[0] += 1
        ext = ".jpg" if fmt == "JPEG" else ".png"
        out_path = tmp_path / f"img_{counter[0]}{ext}"

        w, h = size

        if pattern == "split_v":
            # Non-monochromatic: top half = color, bottom half = color2.
            # Use achromatic shades (R=G=B) when saving as JPEG so the color
            # values survive the YCbCr round-trip losslessly.
            if color2 is None:
                # Default: darker version of color (halve each channel)
                color2 = tuple(max(0, c // 2) for c in color)
            img = Image.new("RGB", size)
            img.paste(color,  [0, 0,   w, h // 2])
            img.paste(color2, [0, h // 2, w, h])
        elif mode == "RGB":
            img = Image.new("RGB", size, color)
        elif mode == "RGBA":
            img = Image.new("RGBA", size, (*color, 255))
        elif mode == "L":
            lum = int(0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2])
            img = Image.new("L", size, lum)
        elif mode == "P":
            img = Image.new("RGB", size, color).convert("P")
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        save_kwargs: dict = {}
        if exif_orientation is not None and fmt == "JPEG":
            try:
                import piexif
                exif_bytes = piexif.dump(
                    {"0th": {piexif.ImageIFD.Orientation: exif_orientation}}
                )
                save_kwargs["exif"] = exif_bytes
            except ImportError:
                pass  # piexif optional; test will still pass for solid colors

        img.save(str(out_path), fmt, **save_kwargs)
        img.close()
        return out_path

    return _make


# ---------------------------------------------------------------------------
# Session factory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def session_factory(db: "Database") -> Callable:
    """
    Creates a scan session row and returns its id.
    Plan §conftest.py — session_factory fixture.
    """
    def _make(name: str = "Test Session") -> int:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return db.create_session(name, ts)

    return _make


# ---------------------------------------------------------------------------
# Canonical fixture images directory helper
# ---------------------------------------------------------------------------

FIXTURE_IMAGES_DIR = Path(__file__).parent / "fixtures" / "images"


def fixture_image(name: str) -> Path:
    """
    Return the Path to a canonical fixture image.
    Raises FileNotFoundError with a helpful message if fixtures haven't been
    generated yet (run: python tests/fixtures/make_fixtures.py).
    """
    p = FIXTURE_IMAGES_DIR / name
    if not p.exists():
        raise FileNotFoundError(
            f"Fixture image '{name}' not found at {p}.\n"
            "Generate fixtures first: python tests/fixtures/make_fixtures.py"
        )
    return p
