"""
tests/unit/test_trash.py — Tests for core/trash.py soft-delete module.
"""

import time
from pathlib import Path

import pytest

from core.trash import purge_expired, recover, soft_delete


class TestSoftDelete:
    """Tests for soft_delete()."""

    def test_moves_file_to_trash(self, tmp_path):
        src = tmp_path / "photos" / "img.jpg"
        src.parent.mkdir()
        src.write_bytes(b"JPEG data")

        trash_root = tmp_path / ".dejaview_trash"
        trash_path = soft_delete(str(src), str(trash_root), session_id=42)

        assert not src.exists(), "Source file should be gone"
        assert Path(trash_path).exists(), "File should exist in trash"
        assert Path(trash_path).read_bytes() == b"JPEG data"

    def test_creates_session_subfolder(self, tmp_path):
        src = tmp_path / "a.jpg"
        src.write_bytes(b"x")
        trash_root = tmp_path / ".dejaview_trash"

        trash_path = soft_delete(str(src), str(trash_root), session_id=7)

        # Trash path should be under trash_root/7/
        assert str(trash_root / "7") in trash_path

    def test_raises_on_missing_file(self, tmp_path):
        trash_root = tmp_path / ".dejaview_trash"
        with pytest.raises(FileNotFoundError):
            soft_delete(str(tmp_path / "nonexistent.jpg"), str(trash_root), 1)

    def test_handles_name_collision(self, tmp_path):
        """If the flattened name already exists in trash, append a counter."""
        src1 = tmp_path / "img.jpg"
        src1.write_bytes(b"first")
        trash_root = tmp_path / ".dejaview_trash"
        path1 = soft_delete(str(src1), str(trash_root), session_id=1)

        # Create the same source file again
        src2 = tmp_path / "img.jpg"
        src2.write_bytes(b"second")
        path2 = soft_delete(str(src2), str(trash_root), session_id=1)

        assert path1 != path2
        assert Path(path1).read_bytes() == b"first"
        assert Path(path2).read_bytes() == b"second"


class TestRecover:
    """Tests for recover()."""

    def test_restores_file(self, tmp_path):
        src = tmp_path / "photos" / "img.jpg"
        src.parent.mkdir()
        src.write_bytes(b"precious data")
        trash_root = tmp_path / ".dejaview_trash"

        trash_path = soft_delete(str(src), str(trash_root), session_id=1)
        assert not src.exists()

        recover(trash_path, str(src))
        assert src.exists()
        assert src.read_bytes() == b"precious data"
        assert not Path(trash_path).exists()

    def test_raises_on_missing_trash_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            recover(
                str(tmp_path / "nonexistent"),
                str(tmp_path / "restore.jpg"),
            )

    def test_raises_on_existing_target(self, tmp_path):
        src = tmp_path / "img.jpg"
        src.write_bytes(b"data")
        trash_root = tmp_path / ".dejaview_trash"

        trash_path = soft_delete(str(src), str(trash_root), session_id=1)

        # Create a different file at the original path
        src.write_bytes(b"new data")

        with pytest.raises(FileExistsError):
            recover(trash_path, str(src))

    def test_creates_parent_directories(self, tmp_path):
        src = tmp_path / "deep" / "nested" / "img.jpg"
        src.parent.mkdir(parents=True)
        src.write_bytes(b"data")
        trash_root = tmp_path / ".dejaview_trash"

        trash_path = soft_delete(str(src), str(trash_root), session_id=1)

        # Remove the parent directories
        (tmp_path / "deep" / "nested").rmdir()
        (tmp_path / "deep").rmdir()

        recover(trash_path, str(src))
        assert src.exists()


class TestPurgeExpired:
    """Tests for purge_expired()."""

    def test_empty_trash_returns_empty(self, tmp_path):
        trash_root = tmp_path / ".dejaview_trash"
        assert purge_expired(str(trash_root)) == []

    def test_nonexistent_root_returns_empty(self, tmp_path):
        assert purge_expired(str(tmp_path / "nope")) == []

    def test_purges_old_files(self, tmp_path):
        trash_root = tmp_path / ".dejaview_trash"
        session_dir = trash_root / "1"
        session_dir.mkdir(parents=True)

        old_file = session_dir / "old.jpg"
        old_file.write_bytes(b"old")

        # Set mtime to 60 days ago
        old_mtime = time.time() - (60 * 86400)
        import os
        os.utime(str(old_file), (old_mtime, old_mtime))

        purged = purge_expired(str(trash_root), max_age_days=30)
        assert len(purged) == 1
        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        trash_root = tmp_path / ".dejaview_trash"
        session_dir = trash_root / "1"
        session_dir.mkdir(parents=True)

        recent_file = session_dir / "recent.jpg"
        recent_file.write_bytes(b"recent")
        # mtime is now — should not be purged

        purged = purge_expired(str(trash_root), max_age_days=30)
        assert len(purged) == 0
        assert recent_file.exists()

    def test_removes_empty_session_dirs(self, tmp_path):
        trash_root = tmp_path / ".dejaview_trash"
        session_dir = trash_root / "1"
        session_dir.mkdir(parents=True)

        old_file = session_dir / "old.jpg"
        old_file.write_bytes(b"old")
        old_mtime = time.time() - (60 * 86400)
        import os
        os.utime(str(old_file), (old_mtime, old_mtime))

        purge_expired(str(trash_root), max_age_days=30)
        assert not session_dir.exists(), "Empty session dir should be removed"
