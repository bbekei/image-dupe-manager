"""
data/db.py — SQLite abstraction layer for DejaView.

Module ownership rules (from plan):
- All raw SQL lives here; no business logic.
- No disk operations (no os.remove, no file I/O).
- All external data goes through ? parameterized queries — no exceptions.

Database stored at %APPDATA%\\DejaView\\library.db (caller supplies path).
WAL mode is enabled on open for concurrent UI reads during scan writes.
"""

import re
import sqlite3
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Validation helper (plan §Security — pixel_hash format enforcement)
# ---------------------------------------------------------------------------

_HASH_RE = re.compile(r'^[0-9a-f]{64}$')


def validate_pixel_hash(value: str) -> bool:
    """Return True iff value is a 64-char lowercase hex string."""
    return isinstance(value, str) and bool(_HASH_RE.match(value))


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    name        TEXT,
    created_at  TEXT,
    status      TEXT DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'paused', 'complete', 'stopped'))
);

CREATE TABLE IF NOT EXISTS session_folders (
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    folder_path TEXT    NOT NULL,
    PRIMARY KEY (session_id, folder_path)
);

CREATE TABLE IF NOT EXISTS files (
    id             INTEGER PRIMARY KEY,
    session_id     INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    path           TEXT    NOT NULL,
    size           INTEGER,
    modified_at    TEXT,
    pixel_hash     TEXT,
    thumbnail_path TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'deleted', 'renamed')),
    scanned_at     TEXT,
    UNIQUE (session_id, path)
);

CREATE TABLE IF NOT EXISTS sync_config (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    local_username   TEXT NOT NULL,
    gdrive_folder_id TEXT,
    gdrive_file_id   TEXT,
    sync_enabled     INTEGER NOT NULL DEFAULT 0,
    export_privacy   TEXT    NOT NULL DEFAULT 'filename'
        CHECK (export_privacy IN ('hash_only', 'filename', 'full_path')),
    pending_export   INTEGER NOT NULL DEFAULT 0,
    last_exported_at TEXT,
    last_imported_at TEXT,
    scan_delay_ms    INTEGER NOT NULL DEFAULT 0
        CHECK (scan_delay_ms >= 0 AND scan_delay_ms <= 20)
);

CREATE TABLE IF NOT EXISTS remote_peers (
    id           INTEGER PRIMARY KEY,
    username     TEXT UNIQUE NOT NULL,
    last_seen_at TEXT,
    file_mtime   TEXT
);

CREATE TABLE IF NOT EXISTS remote_files (
    id          INTEGER PRIMARY KEY,
    peer_id     INTEGER NOT NULL REFERENCES remote_peers(id) ON DELETE CASCADE,
    remote_id   TEXT,
    filename    TEXT,
    path        TEXT,
    size        INTEGER,
    modified_at TEXT,
    pixel_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_config (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    language TEXT NOT NULL DEFAULT 'auto',
    theme    TEXT NOT NULL DEFAULT 'system'
);

CREATE VIEW IF NOT EXISTS duplicate_groups AS
    SELECT session_id, pixel_hash, COUNT(*) AS file_count
    FROM files
    WHERE pixel_hash IS NOT NULL AND status = 'active'
    GROUP BY session_id, pixel_hash
    HAVING COUNT(*) > 1;

CREATE INDEX IF NOT EXISTS idx_files_session    ON files(session_id);
CREATE INDEX IF NOT EXISTS idx_files_hash       ON files(pixel_hash);
CREATE INDEX IF NOT EXISTS idx_files_path       ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_status     ON files(status);
CREATE INDEX IF NOT EXISTS idx_remote_files_hash ON remote_files(pixel_hash);
"""


class Database:
    """Thin wrapper around a SQLite connection with the DejaView schema."""

    def __init__(self, db_path: str | Path):
        self._path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the database and apply DDL."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Apply DDL statements one by one (executescript commits implicitly,
        # but we need WAL set before anything else runs).
        self._conn.executescript(_DDL)

    def close(self) -> None:
        """Commit any pending work and close the connection."""
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not open — call open() first")
        return self._conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, name: str, created_at: str) -> int:
        """Insert a new scan session and return its id."""
        cur = self.conn.execute(
            "INSERT INTO sessions (name, created_at, status) VALUES (?, ?, 'in_progress')",
            (name, created_at),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_session_status(self, session_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (status, session_id),
        )
        self.conn.commit()

    def get_session(self, session_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

    def get_latest_session(self) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def delete_session(self, session_id: int) -> None:
        """Delete a session; ON DELETE CASCADE removes child rows."""
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Session folders
    # ------------------------------------------------------------------

    def add_session_folder(self, session_id: int, folder_path: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO session_folders (session_id, folder_path) VALUES (?, ?)",
            (session_id, folder_path),
        )
        self.conn.commit()

    def remove_session_folder(self, session_id: int, folder_path: str) -> None:
        self.conn.execute(
            "DELETE FROM session_folders WHERE session_id = ? AND folder_path = ?",
            (session_id, folder_path),
        )
        self.conn.commit()

    def get_session_folders(self, session_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT folder_path FROM session_folders WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return [r["folder_path"] for r in rows]

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def insert_file(
        self,
        session_id: int,
        path: str,
        size: int,
        modified_at: str,
        scanned_at: str,
    ) -> int:
        """Insert a file row (Pass 1). Uses INSERT OR IGNORE to be idempotent."""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO files
                (session_id, path, size, modified_at, scanned_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, path, size, modified_at, scanned_at),
        )
        self.conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        # Row already existed — fetch its id
        row = self.conn.execute(
            "SELECT id FROM files WHERE session_id = ? AND path = ?",
            (session_id, path),
        ).fetchone()
        return row["id"]

    def insert_files_batch(self, rows: list[tuple]) -> None:
        """
        Bulk-insert up to 100 file rows per transaction (plan §Resource Usage —
        database write batching during Pass 1).

        Each element of rows: (session_id, path, size, modified_at, scanned_at)
        """
        sql = """
            INSERT OR IGNORE INTO files
                (session_id, path, size, modified_at, scanned_at)
            VALUES (?, ?, ?, ?, ?)
        """
        for i in range(0, len(rows), 100):
            batch = rows[i : i + 100]
            self.conn.executemany(sql, batch)
            self.conn.commit()

    def update_pixel_hash(
        self, file_id: int, pixel_hash: str, thumbnail_path: str
    ) -> None:
        """Write pixel_hash and thumbnail_path after Pass-2 hashing."""
        self.conn.execute(
            "UPDATE files SET pixel_hash = ?, thumbnail_path = ? WHERE id = ?",
            (pixel_hash, thumbnail_path, file_id),
        )
        self.conn.commit()

    def get_file(self, file_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ).fetchone()

    def get_files_for_session(self, session_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM files WHERE session_id = ?", (session_id,)
        ).fetchall()

    def get_unhashed_files_grouped_by_size(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """
        Return files whose size appears at least twice in this session and whose
        pixel_hash is still NULL — these are the Pass-2 candidates.
        """
        return self.conn.execute(
            """
            SELECT f.*
            FROM files f
            WHERE f.session_id = ?
              AND f.pixel_hash IS NULL
              AND f.size IN (
                  SELECT size FROM files
                  WHERE session_id = ? AND size IS NOT NULL
                  GROUP BY size HAVING COUNT(*) > 1
              )
            ORDER BY f.size, f.id
            """,
            (session_id, session_id),
        ).fetchall()

    def get_folder_file_counts(
        self, session_id: int, folder_prefix: str
    ) -> tuple[int, int]:
        """Return (total_files, hashed_files) under *folder_prefix* for the session."""
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(pixel_hash) AS hashed
            FROM files
            WHERE session_id = ? AND path LIKE ? || '%' AND status = 'active'
            """,
            (session_id, folder_prefix),
        ).fetchone()
        return (row["total"], row["hashed"])

    def get_duplicate_groups(self, session_id: int) -> list[sqlite3.Row]:
        """Return all (pixel_hash, file_count) rows from the view for a session."""
        return self.conn.execute(
            "SELECT * FROM duplicate_groups WHERE session_id = ?", (session_id,)
        ).fetchall()

    def get_files_by_pixel_hash(
        self, session_id: int, pixel_hash: str
    ) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM files
            WHERE session_id = ? AND pixel_hash = ? AND status = 'active'
            """,
            (session_id, pixel_hash),
        ).fetchall()

    def update_file_status(self, file_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE files SET status = ? WHERE id = ?", (status, file_id)
        )
        self.conn.commit()

    def update_file_path(self, file_id: int, new_path: str) -> None:
        self.conn.execute(
            "UPDATE files SET path = ? WHERE id = ?", (new_path, file_id)
        )
        self.conn.commit()

    def deactivate_files_under_folder(
        self, session_id: int, folder_path: str
    ) -> None:
        """
        Mark all files whose path starts with folder_path as 'deleted'
        when a folder is removed from scan scope (plan §Post-Action Cleanup).
        """
        prefix = folder_path.rstrip("/\\") + "/"
        # Also match the folder itself if path == folder_path exactly
        self.conn.execute(
            """
            UPDATE files SET status = 'deleted'
            WHERE session_id = ?
              AND (path = ? OR path LIKE ? ESCAPE '\\')
            """,
            (session_id, folder_path, _like_escape(prefix) + "%"),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Sync config (singleton row, id=1)
    # ------------------------------------------------------------------

    def upsert_sync_config(self, **fields) -> None:
        """
        Insert or update the sync_config singleton.
        fields: any subset of sync_config columns (except id).

        If the row already exists, only the supplied fields are updated.
        If the row does not exist, an INSERT is attempted (caller must supply
        at least local_username to satisfy the NOT NULL constraint).
        """
        allowed = {
            "local_username", "gdrive_folder_id", "gdrive_file_id",
            "sync_enabled", "export_privacy", "pending_export",
            "last_exported_at", "last_imported_at", "scan_delay_ms",
        }
        safe = {k: v for k, v in fields.items() if k in allowed}
        if not safe:
            return

        existing = self.conn.execute(
            "SELECT 1 FROM sync_config WHERE id = 1"
        ).fetchone()

        if existing:
            # UPDATE only the supplied columns
            set_clause = ", ".join(f"{k} = ?" for k in safe)
            self.conn.execute(
                f"UPDATE sync_config SET {set_clause} WHERE id = 1",
                list(safe.values()),
            )
        else:
            # INSERT — caller must supply local_username
            cols = ", ".join(safe.keys())
            placeholders = ", ".join("?" for _ in safe)
            self.conn.execute(
                f"INSERT INTO sync_config (id, {cols}) VALUES (1, {placeholders})",
                list(safe.values()),
            )
        self.conn.commit()

    def get_sync_config(self) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM sync_config WHERE id = 1"
        ).fetchone()

    def get_scan_delay_ms(self) -> int:
        """Return the configured inter-file scan delay (0 if unconfigured)."""
        row = self.get_sync_config()
        return int(row["scan_delay_ms"]) if row else 0

    # ------------------------------------------------------------------
    # App config (singleton row, id=1)
    # ------------------------------------------------------------------

    def get_app_config(self) -> Optional[sqlite3.Row]:
        """Return the app_config singleton row, or None if not yet created."""
        return self.conn.execute(
            "SELECT * FROM app_config WHERE id = 1"
        ).fetchone()

    def upsert_app_config(self, **fields) -> None:
        """Insert or update the app_config singleton with the given fields."""
        allowed = {"language", "theme"}
        safe = {k: v for k, v in fields.items() if k in allowed}
        if not safe:
            return

        existing = self.conn.execute(
            "SELECT 1 FROM app_config WHERE id = 1"
        ).fetchone()

        if existing:
            set_clause = ", ".join(f"{k} = ?" for k in safe)
            self.conn.execute(
                f"UPDATE app_config SET {set_clause} WHERE id = 1",
                list(safe.values()),
            )
        else:
            cols = ", ".join(safe.keys())
            placeholders = ", ".join("?" for _ in safe)
            self.conn.execute(
                f"INSERT INTO app_config (id, {cols}) VALUES (1, {placeholders})",
                list(safe.values()),
            )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Remote peers
    # ------------------------------------------------------------------

    def upsert_remote_peer(
        self, username: str, last_seen_at: str, file_mtime: Optional[str] = None
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO remote_peers (username, last_seen_at, file_mtime)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                file_mtime   = excluded.file_mtime
            """,
            (username, last_seen_at, file_mtime),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM remote_peers WHERE username = ?", (username,)
        ).fetchone()
        return row["id"]

    def get_remote_peer(self, username: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM remote_peers WHERE username = ?", (username,)
        ).fetchone()

    def delete_remote_peer(self, username: str) -> None:
        """Delete peer; ON DELETE CASCADE removes their remote_files."""
        self.conn.execute(
            "DELETE FROM remote_peers WHERE username = ?", (username,)
        )
        self.conn.commit()

    def get_all_remote_peers(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM remote_peers").fetchall()

    # ------------------------------------------------------------------
    # Remote files
    # ------------------------------------------------------------------

    def insert_remote_files(
        self, peer_id: int, entries: list[dict]
    ) -> None:
        """
        Bulk-insert remote file entries for a peer.
        Each dict must contain 'pixel_hash'; other fields optional.
        pixel_hash must already be validated by the caller.
        """
        sql = """
            INSERT INTO remote_files
                (peer_id, remote_id, filename, path, size, modified_at, pixel_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                peer_id,
                e.get("remote_id"),
                e.get("filename"),
                e.get("path"),
                e.get("size"),
                e.get("modified_at"),
                e["pixel_hash"],
            )
            for e in entries
        ]
        self.conn.executemany(sql, rows)
        self.conn.commit()

    def delete_remote_files_for_peer(self, peer_id: int) -> None:
        self.conn.execute(
            "DELETE FROM remote_files WHERE peer_id = ?", (peer_id,)
        )
        self.conn.commit()

    def get_cross_library_matches(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """
        Return local files that match a remote peer's pixel_hash.
        Plan §Database Schema — cross-library JOIN query.
        """
        return self.conn.execute(
            """
            SELECT f.id          AS local_file_id,
                   f.path        AS local_path,
                   f.size        AS local_size,
                   f.modified_at AS local_modified_at,
                   f.pixel_hash,
                   rf.filename   AS remote_filename,
                   rf.path       AS remote_path,
                   rf.size       AS remote_size,
                   rf.modified_at AS remote_modified_at,
                   rp.username
            FROM files f
            JOIN remote_files rf ON rf.pixel_hash = f.pixel_hash
            JOIN remote_peers rp ON rp.id = rf.peer_id
            WHERE f.session_id = ? AND f.status = 'active'
            """,
            (session_id,),
        ).fetchall()

    # ------------------------------------------------------------------
    # Thumbnail cleanup (plan §Post-Action Cleanup)
    # ------------------------------------------------------------------

    def cleanup_orphaned_thumbnails(self) -> list[str]:
        """
        Return thumbnail_path values that are no longer referenced by any
        active file.  Caller is responsible for os.remove() — db.py does no
        disk I/O (plan module ownership rule).
        """
        rows = self.conn.execute(
            """
            SELECT DISTINCT thumbnail_path
            FROM files
            WHERE thumbnail_path IS NOT NULL
              AND pixel_hash NOT IN (
                  SELECT pixel_hash FROM files WHERE status = 'active'
              )
            """
        ).fetchall()
        return [r["thumbnail_path"] for r in rows]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _like_escape(s: str) -> str:
    """Escape special LIKE characters in s (%, _, \\) for use as a LIKE pattern."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
