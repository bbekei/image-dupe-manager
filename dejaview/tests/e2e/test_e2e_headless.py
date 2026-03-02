"""
tests/e2e/test_e2e_headless.py — Headless end-to-end workflow tests.

Exercises the full Scan → Plan → Execute → Verify pipeline using core modules
directly.  No GUI, no built binary, no pywinauto.  Fast enough for CI.

Two categories:
  A. Full-pipeline tests — real images from e2e_dataset/ + Scanner QThread.
  B. Direct-insert tests — skip scanning, use DB inserts for speed.

Run with:
    cd dejaview
    python -m pytest tests/e2e/test_e2e_headless.py -m headless_e2e --no-cov -v

FEATURE_REQUEST_PLAN_E2E_TEST_SUITE.md — Tests H-01 through H-12.
"""

import os
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.executor import PlanExecutor
from core.selection import SelectionPreset, apply_preset
from core.trash import recover as trash_recover
from data.db import Database

from .conftest import (
    copy_e2e_images,
    get_manifest_corrupt_basenames,
    load_e2e_manifest,
    requires_e2e_images,
)

pytestmark = [pytest.mark.headless_e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_file(
    db: Database, session_id: int, path: str, size: int = 1000
) -> int:
    """Insert a file row and return its id."""
    return db.insert_file(session_id, path, size, _now(), _now())


def _set_pixel_hash(db: Database, file_id: int, pixel_hash: str) -> None:
    """Set pixel_hash on an existing file row (no thumbnail)."""
    db.update_pixel_hash(file_id, pixel_hash, "")


def _run_executor(db, session_id, trash_root):
    """Run PlanExecutor synchronously and return (success, errors) counts."""
    results = []
    error_list = []
    executor = PlanExecutor(db=db, session_id=session_id, trash_root=trash_root)
    executor.execution_complete.connect(lambda s, e: results.append((s, e)))
    executor.execution_error.connect(lambda p, m: error_list.append((p, m)))
    executor.run()
    return results[0] if results else (0, 0), error_list


# ═══════════════════════════════════════════════════════════════════════════
# A. Full-Pipeline Tests — real images from e2e_dataset/ + Scanner QThread
# ═══════════════════════════════════════════════════════════════════════════


@requires_e2e_images
class TestFullPipeline:
    """Tests that exercise the complete Scanner → Plan → Execute → Verify
    pipeline using real fixture images from tests/fixtures/e2e_dataset/."""

    @pytest.fixture
    def scan_env(self, db, thumb_dir, tmp_path, session_factory):
        """Set up a scan environment from the manifest."""
        manifest = load_e2e_manifest()
        scan_dir = copy_e2e_images(tmp_path, manifest)
        sid = session_factory()
        db.add_session_folder(sid, str(scan_dir))
        return db, sid, thumb_dir, scan_dir, manifest

    def _run_scan(self, qtbot, db, sid, thumb_dir):
        """Run the Scanner QThread and wait for completion."""
        from core.scanner import Scanner

        scanner = Scanner(db=db, session_id=sid, thumb_dir=thumb_dir)
        timeout_ms = 30_000
        with qtbot.waitSignal(scanner.scan_complete, timeout=timeout_ms):
            scanner.start()

    # ── H-01: scan → KEEP_LARGEST → execute → verify ─────────────────

    def test_h01_full_pipeline_keep_largest(
        self, qtbot, scan_env, tmp_path
    ):
        """H-01 — Full happy path: scan real images, apply KEEP_LARGEST_FILE,
        execute, verify DB and filesystem state."""
        db, sid, thumb_dir, scan_dir, manifest = scan_env
        self._run_scan(qtbot, db, sid, thumb_dir)

        # Validate duplicate groups detected match manifest
        expected_groups = manifest["statistics"]["exact_duplicate_groups"]
        groups = db.get_duplicate_groups(sid)
        assert len(groups) >= expected_groups, (
            f"Expected >= {expected_groups} duplicate groups, "
            f"got {len(groups)}"
        )

        # Apply preset
        keep_count, delete_count = apply_preset(
            db, sid, SelectionPreset.KEEP_LARGEST_FILE
        )
        assert keep_count > 0, "No files marked for keep"
        assert delete_count > 0, "No files marked for delete"

        # Verify plan summary before execution
        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == delete_count

        # Execute
        trash = tmp_path / "trash"
        (success, errors), _ = _run_executor(db, sid, trash)
        assert errors == 0, f"Execution had {errors} errors"
        assert success == delete_count

        # Verify filesystem: deleted files gone, kept files remain
        files = db.get_files_for_session(sid)
        for f in files:
            f_dict = dict(f)
            if f_dict["status"] == "deleted":
                assert not Path(f_dict["path"]).exists(), (
                    f"Deleted file still on disk: {f_dict['path']}"
                )
            elif f_dict["status"] == "active":
                assert Path(f_dict["path"]).exists(), (
                    f"Active file missing from disk: {f_dict['path']}"
                )

        # Verify DB: soft_deletes populated, plan summary zeroed
        soft_dels = db.get_active_soft_deletes(sid)
        assert len(soft_dels) == delete_count
        summary_after = db.get_plan_summary(sid)
        assert summary_after["delete_count"] == 0, "Pending deletes remain after execution"

    # ── H-02: scan → KEEP_NEWEST → execute → verify ──────────────────

    def test_h02_full_pipeline_keep_newest(
        self, qtbot, scan_env, tmp_path
    ):
        """H-02 — Date-based preset: set mtimes programmatically, apply
        KEEP_NEWEST, verify the newest file is kept."""
        db, sid, thumb_dir, scan_dir, manifest = scan_env

        # Set mtimes: make the first member in each group the "newest"
        for group_def in manifest.get("duplicate_groups", {}).values():
            members = group_def.get("members", [])
            for i, rel_path in enumerate(members):
                full_path = scan_dir / rel_path
                if full_path.exists():
                    # Newest = highest mtime; first member gets the highest
                    mtime = time.time() - (i * 3600)  # each subsequent is 1h older
                    os.utime(str(full_path), (mtime, mtime))

        self._run_scan(qtbot, db, sid, thumb_dir)

        keep_count, delete_count = apply_preset(
            db, sid, SelectionPreset.KEEP_NEWEST
        )
        assert keep_count > 0

        # Execute
        trash = tmp_path / "trash"
        (success, errors), _ = _run_executor(db, sid, trash)
        assert errors == 0

        # Verify: for each group, the first member (newest mtime) should be kept
        for group_def in manifest.get("duplicate_groups", {}).values():
            members = group_def.get("members", [])
            if len(members) < 2:
                continue
            newest_path = str(scan_dir / members[0])
            assert Path(newest_path).exists(), (
                f"Newest file '{members[0]}' should have been kept but was deleted"
            )

        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 0

    # ── H-07: scan multiple groups → verify all detected ─────────────

    def test_h07_full_pipeline_multiple_groups(
        self, qtbot, scan_env, tmp_path
    ):
        """H-07 — All manifest groups detected as distinct duplicate groups."""
        db, sid, thumb_dir, scan_dir, manifest = scan_env
        self._run_scan(qtbot, db, sid, thumb_dir)

        # Scanner finds groups by pixel_hash.  Scatter groups (100) plus
        # directory duplicates produce additional groups, so use >= for the
        # scatter-group lower bound.
        expected_min = manifest["statistics"]["exact_duplicate_groups"]
        groups = db.get_duplicate_groups(sid)
        assert len(groups) >= expected_min, (
            f"Expected >= {expected_min} groups, got {len(groups)}"
        )

        # Each scatter group should map to a distinct pixel_hash
        group_hashes = set()
        all_files = db.get_files_for_session(sid)
        files_by_path = {
            dict(f)["path"]: dict(f) for f in all_files
        }
        for group_def in manifest.get("duplicate_groups", {}).values():
            members = group_def.get("members", [])
            if len(members) < 2:
                continue
            first_path = str(scan_dir / members[0])
            f_row = files_by_path.get(first_path)
            if f_row and f_row["pixel_hash"]:
                group_hashes.add(f_row["pixel_hash"])

        assert len(group_hashes) >= expected_min, (
            f"Expected >= {expected_min} distinct hashes, "
            f"got {len(group_hashes)}"
        )

    # ── H-08: scan with corrupt files → graceful handling ────────────

    def test_h08_full_pipeline_corrupt_files(
        self, qtbot, scan_env
    ):
        """H-08 — Corrupt files don't crash the scanner; valid files are hashed."""
        db, sid, thumb_dir, scan_dir, manifest = scan_env
        self._run_scan(qtbot, db, sid, thumb_dir)

        all_files = db.get_files_for_session(sid)
        corrupt_names = get_manifest_corrupt_basenames(manifest)

        for f in all_files:
            f_dict = dict(f)
            basename = Path(f_dict["path"]).name
            if basename in corrupt_names:
                assert f_dict["pixel_hash"] is None, (
                    f"Corrupt file '{basename}' unexpectedly got a pixel_hash"
                )
            elif f_dict["size"] > 0:
                # Valid files that were size-duplicate candidates should be hashed
                # (non-candidate unique files may still have NULL pixel_hash)
                pass  # No assertion — depends on size duplication

        # Ensure at least some files were hashed successfully
        hashed = [dict(f) for f in all_files if dict(f)["pixel_hash"] is not None]
        assert len(hashed) > 0, "No files were hashed — possible scan failure"

    # ── H-11: scan completes within time boundary ─────────────────────

    def test_h11_scan_completes_within_timeout(
        self, qtbot, scan_env
    ):
        """H-11 — Performance regression guard: scan must complete within
        the manifest's scan_timeout_seconds (default 30s)."""
        db, sid, thumb_dir, scan_dir, manifest = scan_env

        timeout_s = 30  # default scan timeout for performance guard

        t0 = time.monotonic()
        self._run_scan(qtbot, db, sid, thumb_dir)
        elapsed = time.monotonic() - t0

        assert elapsed < timeout_s, (
            f"Scan took {elapsed:.1f}s, exceeding {timeout_s}s boundary"
        )

        # Verify all scannable files are in DB.
        # The scanner only processes JPEG/HEIC extensions, so exclude
        # .png / .bmp / etc. from the expected count.
        scannable_exts = {".jpg", ".jpeg", ".heic", ".heif"}
        expected_total = sum(
            1 for p in manifest["files"]
            if Path(p).suffix.lower() in scannable_exts
        )
        all_files = db.get_files_for_session(sid)
        assert len(all_files) >= expected_total, (
            f"Expected >= {expected_total} scannable files, "
            f"got {len(all_files)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# B. Direct-Insert Tests — skip scanning, use DB inserts for speed
# ═══════════════════════════════════════════════════════════════════════════


class TestDirectInsert:
    """Tests that skip scanning and insert file rows directly.
    Faster and more focused on planning + execution correctness."""

    HASH_A = "a" * 32  # 32-char hex = xxh128
    HASH_B = "b" * 32
    HASH_C = "c" * 32

    def _make_file(self, tmp_path: Path, name: str, content: bytes = b"data") -> Path:
        """Create a real file on disk and return its path."""
        f = tmp_path / "files" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(content)
        return f

    # ── H-03: manual keep/delete on individual files → execute ────────

    def test_h03_manual_keep_delete_decisions(
        self, db: Database, session_factory, tmp_path
    ):
        """H-03 — Per-file keep/delete decisions: 2 duplicate pairs, each
        with one keep and one delete. Verify correct files trashed."""
        sid = session_factory()
        trash = tmp_path / "trash"

        # Pair A: A1 (keep) + A2 (delete)
        a1 = self._make_file(tmp_path, "pair_a/img1.jpg")
        a2 = self._make_file(tmp_path, "pair_a/img2.jpg")
        fid_a1 = _insert_file(db, sid, str(a1), 1000)
        fid_a2 = _insert_file(db, sid, str(a2), 1000)
        _set_pixel_hash(db, fid_a1, self.HASH_A)
        _set_pixel_hash(db, fid_a2, self.HASH_A)

        # Pair B: B1 (delete) + B2 (keep)
        b1 = self._make_file(tmp_path, "pair_b/img1.jpg")
        b2 = self._make_file(tmp_path, "pair_b/img2.jpg")
        fid_b1 = _insert_file(db, sid, str(b1), 1000)
        fid_b2 = _insert_file(db, sid, str(b2), 1000)
        _set_pixel_hash(db, fid_b1, self.HASH_B)
        _set_pixel_hash(db, fid_b2, self.HASH_B)

        # Set decisions
        db.set_file_action(sid, fid_a1, "keep", decided_at=_now())
        db.set_file_action(sid, fid_a2, "delete", decided_at=_now())
        db.set_file_action(sid, fid_b1, "delete", decided_at=_now())
        db.set_file_action(sid, fid_b2, "keep", decided_at=_now())

        # Execute
        (success, errors), _ = _run_executor(db, sid, trash)
        assert success == 2
        assert errors == 0

        # Verify: kept files exist, deleted files gone
        assert a1.exists(), "A1 (keep) should still exist"
        assert not a2.exists(), "A2 (delete) should be gone"
        assert not b1.exists(), "B1 (delete) should be gone"
        assert b2.exists(), "B2 (keep) should still exist"

        # Verify DB: executed_at set for delete actions
        actions = db.get_file_actions_for_session(sid)
        for a in actions:
            a_dict = dict(a)
            if a_dict["action"] == "delete":
                assert a_dict["executed_at"] is not None

    # ── H-04: mixed keep + delete + ignore → execute ──────────────────

    def test_h04_mixed_decisions_ignore_untouched(
        self, db: Database, session_factory, tmp_path
    ):
        """H-04 — Ignore action leaves files untouched on disk and in DB.
        Only delete actions are executed."""
        sid = session_factory()
        trash = tmp_path / "trash"

        f_keep = self._make_file(tmp_path, "keep.jpg")
        f_delete = self._make_file(tmp_path, "delete.jpg")
        f_ignore = self._make_file(tmp_path, "ignore.jpg")

        fid_keep = _insert_file(db, sid, str(f_keep), 1000)
        fid_delete = _insert_file(db, sid, str(f_delete), 1000)
        fid_ignore = _insert_file(db, sid, str(f_ignore), 1000)

        _set_pixel_hash(db, fid_keep, self.HASH_A)
        _set_pixel_hash(db, fid_delete, self.HASH_A)
        _set_pixel_hash(db, fid_ignore, self.HASH_A)

        db.set_file_action(sid, fid_keep, "keep", decided_at=_now())
        db.set_file_action(sid, fid_delete, "delete", decided_at=_now())
        db.set_file_action(sid, fid_ignore, "ignore", decided_at=_now())

        (success, errors), _ = _run_executor(db, sid, trash)
        assert success == 1  # only the delete
        assert errors == 0

        # Filesystem
        assert f_keep.exists(), "Kept file should remain"
        assert not f_delete.exists(), "Deleted file should be gone"
        assert f_ignore.exists(), "Ignored file should remain untouched"

        # DB: ignored file still active, no executed_at
        file_ignore = db.get_file(fid_ignore)
        assert file_ignore["status"] == "active"
        action_ignore = db.conn.execute(
            "SELECT executed_at FROM file_actions WHERE session_id = ? AND file_id = ?",
            (sid, fid_ignore),
        ).fetchone()
        assert action_ignore["executed_at"] is None, (
            "Ignore action should NOT have executed_at set"
        )

    # ── H-05: master copy protection ─────────────────────────────────

    def test_h05_master_copy_protection(
        self, db: Database, session_factory, tmp_path
    ):
        """H-05 — apply_preset never marks ALL copies for deletion.
        At least one file in every group must be kept."""
        sid = session_factory()

        # 3 files in one group
        for i in range(3):
            f = self._make_file(tmp_path, f"img_{i}.jpg", content=b"x" * (100 + i))
            fid = _insert_file(db, sid, str(f), 100 + i)
            _set_pixel_hash(db, fid, self.HASH_A)

        keep_count, delete_count = apply_preset(
            db, sid, SelectionPreset.KEEP_LARGEST_FILE
        )

        assert keep_count == 1, "Exactly one file should be kept"
        assert delete_count == 2, "Two files should be marked for deletion"

        # Verify no "delete all" scenario
        actions = db.get_file_actions_for_session(sid)
        action_types = Counter(dict(a)["action"] for a in actions)
        assert action_types["keep"] >= 1, (
            "Master copy protection violated: no file marked as keep"
        )

    # ── H-06: two-file group — delete one → verify auto-keep ─────────

    def test_h06_two_file_auto_keep(
        self, db: Database, session_factory, tmp_path
    ):
        """H-06 — In a 2-file duplicate group, apply_preset produces
        exactly 1 keep + 1 delete."""
        sid = session_factory()
        trash = tmp_path / "trash"

        f1 = self._make_file(tmp_path, "big.jpg", content=b"x" * 2000)
        f2 = self._make_file(tmp_path, "small.jpg", content=b"x" * 500)
        fid1 = _insert_file(db, sid, str(f1), 2000)
        fid2 = _insert_file(db, sid, str(f2), 500)
        _set_pixel_hash(db, fid1, self.HASH_A)
        _set_pixel_hash(db, fid2, self.HASH_A)

        keep_count, delete_count = apply_preset(
            db, sid, SelectionPreset.KEEP_LARGEST_FILE
        )
        assert (keep_count, delete_count) == (1, 1)

        # The larger file (fid1) should be kept
        actions = {
            dict(a)["file_id"]: dict(a)["action"]
            for a in db.get_file_actions_for_session(sid)
        }
        assert actions[fid1] == "keep", "Larger file should be kept"
        assert actions[fid2] == "delete", "Smaller file should be deleted"

        # Execute and verify
        (success, errors), _ = _run_executor(db, sid, trash)
        assert success == 1
        assert f1.exists(), "Kept file should remain"
        assert not f2.exists(), "Deleted file should be gone"

    # ── H-09: soft_delete → recover → verify restored ────────────────

    def test_h09_soft_delete_and_recovery(
        self, db: Database, session_factory, tmp_path
    ):
        """H-09 — Delete a file, then recover it. File restored to
        original location."""
        sid = session_factory()
        trash = tmp_path / "trash"

        original = self._make_file(tmp_path, "precious.jpg", content=b"precious data")
        fid = _insert_file(db, sid, str(original), 13)
        _set_pixel_hash(db, fid, self.HASH_A)

        # Need a second file to form a duplicate group
        other = self._make_file(tmp_path, "other.jpg", content=b"precious data")
        fid_other = _insert_file(db, sid, str(other), 13)
        _set_pixel_hash(db, fid_other, self.HASH_A)

        db.set_file_action(sid, fid, "delete", decided_at=_now())
        db.set_file_action(sid, fid_other, "keep", decided_at=_now())

        # Execute: file moved to trash
        (success, errors), _ = _run_executor(db, sid, trash)
        assert success == 1
        assert not original.exists()

        # Get trash path from DB
        soft_dels = db.get_active_soft_deletes(sid)
        assert len(soft_dels) == 1
        trash_path = soft_dels[0]["trash_path"]
        original_path = soft_dels[0]["original_path"]
        assert Path(trash_path).exists(), "File should be in trash"

        # Recover
        trash_recover(trash_path, original_path)
        assert Path(original_path).exists(), "File should be restored"
        assert not Path(trash_path).exists(), "Trash file should be gone"

        # Verify content survived the round-trip
        assert Path(original_path).read_bytes() == b"precious data"

    # ── H-10: plan summary before and after execution ─────────────────

    def test_h10_plan_summary_before_and_after(
        self, db: Database, session_factory, tmp_path
    ):
        """H-10 — get_plan_summary() returns correct counts before and
        after execution."""
        sid = session_factory()
        trash = tmp_path / "trash"

        # Create 3 files in a group: 1 keep + 2 delete
        files = []
        for i in range(3):
            f = self._make_file(tmp_path, f"img_{i}.jpg")
            fid = _insert_file(db, sid, str(f), 1000 + i)
            _set_pixel_hash(db, fid, self.HASH_A)
            files.append((f, fid))

        apply_preset(db, sid, SelectionPreset.KEEP_LARGEST_FILE)

        # Before execution
        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 2
        assert summary["keep_count"] == 1

        # Execute
        _run_executor(db, sid, trash)

        # After execution — all executed, no pending deletes
        summary = db.get_plan_summary(sid)
        assert summary["delete_count"] == 0, (
            "Pending delete count should be 0 after execution"
        )

    # ── H-12: execution within time boundary ──────────────────────────

    def test_h12_execution_within_time_boundary(
        self, db: Database, session_factory, tmp_path
    ):
        """H-12 — Execute 50 file deletions within 10 seconds."""
        sid = session_factory()
        trash = tmp_path / "trash"

        # Create 50 files, all in one duplicate group
        for i in range(50):
            f = self._make_file(tmp_path, f"batch/img_{i:03d}.jpg")
            fid = _insert_file(db, sid, str(f), 1000)
            _set_pixel_hash(db, fid, self.HASH_A)
            if i == 0:
                db.set_file_action(sid, fid, "keep", decided_at=_now())
            else:
                db.set_file_action(sid, fid, "delete", decided_at=_now())

        t0 = time.monotonic()
        (success, errors), _ = _run_executor(db, sid, trash)
        elapsed = time.monotonic() - t0

        assert success == 49, f"Expected 49 successful deletes, got {success}"
        assert errors == 0
        assert elapsed < 10.0, (
            f"Execution took {elapsed:.1f}s, exceeding 10s boundary"
        )

        # Verify all deleted files are in trash
        soft_dels = db.get_active_soft_deletes(sid)
        assert len(soft_dels) == 49
