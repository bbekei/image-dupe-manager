"""
tests/fixtures/realistic_corpus.py — Generate a realistic 500+ file test corpus.

Phase 1, Week 2: Realistic fixture set.

Creates a directory tree with:
- 500+ JPEG/HEIC-extension files across 20+ folders
- Non-ASCII folder AND file names (Hungarian, Japanese, Korean, Spanish)
- Duplicate groups (same content, different names/locations)
- Unique files (no duplicates)
- Various image sizes (simulating cameras, phones, screenshots)
- Nested subdirectories (3 levels deep)

This module provides a pytest fixture (realistic_corpus) that generates the
corpus in tmp_path.  It is NOT committed to VCS — generated on each test run.

Plan guardrail: Fixture sets must include at least one non-ASCII path AND
non-ASCII filename, and one corpus above 500 images.
"""

from pathlib import Path

from PIL import Image


def _jpg(path: Path, color: tuple, size: tuple = (64, 64)) -> Path:
    """Create a deterministic JPEG at path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(str(path), "JPEG", quality=95, subsampling=0)
    img.close()
    return path


def _png(path: Path, color: tuple, size: tuple = (64, 64)) -> Path:
    """Create a deterministic PNG at path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(str(path), "PNG")
    img.close()
    return path


def generate_corpus(root: Path) -> dict:
    """
    Generate a realistic 500+ file corpus under root.

    Returns a dict with metadata:
        {
            "total_files": int,
            "duplicate_groups": int,
            "unique_files": int,
            "non_ascii_folders": list[str],
            "non_ascii_files": list[str],
            "folders": list[str],
        }
    """
    files_created = []
    duplicate_groups = 0

    # ── Folder structure with non-ASCII names ────────────────────────────
    folders = {
        # ASCII folders
        "Vacation 2024": None,
        "Vacation 2024/Beach": None,
        "Vacation 2024/Mountains": None,
        "Work/Screenshots": None,
        "Work/Presentations": None,
        "Family/Christmas": None,
        "Family/Birthday": None,
        "Misc": None,
        "Downloads/Camera Upload": None,
        "Backup/Old Phone": None,
        # Non-ASCII folders (Hungarian)
        "Családi fotók": None,
        "Családi fotók/Karácsony": None,
        "Családi fotók/Nyaralás": None,
        "Emlékek/Régi képek": None,
        # Non-ASCII folders (Japanese)
        "写真/旅行": None,
        "写真/家族": None,
        # Non-ASCII folders (Korean)
        "사진 모음/여행": None,
        # Non-ASCII folders (Spanish)
        "Fotos de Ñoño": None,
        # Deep nesting
        "Archive/2023/Q1/January": None,
        "Archive/2023/Q1/February": None,
        "Archive/2023/Q2/April": None,
    }

    for folder in folders:
        (root / folder).mkdir(parents=True, exist_ok=True)

    folder_list = list(folders.keys())
    non_ascii_folders = [f for f in folder_list if any(ord(c) > 127 for c in f)]

    # ── Duplicate groups: same color = same pixel hash ───────────────────
    # 30 groups × 8 copies = 240 duplicate files
    dup_colors = [
        (i * 8 % 256, (i * 13 + 50) % 256, (i * 17 + 100) % 256)
        for i in range(30)
    ]

    non_ascii_files = []
    file_idx = 0

    for group_idx, color in enumerate(dup_colors):
        duplicate_groups += 1
        # Spread copies across different folders
        for copy_idx in range(8):
            folder = folder_list[file_idx % len(folder_list)]
            # Mix ASCII and non-ASCII filenames
            if copy_idx == 0:
                name = f"IMG_{group_idx:04d}_eredeti.jpg"  # Hungarian: "original"
                non_ascii_files.append(name)
            elif copy_idx == 1:
                name = f"写真_{group_idx:04d}.jpg"  # Japanese
                non_ascii_files.append(name)
            elif copy_idx == 2:
                name = f"사진_{group_idx:04d}.jpg"  # Korean
                non_ascii_files.append(name)
            else:
                name = f"IMG_{group_idx:04d}_copy{copy_idx}.jpg"

            path = _jpg(root / folder / name, color=color)
            files_created.append(path)
            file_idx += 1

    # ── Unique files: different sizes = unique file size ──────────────────
    # 280 unique files across folders
    sizes = [
        (64, 64), (128, 128), (256, 256), (32, 32),
        (100, 75), (200, 150), (320, 240), (160, 120),
        (48, 48), (80, 60),
    ]

    for i in range(280):
        folder = folder_list[i % len(folder_list)]
        size = sizes[i % len(sizes)]
        color = ((i * 3) % 256, (i * 7 + 20) % 256, (i * 11 + 40) % 256)

        # Make size unique by varying dimensions slightly
        unique_size = (size[0] + i // 10, size[1] + i // 10)

        if i % 15 == 0:
            name = f"képek_{i:04d}.jpg"
            non_ascii_files.append(name)
        elif i % 20 == 0:
            # Use .jpeg extension for variety (scanner supports .jpg and .jpeg)
            name = f"screenshot_{i:04d}.jpeg"
        else:
            name = f"photo_{i:04d}.jpg"

        path = _jpg(root / folder / name, color=color, size=unique_size)
        files_created.append(path)
        file_idx += 1

    return {
        "total_files": len(files_created),
        "duplicate_groups": duplicate_groups,
        "unique_files": len(files_created) - duplicate_groups * 8,
        "non_ascii_folders": non_ascii_folders,
        "non_ascii_files": list(set(non_ascii_files)),
        "folders": folder_list,
        "root": root,
    }
