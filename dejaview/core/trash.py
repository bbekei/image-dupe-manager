"""
core/trash.py — Soft-delete infrastructure for DejaView.

Moves files to a `.dejaview_trash/{session_id}/` directory instead of
permanently deleting them.  Files are recoverable for 30 days.

This is the ONLY module that performs destructive filesystem operations
(moves, deletes).  All other code delegates file operations here.
"""

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def soft_delete(
    file_path: str | Path,
    trash_root: str | Path,
    session_id: int,
) -> str:
    """Move a file to the soft-delete trash directory.

    Args:
        file_path:   Absolute path to the file to soft-delete.
        trash_root:  Root of the trash tree (e.g. ``~/.dejaview_trash``).
        session_id:  Current session id (used as subfolder name).

    Returns:
        The absolute path where the file was moved to (trash_path).

    Raises:
        FileNotFoundError: If the source file does not exist.
        OSError: If the move operation fails.
    """
    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")

    # Build destination: trash_root / session_id / flattened_path
    # Flatten the original path to avoid nested directory creation issues.
    # Replace path separators and colon (drive letter) with underscores.
    flat_name = str(src).replace(":", "_").replace("\\", "_").replace("/", "_")
    dest_dir = Path(trash_root) / str(session_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / flat_name

    # Handle name collisions (unlikely but safe)
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(src), str(dest))
    log.info("Soft-deleted %s → %s", src, dest)
    return str(dest)


def recover(trash_path: str | Path, original_path: str | Path) -> None:
    """Restore a soft-deleted file to its original location.

    Args:
        trash_path:    Path inside the trash directory.
        original_path: The original filesystem path to restore to.

    Raises:
        FileNotFoundError: If the trash file does not exist.
        FileExistsError: If a file already exists at the original path.
        OSError: If the move operation fails.
    """
    src = Path(trash_path)
    dest = Path(original_path)

    if not src.exists():
        raise FileNotFoundError(f"Trash file not found: {src}")
    if dest.exists():
        raise FileExistsError(
            f"Cannot recover — file already exists at: {dest}"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    log.info("Recovered %s → %s", src, dest)


def purge_expired(
    trash_root: str | Path,
    max_age_days: int = 30,
) -> list[str]:
    """Permanently delete trash files older than max_age_days.

    Args:
        trash_root:   Root of the trash directory tree.
        max_age_days: Files older than this are purged (default 30).

    Returns:
        List of paths that were permanently deleted.
    """
    root = Path(trash_root)
    if not root.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    purged: list[str] = []

    for session_dir in root.iterdir():
        if not session_dir.is_dir():
            continue

        for trash_file in session_dir.iterdir():
            if not trash_file.is_file():
                continue

            # Use file modification time as the deletion timestamp
            mtime = datetime.fromtimestamp(
                trash_file.stat().st_mtime, tz=timezone.utc
            )
            if mtime < cutoff:
                try:
                    trash_file.unlink()
                    purged.append(str(trash_file))
                    log.info("Purged expired trash: %s", trash_file)
                except OSError as exc:
                    log.warning("Failed to purge %s: %s", trash_file, exc)

        # Remove empty session directories
        try:
            if session_dir.is_dir() and not any(session_dir.iterdir()):
                session_dir.rmdir()
        except OSError:
            pass

    return purged
