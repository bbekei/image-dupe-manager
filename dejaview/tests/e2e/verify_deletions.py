"""
tests/e2e/verify_deletions.py — Post-cleanup deletion verifier.

Standalone script that verifies every image in the DejaView trash folder
has an exact pixel-hash duplicate still present in the source directory.
Guarantees no image data is lost after a cleanup run.

Usage (standalone):
    python tests/e2e/verify_deletions.py

Usage (programmatic / future e2e):
    from tests.e2e.verify_deletions import verify_deletions
    report = verify_deletions(source_dir, trash_dir, csv_path)
    assert report.missing == 0

The pixel-hash algorithm is identical to core/hasher.py:
  1. Image.open → exif_transpose → convert("RGB")
  2. xxhash.xxh128(pixel_bytes).hexdigest()

Performance (mirrors core/scanner.py):
  - ThreadPoolExecutor parallelism (Pillow/xxhash release the GIL)
  - Memory-aware worker count cap
  - Zone.Identifier ADS stripping on Windows
"""

import concurrent.futures
import csv
import ctypes
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import xxhash
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# Same extensions the app accepts.
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".heic", ".heif", ".png", ".bmp", ".tiff", ".tif", ".webp"})

# Default trash location (matches main_window.py).
DEFAULT_TRASH_ROOT = Path(
    os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
) / "DejaView" / ".dejaview_trash"

# Extensions eligible for Zone.Identifier stripping (matches core/hasher.py).
_SAFE_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".heic", ".heif"})

# Memory budget per worker (MB) — same as scanner.py.
_MEMORY_PER_WORKER_MB = 150
_MEMORY_RESERVE_MB = 2048


# ---------------------------------------------------------------------------
# Worker count (mirrors core/scanner.py _memory_worker_cap)
# ---------------------------------------------------------------------------

def _memory_worker_cap() -> int:
    """Return the max workers that fit in available RAM, or 16 as fallback."""
    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            avail_mb = stat.ullAvailPhys // (1024 * 1024)
        else:
            pages = os.sysconf("SC_AVPHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            avail_mb = (pages * page_size) // (1024 * 1024)
        usable_mb = max(0, avail_mb - _MEMORY_RESERVE_MB)
        return max(2, usable_mb // _MEMORY_PER_WORKER_MB)
    except Exception:
        return 16


def _optimal_workers() -> int:
    """Compute optimal thread pool size, capped by CPU and RAM."""
    cpu_cap = min(os.cpu_count() or 4, 16)
    mem_cap = _memory_worker_cap()
    return max(2, min(cpu_cap, mem_cap))


# ---------------------------------------------------------------------------
# Zone.Identifier stripping (mirrors core/hasher.py)
# ---------------------------------------------------------------------------

def _strip_zone_identifier(path: Path) -> None:
    """Remove the Windows Mark-of-the-Web ADS if present."""
    if sys.platform != "win32":
        return
    if path.suffix.lower() not in _SAFE_IMAGE_EXTENSIONS:
        return
    ads = str(path) + ":Zone.Identifier"
    try:
        os.remove(ads)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Pixel hash (mirrors core/hasher.py exactly)
# ---------------------------------------------------------------------------

def pixel_hash(path: Path) -> str:
    """Compute the xxh128 pixel hash for an image, identical to core/hasher.hash_file."""
    img = None
    try:
        _strip_zone_identifier(path)
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")

        if _HAS_NUMPY:
            arr = np.asarray(img)
            h = xxhash.xxh128_hexdigest(arr.data)
            del arr
        else:
            h = xxhash.xxh128_hexdigest(img.tobytes())

        return h
    finally:
        if img is not None:
            try:
                img.close()
            except Exception:
                pass


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# Core verification logic (reusable from e2e tests and GUI)
# ---------------------------------------------------------------------------

@dataclass
class VerificationReport:
    """Result of a deletion verification run."""
    matched: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    csv_path: str | None = None

    @property
    def total_trash(self) -> int:
        return len(self.matched) + len(self.missing) + len(self.errors)

    @property
    def ok(self) -> bool:
        return len(self.missing) == 0 and len(self.errors) == 0


def verify_deletions(
    source_dir: str | Path,
    trash_dir: str | Path,
    csv_path: str | Path | None = None,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> VerificationReport:
    """Verify that every trashed image has an exact pixel-hash match in source_dir.

    Args:
        source_dir: Directory where originals still reside.
        trash_dir:  DejaView trash directory (may contain session subfolders).
        csv_path:   Where to write the CSV report. None = auto-generate next to script.
        on_log:     Optional callback for log messages (GUI or CLI).
        on_progress: Optional callback (current, total) for progress updates.

    Returns:
        VerificationReport with matched/missing/error lists.
    """
    source_dir = Path(source_dir)
    trash_dir = Path(trash_dir)

    def _log(msg: str) -> None:
        if on_log:
            on_log(msg)
        else:
            print(msg)

    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    if not trash_dir.is_dir():
        raise FileNotFoundError(f"Trash directory not found: {trash_dir}")

    if csv_path is None:
        csv_path = Path.cwd() / "deletion_verification_report.csv"
    csv_path = Path(csv_path)

    workers = _optimal_workers()
    _log(f"Using {workers} parallel workers")

    # ── Step 1: Collect source images ───────────────────────────────────
    _log(f"Scanning source directory: {source_dir}")
    source_images: list[Path] = []
    for root, _dirs, files in os.walk(source_dir):
        for fname in files:
            fpath = Path(root) / fname
            if _is_image(fpath):
                source_images.append(fpath)

    _log(f"  Found {len(source_images)} source images to hash")

    # ── Step 2: Hash source images (parallel) ───────────────────────────
    source_hashes: dict[str, list[Path]] = {}  # hash → [path, ...]
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_path = {
            executor.submit(pixel_hash, fpath): fpath
            for fpath in source_images
        }
        for future in concurrent.futures.as_completed(future_to_path):
            fpath = future_to_path[future]
            completed += 1
            if on_progress:
                on_progress(completed, len(source_images))
            if completed % 200 == 0 or completed == len(source_images):
                _log(f"  Hashing source: {completed}/{len(source_images)}...")
            try:
                h = future.result()
                source_hashes.setdefault(h, []).append(fpath)
            except Exception as exc:
                _log(f"  WARNING: Cannot hash source file {fpath}: {exc}")

    _log(f"  Hashed {len(source_images)} source images -> {len(source_hashes)} unique hashes")

    # ── Step 3: Collect trash images ────────────────────────────────────
    _log(f"Scanning trash directory: {trash_dir}")
    trash_images: list[Path] = []
    for root, _dirs, files in os.walk(trash_dir):
        for fname in files:
            fpath = Path(root) / fname
            if _is_image(fpath):
                trash_images.append(fpath)

    _log(f"  Found {len(trash_images)} trashed images to verify")

    # ── Step 4: Hash trash images and match (parallel) ──────────────────
    report = VerificationReport(csv_path=str(csv_path))
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_path = {
            executor.submit(pixel_hash, tpath): tpath
            for tpath in trash_images
        }
        for future in concurrent.futures.as_completed(future_to_path):
            trash_path = future_to_path[future]
            completed += 1
            if on_progress:
                on_progress(completed, len(trash_images))
            if completed % 100 == 0 or completed == len(trash_images):
                _log(f"  Verifying trash: {completed}/{len(trash_images)}...")

            try:
                h = future.result()
            except Exception as exc:
                report.errors.append({
                    "trash_file": str(trash_path),
                    "trash_size": trash_path.stat().st_size if trash_path.exists() else 0,
                    "error": str(exc),
                })
                _log(f"  ERROR: {trash_path.name}: {exc}")
                continue

            matches = source_hashes.get(h)
            if matches:
                match_path = matches[0]
                report.matched.append({
                    "trash_file": trash_path.name,
                    "trash_size": trash_path.stat().st_size,
                    "original_file": str(match_path),
                    "original_size": match_path.stat().st_size,
                })
            else:
                report.missing.append({
                    "trash_file": trash_path.name,
                    "trash_size": trash_path.stat().st_size,
                    "original_file": "",
                    "original_size": 0,
                })
                _log(f"  MISSING: {trash_path.name} — no matching original!")

    # ── Step 5: Write CSV report ────────────────────────────────────────
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Deleted File", "Deleted Size (bytes)", "Original File", "Original Size (bytes)"])

        for row in report.matched:
            writer.writerow([row["trash_file"], row["trash_size"], row["original_file"], row["original_size"]])

        for row in report.missing:
            writer.writerow([row["trash_file"], row["trash_size"], "*** NOT FOUND ***", ""])

        for row in report.errors:
            writer.writerow([row["trash_file"], row["trash_size"], f"ERROR: {row['error']}", ""])

    _log(f"CSV report written to: {csv_path}")
    return report


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

def _ask_directory(prompt: str, default: Path | None = None) -> Path:
    """Prompt the user for a directory path with optional default."""
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "

    while True:
        raw = input(display).strip()
        if not raw and default:
            return default
        p = Path(raw)
        if p.is_dir():
            return p
        print(f"  Directory not found: {p}")


def main() -> int:
    print("=" * 60)
    print("DejaView — Post-Cleanup Deletion Verifier")
    print("=" * 60)
    print()
    print("This tool verifies that every image moved to the DejaView")
    print("trash still has an identical copy in the source folder.")
    print()

    source_dir = _ask_directory("Source directory (where originals remain)")
    trash_dir = _ask_directory("Trash directory", default=DEFAULT_TRASH_ROOT)

    # CSV output path
    default_csv = Path.cwd() / "deletion_verification_report.csv"
    csv_input = input(f"CSV report path [{default_csv}]: ").strip()
    csv_path = Path(csv_input) if csv_input else default_csv

    print()
    report = verify_deletions(source_dir, trash_dir, csv_path)

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"  Total trashed images : {report.total_trash}")
    print(f"  Verified (matched)   : {len(report.matched)}")
    print(f"  MISSING (no match)   : {len(report.missing)}")
    print(f"  Errors (unhashable)  : {len(report.errors)}")
    print()

    if report.missing:
        print("MISSING FILES (no matching original found):")
        for row in report.missing:
            print(f"  - {row['trash_file']} ({row['trash_size']} bytes)")
        print()

    if report.errors:
        print("ERROR FILES (could not be hashed):")
        for row in report.errors:
            print(f"  - {row['trash_file']}: {row['error']}")
        print()

    if report.ok:
        print("RESULT: PASS — All trashed images have verified duplicates.")
        return 0
    else:
        print("RESULT: FAIL — Some trashed images could NOT be verified!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
