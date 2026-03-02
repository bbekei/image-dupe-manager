#!/usr/bin/env python3
"""
Generate comprehensive E2E test image set for DejaView.

Creates a realistic photo library with:
- 1000+ unique original images in 54 directories (max depth 8)
- 20 fully duplicate directories (2–5 total instances each)
- 100 scattered duplicate files (2–5 total instances each)
- 24 rotated images (8 each of 90°, 180°, 270°)
- 20 mirrored images (10 horizontal, 10 vertical)
- 5 corrupt files with image extensions
- 12 files with special characters in names
- JSON manifest mapping every file to its expected duplicate group

Usage:
    cd dejaview
    python tests/fixtures/make_e2e_fixtures.py

Source images: C:\\Users\\Public\\Pictures
Output:        tests/fixtures/images/e2e_dataset/
"""

import hashlib
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("ERROR: Pillow is required.  pip install Pillow")

# ── Configuration ──────────────────────────────────────────────────────────────

SEED = 42
random.seed(SEED)

SOURCE_DIR = Path(r"C:\Users\Public\Pictures")
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "images" / "e2e_dataset"
MANIFEST_PATH = SCRIPT_DIR / "e2e_manifest.json"

MAX_DIM = 640
JPEG_QUALITY = 85
NUM_ORIGINALS = 1000
NUM_DUP_DIRS = 20
NUM_SCATTERED_DUPES = 100
NUM_ROTATED = 24        # 8 × {90, 180, 270}
NUM_MIRRORED = 20       # 10 horizontal + 10 vertical
NUM_CORRUPT = 5
SOURCE_BUFFER = 200     # extra source images to guard against open failures

# ── Directory tree (54 leaf dirs, max depth 8) ─────────────────────────────────

ORIGINAL_LEAF_DIRS = [
    # ─── 2018 (24 dirs) ───
    "collection/2018/winter/january/snow/park/lake/dock",            # D8
    "collection/2018/winter/january/snow/park/trails",               # D7
    "collection/2018/winter/january/snow/cityscape",                 # D6
    "collection/2018/winter/january/portraits",                      # D5
    "collection/2018/winter/february/valentines",                    # D5
    "collection/2018/winter/march/blossoms",                         # D5
    "collection/2018/spring/april/flowers/tulips/red/closeup",       # D8
    "collection/2018/spring/april/flowers/roses",                    # D6
    "collection/2018/spring/april/wildlife",                         # D5
    "collection/2018/spring/may/picnic",                             # D5
    "collection/2018/spring/june/graduation",                        # D5
    "collection/2018/summer/july/beach/dunes/sunset/golden",         # D8
    "collection/2018/summer/july/beach/rocky",                       # D6
    "collection/2018/summer/july/pool",                              # D5
    "collection/2018/summer/august/camping/summit",                  # D6
    "collection/2018/summer/september/school",                       # D5
    "collection/2018/fall/october/foliage/maple/morning/path",       # D8
    "collection/2018/fall/october/foliage/oak",                      # D6
    "collection/2018/fall/october/halloween",                        # D5
    "collection/2018/fall/november/thanksgiving",                    # D5
    "collection/2018/fall/december/christmas",                       # D5
    "collection/2018/fall/december/new_years",                       # D5
    "collection/2018/misc/scanned",                                  # D4
    "collection/2018/misc/phone",                                    # D4
    # ─── 2019 (11 dirs) ───
    "collection/2019/spring/garden/herbs",                           # D5
    "collection/2019/spring/garden/vegetables",                      # D5
    "collection/2019/spring/outings/zoo",                            # D5
    "collection/2019/summer/travel/paris/eiffel/night/lights",       # D8
    "collection/2019/summer/travel/paris/louvre",                    # D6
    "collection/2019/summer/travel/lyon",                            # D5
    "collection/2019/summer/home/bbq",                               # D5
    "collection/2019/fall/school/soccer",                            # D5
    "collection/2019/fall/school/arts",                              # D5
    "collection/2019/winter/skiing/lodge",                           # D5
    "collection/2019/winter/holidays/gifts",                         # D5
    # ─── 2020 (7 dirs) ───
    "collection/2020/lockdown/home_office",                          # D4
    "collection/2020/lockdown/cooking",                              # D4
    "collection/2020/lockdown/garden",                               # D4
    "collection/2020/summer/hikes/forest/creek",                     # D6
    "collection/2020/summer/hikes/meadow",                           # D5
    "collection/2020/fall/colors/lake",                              # D5
    "collection/2020/winter/cozy/fireplace",                         # D5
    # ─── 2021 (7 dirs) ───
    "collection/2021/spring/park/cherry_blossoms",                   # D5
    "collection/2021/spring/riverbank",                              # D4
    "collection/2021/summer/road_trip/canyon/rim/overlook/dusk",     # D8
    "collection/2021/summer/road_trip/camp",                         # D5
    "collection/2021/summer/road_trip/coast/cliffs",                 # D6
    "collection/2021/fall/harvest_festival",                         # D4
    "collection/2021/winter/holidays/family",                        # D5
    # ─── 2022 (5 dirs) ───
    "collection/2022/spring/birds/wetland",                          # D5
    "collection/2022/spring/macro/insects",                          # D5
    "collection/2022/summer/beach_house/porch",                      # D5
    "collection/2022/fall/foggy_morning",                            # D4
    "collection/2022/winter/first_snow",                             # D4
]

# Windows-safe special-character filenames
SPECIAL_CHAR_NAMES = [
    "photo (summer vacation).jpg",
    "mom & dad at beach.jpg",
    "trip #1 — favorite.jpg",
    "best photo, ever!.jpg",
    "john's birthday.jpg",
    "photo [edited].jpg",
    "before + after.jpg",
    "café résumé.jpg",
    "naïve château.jpg",
    "señor piñata.jpg",
    "{holiday} ~memories~.jpg",
    "100% natural @home.jpg",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def collect_source_images(source_dir: Path, needed: int) -> list[Path]:
    """Walk *source_dir*, return up to *needed* validated image paths."""
    print(f"Scanning {source_dir} for source images ...")
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif"}
    candidates: list[Path] = []
    for root, _dirs, files in os.walk(source_dir):
        for f in files:
            if Path(f).suffix.lower() in exts:
                candidates.append(Path(root) / f)

    print(f"  Found {len(candidates)} candidates")
    random.shuffle(candidates)

    valid: list[Path] = []
    skipped = 0
    for p in candidates:
        if len(valid) >= needed:
            break
        try:
            with Image.open(p) as img:
                img.verify()
            valid.append(p)
        except Exception:
            skipped += 1
    print(f"  Validated {len(valid)} (skipped {skipped})")
    return valid


def resize_and_save(src: Path, dst: Path) -> int:
    """Open → EXIF-normalise → RGB → resize → JPEG.  Return file size."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img) or img
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_DIM:
            ratio = MAX_DIM / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        img.save(dst, "JPEG", quality=JPEG_QUALITY)
    return dst.stat().st_size


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Main ───────────────────────────────────────────────────────────────────────

def generate():
    t0 = time.time()

    if OUTPUT_DIR.exists():
        print(f"Removing existing {OUTPUT_DIR} ...")
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    manifest: dict = {
        "metadata": {
            "generated": datetime.now().isoformat(),
            "seed": SEED,
            "source_dir": str(SOURCE_DIR),
            "max_dimension": MAX_DIM,
            "jpeg_quality": JPEG_QUALITY,
        },
        "files": {},
        "duplicate_groups": {},          # exact byte-for-byte groups
        "directory_duplicates": {},      # directory-level groups
        "transform_groups": {},          # rotation / mirror
        "statistics": {},
    }

    # ── 1. Collect sources ─────────────────────────────────────────────────────
    needed = NUM_ORIGINALS + len(SPECIAL_CHAR_NAMES) + SOURCE_BUFFER
    sources = collect_source_images(SOURCE_DIR, needed)
    if len(sources) < NUM_ORIGINALS:
        sys.exit(f"Need {NUM_ORIGINALS} images, found only {len(sources)}")

    # ── 2. Distribute originals across tree ────────────────────────────────────
    n_dirs = len(ORIGINAL_LEAF_DIRS)
    print(f"\nDistributing {NUM_ORIGINALS} originals across {n_dirs} directories ...")

    # Per-directory counts with ±5 variation, min 8
    base = NUM_ORIGINALS // n_dirs
    counts = [max(8, base + random.randint(-5, 5)) for _ in range(n_dirs)]
    # Adjust total to exactly NUM_ORIGINALS
    while sum(counts) < NUM_ORIGINALS:
        counts[random.randint(0, n_dirs - 1)] += 1
    while sum(counts) > NUM_ORIGINALS:
        idx = random.randint(0, n_dirs - 1)
        if counts[idx] > 8:
            counts[idx] -= 1

    original_files: dict[int, str] = {}   # global_index → rel_path
    src_idx = 0
    file_idx = 0

    for dir_i, leaf in enumerate(ORIGINAL_LEAF_DIRS):
        target = counts[dir_i]
        placed = 0
        while placed < target and src_idx < len(sources):
            src = sources[src_idx]
            src_idx += 1
            fname = f"orig_{file_idx:04d}.jpg"
            rel = f"{leaf}/{fname}"
            dst = OUTPUT_DIR / rel
            try:
                sz = resize_and_save(src, dst)
            except Exception as exc:
                print(f"  skip {src.name}: {exc}")
                continue

            sha = file_sha256(dst)
            manifest["files"][rel] = {
                "size_bytes": sz,
                "sha256": sha,
                "category": "original",
                "duplicate_group": None,
                "transform": "none",
                "original_path": None,
                "is_corrupt": False,
            }
            original_files[file_idx] = rel
            file_idx += 1
            placed += 1

        if file_idx % 200 == 0 and file_idx > 0:
            print(f"  ... {file_idx} originals placed")

    print(f"  Total originals: {file_idx}")

    # ── 3. Select non-overlapping pools for duplication / transforms ────────────
    # 3a  Pick 20 dirs for full-directory duplication
    dup_dir_pool = random.sample(ORIGINAL_LEAF_DIRS, NUM_DUP_DIRS)
    dup_dir_set = set(dup_dir_pool)

    # 3b  Indices NOT in dup-dir pool → candidates for scatter / rot / mirror
    free_indices = [i for i, rel in original_files.items()
                    if not any(rel.startswith(d + "/") for d in dup_dir_set)]
    random.shuffle(free_indices)

    # Partition the free pool
    scatter_indices = free_indices[:NUM_SCATTERED_DUPES]
    rot_indices     = free_indices[NUM_SCATTERED_DUPES:
                                   NUM_SCATTERED_DUPES + NUM_ROTATED]
    mir_offset      = NUM_SCATTERED_DUPES + NUM_ROTATED
    mirror_indices  = free_indices[mir_offset:mir_offset + NUM_MIRRORED]

    if len(scatter_indices) < NUM_SCATTERED_DUPES:
        print(f"  WARNING: only {len(scatter_indices)} files for scatter duplication")
    if len(rot_indices) < NUM_ROTATED:
        print(f"  WARNING: only {len(rot_indices)} files for rotation")
    if len(mirror_indices) < NUM_MIRRORED:
        print(f"  WARNING: only {len(mirror_indices)} files for mirroring")

    # ── 4. Duplicate directories ───────────────────────────────────────────────
    print(f"\nCreating {NUM_DUP_DIRS} duplicate directories ...")

    for dg, orig_dir in enumerate(dup_dir_pool, start=1):
        total_instances = random.randint(2, 5)          # 2–5 total (incl. original)
        orig_abs = OUTPUT_DIR / orig_dir
        orig_files_list = sorted(orig_abs.glob("*.jpg"))
        if not orig_files_list:
            continue

        gid = f"dir_group_{dg:03d}"
        dup_paths: list[str] = []

        for cn in range(1, total_instances):             # copies 1..(total-1)
            dup_rel = (f"dup_dirs/dupdir_{dg:03d}_copy{cn}"
                       f"_of_{Path(orig_dir).name}")
            dup_abs = OUTPUT_DIR / dup_rel
            dup_abs.mkdir(parents=True, exist_ok=True)

            for of in orig_files_list:
                d = dup_abs / of.name
                shutil.copy2(of, d)
                r = f"{dup_rel}/{of.name}"
                manifest["files"][r] = {
                    "size_bytes": d.stat().st_size,
                    "sha256": file_sha256(d),
                    "category": "directory_duplicate",
                    "duplicate_group": gid,
                    "transform": "none",
                    "original_path": f"{orig_dir}/{of.name}",
                    "is_corrupt": False,
                }
            dup_paths.append(dup_rel)

        # Tag originals with same group
        for of in orig_files_list:
            key = f"{orig_dir}/{of.name}"
            if key in manifest["files"]:
                manifest["files"][key]["duplicate_group"] = gid

        manifest["directory_duplicates"][gid] = {
            "original_dir": orig_dir,
            "duplicate_dirs": dup_paths,
            "total_instances": total_instances,
            "files_per_dir": len(orig_files_list),
        }

    print(f"  Done ({len(manifest['directory_duplicates'])} groups)")

    # ── 5. Scattered duplicate files ───────────────────────────────────────────
    print(f"\nCreating {len(scatter_indices)} scattered duplicates ...")

    scatter_targets = [
        "duplicates/scattered/batch_01",
        "duplicates/scattered/batch_02",
        "duplicates/scattered/batch_03",
        "duplicates/scattered/batch_04",
        "duplicates/scattered/misc",
    ]

    for si, orig_i in enumerate(scatter_indices, start=1):
        rel_orig = original_files[orig_i]
        orig_abs = OUTPUT_DIR / rel_orig
        if not orig_abs.exists():
            continue

        total_instances = random.randint(2, 5)
        gid = f"scatter_group_{si:03d}"
        members = [rel_orig]

        # Tag original
        if rel_orig in manifest["files"]:
            manifest["files"][rel_orig]["duplicate_group"] = gid

        for cn in range(1, total_instances):
            tdir = random.choice(scatter_targets)
            fname = f"dup_of_{orig_i:04d}_copy{cn}.jpg"
            rel = f"{tdir}/{fname}"
            dst = OUTPUT_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(orig_abs, dst)

            manifest["files"][rel] = {
                "size_bytes": dst.stat().st_size,
                "sha256": file_sha256(dst),
                "category": "scattered_duplicate",
                "duplicate_group": gid,
                "transform": "none",
                "original_path": rel_orig,
                "is_corrupt": False,
            }
            members.append(rel)

        manifest["duplicate_groups"][gid] = {
            "type": "exact",
            "members": members,
            "original": rel_orig,
            "total_instances": total_instances,
        }

    print(f"  Done ({len(manifest['duplicate_groups'])} groups)")

    # ── 6. Rotated images ──────────────────────────────────────────────────────
    print(f"\nCreating {len(rot_indices)} rotated images ...")

    rot_dir = "transforms/rotated"
    (OUTPUT_DIR / rot_dir).mkdir(parents=True, exist_ok=True)
    rotations_cycle = [90, 180, 270]

    for ri, orig_i in enumerate(rot_indices):
        rel_orig = original_files[orig_i]
        orig_abs = OUTPUT_DIR / rel_orig
        degrees = rotations_cycle[ri % 3]
        fname = f"rot{degrees}_of_{orig_i:04d}.jpg"
        rel = f"{rot_dir}/{fname}"
        dst = OUTPUT_DIR / rel

        try:
            with Image.open(orig_abs) as img:
                rotated = img.rotate(degrees, expand=True)
                rotated.save(dst, "JPEG", quality=JPEG_QUALITY)
        except Exception as exc:
            print(f"  skip rotation of {orig_abs.name}: {exc}")
            continue

        gid = f"rot_group_{ri+1:03d}"
        manifest["files"][rel] = {
            "size_bytes": dst.stat().st_size,
            "sha256": file_sha256(dst),
            "category": "rotated",
            "duplicate_group": gid,
            "transform": f"rot{degrees}",
            "original_path": rel_orig,
            "is_corrupt": False,
        }
        manifest["transform_groups"][gid] = {
            "type": "rotation",
            "degrees": degrees,
            "original": rel_orig,
            "variant": rel,
        }

    print(f"  Done ({len([g for g in manifest['transform_groups'] if 'rot' in g])} rotations)")

    # ── 7. Mirrored images ─────────────────────────────────────────────────────
    print(f"\nCreating {len(mirror_indices)} mirrored images ...")

    mir_dir = "transforms/mirrored"
    (OUTPUT_DIR / mir_dir).mkdir(parents=True, exist_ok=True)

    for mi, orig_i in enumerate(mirror_indices):
        rel_orig = original_files[orig_i]
        orig_abs = OUTPUT_DIR / rel_orig
        direction = "horizontal" if mi < NUM_MIRRORED // 2 else "vertical"
        abbr = "h" if direction == "horizontal" else "v"
        fname = f"mirror_{abbr}_of_{orig_i:04d}.jpg"
        rel = f"{mir_dir}/{fname}"
        dst = OUTPUT_DIR / rel

        try:
            with Image.open(orig_abs) as img:
                flipped = (ImageOps.mirror(img) if direction == "horizontal"
                           else ImageOps.flip(img))
                flipped.save(dst, "JPEG", quality=JPEG_QUALITY)
        except Exception as exc:
            print(f"  skip mirror of {orig_abs.name}: {exc}")
            continue

        gid = f"mirror_group_{mi+1:03d}"
        manifest["files"][rel] = {
            "size_bytes": dst.stat().st_size,
            "sha256": file_sha256(dst),
            "category": "mirrored",
            "duplicate_group": gid,
            "transform": f"mirror_{abbr}",
            "original_path": rel_orig,
            "is_corrupt": False,
        }
        manifest["transform_groups"][gid] = {
            "type": "mirror",
            "direction": direction,
            "original": rel_orig,
            "variant": rel,
        }

    print(f"  Done ({len([g for g in manifest['transform_groups'] if 'mirror' in g])} mirrors)")

    # ── 8. Corrupt files ───────────────────────────────────────────────────────
    print(f"\nCreating {NUM_CORRUPT} corrupt files ...")

    corrupt_dir_path = OUTPUT_DIR / "corrupt"
    corrupt_dir_path.mkdir(parents=True, exist_ok=True)

    corrupt_specs = [
        ("corrupt_truncated.jpg",
         b"\xff\xd8\xff\xe0" + b"\x00" * 100,
         "Truncated JPEG: SOI + partial APP0"),
        ("corrupt_empty.png",
         b"",
         "Zero-byte PNG"),
        ("corrupt_wrong_header.jpg",
         b"This is not a JPEG file at all" + b"\x00" * 50,
         "Plain text masquerading as JPEG"),
        ("corrupt_partial_png.png",
         b"\x89PNG\r\n\x1a\n" + b"\x00" * 50,
         "PNG magic + truncated header"),
        ("corrupt_random_bytes.bmp",
         bytes(random.randint(0, 255) for _ in range(200)),
         "Random bytes with .bmp extension"),
    ]

    for fname, content, description in corrupt_specs:
        rel = f"corrupt/{fname}"
        (OUTPUT_DIR / rel).write_bytes(content)
        manifest["files"][rel] = {
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "category": "corrupt",
            "duplicate_group": None,
            "transform": "none",
            "original_path": None,
            "is_corrupt": True,
            "corruption_description": description,
        }

    print(f"  Done")

    # ── 9. Special-character filenames ─────────────────────────────────────────
    print(f"\nCreating {len(SPECIAL_CHAR_NAMES)} special-character files ...")

    special_dir = "special_chars"
    (OUTPUT_DIR / special_dir).mkdir(parents=True, exist_ok=True)

    # Use fresh source images (not from originals pool) so these are unique
    special_src_start = src_idx  # pick up where originals left off
    for i, sname in enumerate(SPECIAL_CHAR_NAMES):
        si = special_src_start + i
        if si >= len(sources):
            print(f"  WARNING: out of source images for special chars")
            break
        src = sources[si]
        rel = f"{special_dir}/{sname}"
        dst = OUTPUT_DIR / rel
        try:
            sz = resize_and_save(src, dst)
        except Exception as exc:
            print(f"  skip {sname}: {exc}")
            continue

        manifest["files"][rel] = {
            "size_bytes": sz,
            "sha256": file_sha256(dst),
            "category": "special_chars",
            "duplicate_group": None,
            "transform": "none",
            "original_path": None,
            "is_corrupt": False,
        }

    print(f"  Done")

    # ── 10. Statistics & manifest ──────────────────────────────────────────────
    print("\nComputing statistics ...")

    leaf_dirs = {str(Path(r).parent) for r in manifest["files"]}
    all_dirs: set[str] = set()
    for d in leaf_dirs:
        parts = Path(d).parts
        for depth in range(1, len(parts) + 1):
            all_dirs.add(str(Path(*parts[:depth])))

    max_depth = max((len(Path(d).parts) for d in leaf_dirs), default=0)

    by_cat: dict[str, int] = {}
    for info in manifest["files"].values():
        c = info["category"]
        by_cat[c] = by_cat.get(c, 0) + 1

    manifest["statistics"] = {
        "total_files": len(manifest["files"]),
        "leaf_directories": len(leaf_dirs),
        "all_directories": len(all_dirs),
        "max_directory_depth": max_depth,
        "files_by_category": by_cat,
        "exact_duplicate_groups": len(manifest["duplicate_groups"]),
        "directory_duplicate_groups": len(manifest["directory_duplicates"]),
        "transform_groups": len(manifest["transform_groups"]),
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"E2E test set generated in {elapsed:.1f}s")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"{'=' * 60}")
    for k, v in manifest["statistics"].items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    generate()
