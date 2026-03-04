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

_HASH_RE = re.compile(r'^[0-9a-f]{32}(?:[0-9a-f]{32})?$')


def validate_pixel_hash(value: str) -> bool:
    """Return True iff value is a 32-char (xxh128) or 64-char (sha256) lowercase hex string."""
    return isinstance(value, str) and bool(_HASH_RE.match(value))


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-8000;
PRAGMA mmap_size=268435456;
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
    hash_algorithm TEXT NOT NULL DEFAULT 'xxh128'
        CHECK (hash_algorithm IN ('sha256', 'xxh128')),
    thumbnail_path TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'deleted', 'renamed')),
    scanned_at     TEXT,
    UNIQUE (session_id, path)
);

CREATE TABLE IF NOT EXISTS sync_config (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    local_username      TEXT NOT NULL,
    gdrive_folder_id    TEXT,
    gdrive_file_id      TEXT,
    sync_enabled        INTEGER NOT NULL DEFAULT 0,
    export_privacy      TEXT    NOT NULL DEFAULT 'filename'
        CHECK (export_privacy IN ('hash_only', 'filename', 'full_path')),
    pending_export      INTEGER NOT NULL DEFAULT 0,
    last_exported_at    TEXT,
    last_imported_at    TEXT,
    scan_delay_ms       INTEGER NOT NULL DEFAULT 0
        CHECK (scan_delay_ms >= 0 AND scan_delay_ms <= 20),
    last_upload_sha256  TEXT
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
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    language         TEXT    NOT NULL DEFAULT 'auto',
    theme            TEXT    NOT NULL DEFAULT 'system',
    max_scan_workers INTEGER NOT NULL DEFAULT 0
        CHECK (max_scan_workers >= 0 AND max_scan_workers <= 32),
    perf_logging     INTEGER NOT NULL DEFAULT 0
);

CREATE VIEW IF NOT EXISTS duplicate_groups AS
    SELECT session_id, pixel_hash, hash_algorithm, COUNT(*) AS file_count
    FROM files
    WHERE pixel_hash IS NOT NULL AND status = 'active'
    GROUP BY session_id, pixel_hash, hash_algorithm
    HAVING COUNT(*) > 1;

CREATE INDEX IF NOT EXISTS idx_files_session    ON files(session_id);
CREATE INDEX IF NOT EXISTS idx_files_hash       ON files(pixel_hash);
CREATE INDEX IF NOT EXISTS idx_files_path       ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_status     ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_session_hash_status
    ON files(session_id, pixel_hash, status);
CREATE INDEX IF NOT EXISTS idx_remote_files_hash ON remote_files(pixel_hash);

CREATE TABLE IF NOT EXISTS file_actions (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    action      TEXT NOT NULL
        CHECK (action IN ('keep', 'delete', 'ignore')),
    scope       TEXT NOT NULL DEFAULT 'file'
        CHECK (scope IN ('file', 'folder')),
    decided_at  TEXT,
    executed_at TEXT,
    UNIQUE (session_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_file_actions_session ON file_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_file_actions_file    ON file_actions(file_id);

CREATE TABLE IF NOT EXISTS soft_deletes (
    id            INTEGER PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES sessions(id),
    file_id       INTEGER NOT NULL REFERENCES files(id),
    original_path TEXT NOT NULL,
    trash_path    TEXT NOT NULL,
    deleted_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    recovered_at  TEXT,
    UNIQUE (session_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_soft_deletes_session ON soft_deletes(session_id);

CREATE TABLE IF NOT EXISTS requests (
    id           INTEGER PRIMARY KEY,
    session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    pixel_hash   TEXT NOT NULL,
    target_peer  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','denied','fulfilled','cancelled')),
    requested_at TEXT NOT NULL,
    responded_at TEXT,
    fulfilled_at TEXT,
    UNIQUE (session_id, pixel_hash, target_peer)
);

CREATE INDEX IF NOT EXISTS idx_requests_session ON requests(session_id);
CREATE INDEX IF NOT EXISTS idx_requests_status  ON requests(status);
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
        self._migrate()

    def _migrate(self) -> None:
        """Apply incremental schema migrations for existing databases."""
        c = self.conn
        # R3: add hash_algorithm column to files (existing rows default to sha256)
        cols = {r[1] for r in c.execute("PRAGMA table_info(files)").fetchall()}
        if "hash_algorithm" not in cols:
            c.execute(
                "ALTER TABLE files ADD COLUMN hash_algorithm TEXT NOT NULL DEFAULT 'sha256'"
            )
            # Recreate the view so it includes hash_algorithm in GROUP BY
            c.execute("DROP VIEW IF EXISTS duplicate_groups")
            c.execute(
                """
                CREATE VIEW duplicate_groups AS
                    SELECT session_id, pixel_hash, hash_algorithm,
                           COUNT(*) AS file_count
                    FROM files
                    WHERE pixel_hash IS NOT NULL AND status = 'active'
                    GROUP BY session_id, pixel_hash, hash_algorithm
                    HAVING COUNT(*) > 1
                """
            )
            c.commit()

        # R3: add max_scan_workers column to app_config
        cols = {r[1] for r in c.execute("PRAGMA table_info(app_config)").fetchall()}
        if "max_scan_workers" not in cols:
            c.execute(
                "ALTER TABLE app_config ADD COLUMN max_scan_workers"
                " INTEGER NOT NULL DEFAULT 0"
            )
            c.commit()

        # Telemetry: add perf_logging column to app_config
        cols = {r[1] for r in c.execute("PRAGMA table_info(app_config)").fetchall()}
        if "perf_logging" not in cols:
            c.execute(
                "ALTER TABLE app_config ADD COLUMN perf_logging"
                " INTEGER NOT NULL DEFAULT 0"
            )
            c.commit()

        # Pluggable Views: add file_actions table
        tables = {
            r[0]
            for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "file_actions" not in tables:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS file_actions (
                    id          INTEGER PRIMARY KEY,
                    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                    action      TEXT NOT NULL
                        CHECK (action IN ('keep', 'delete', 'ignore')),
                    scope       TEXT NOT NULL DEFAULT 'file'
                        CHECK (scope IN ('file', 'folder')),
                    decided_at  TEXT,
                    executed_at TEXT,
                    UNIQUE (session_id, file_id)
                );
                CREATE INDEX IF NOT EXISTS idx_file_actions_session
                    ON file_actions(session_id);
                CREATE INDEX IF NOT EXISTS idx_file_actions_file
                    ON file_actions(file_id);
                """
            )

        # UX Redesign Phase 2: add soft_deletes table
        if "soft_deletes" not in tables:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS soft_deletes (
                    id            INTEGER PRIMARY KEY,
                    session_id    INTEGER NOT NULL REFERENCES sessions(id),
                    file_id       INTEGER NOT NULL REFERENCES files(id),
                    original_path TEXT NOT NULL,
                    trash_path    TEXT NOT NULL,
                    deleted_at    TEXT NOT NULL,
                    expires_at    TEXT NOT NULL,
                    recovered_at  TEXT,
                    UNIQUE (session_id, file_id)
                );
                CREATE INDEX IF NOT EXISTS idx_soft_deletes_session
                    ON soft_deletes(session_id);
                """
            )

        # UX Redesign Phase 4: add requests table
        if "requests" not in tables:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    id           INTEGER PRIMARY KEY,
                    session_id   INTEGER NOT NULL REFERENCES sessions(id)
                                     ON DELETE CASCADE,
                    pixel_hash   TEXT NOT NULL,
                    target_peer  TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN (
                            'pending','approved','denied','fulfilled','cancelled'
                        )),
                    requested_at TEXT NOT NULL,
                    responded_at TEXT,
                    fulfilled_at TEXT,
                    UNIQUE (session_id, pixel_hash, target_peer)
                );
                CREATE INDEX IF NOT EXISTS idx_requests_session
                    ON requests(session_id);
                CREATE INDEX IF NOT EXISTS idx_requests_status
                    ON requests(status);
                """
            )

        # Similar Image Detection: add perceptual_hash, width, height to files
        cols = {r[1] for r in c.execute("PRAGMA table_info(files)").fetchall()}
        if "perceptual_hash" not in cols:
            c.execute("ALTER TABLE files ADD COLUMN perceptual_hash TEXT")
            c.execute("ALTER TABLE files ADD COLUMN width INTEGER")
            c.execute("ALTER TABLE files ADD COLUMN height INTEGER")
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_phash "
                "ON files(perceptual_hash)"
            )
            c.commit()

        # Similar Image Detection: add similarity_enabled to sessions
        session_cols = {
            r[1] for r in c.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "similarity_enabled" not in session_cols:
            c.execute(
                "ALTER TABLE sessions ADD COLUMN similarity_enabled "
                "INTEGER NOT NULL DEFAULT 0"
            )
            c.commit()

        # Similar Image Detection: add similarity_groups + members tables
        tables = {
            r[0]
            for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "similarity_groups" not in tables:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS similarity_groups (
                    id                     INTEGER PRIMARY KEY,
                    session_id             INTEGER NOT NULL
                        REFERENCES sessions(id) ON DELETE CASCADE,
                    created_at             TEXT NOT NULL,
                    status                 TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'reviewed', 'actioned')),
                    member_count           INTEGER NOT NULL DEFAULT 0,
                    representative_file_id INTEGER
                        REFERENCES files(id)
                );
                CREATE INDEX IF NOT EXISTS idx_simgroups_session
                    ON similarity_groups(session_id);

                CREATE TABLE IF NOT EXISTS similarity_group_members (
                    id        INTEGER PRIMARY KEY,
                    group_id  INTEGER NOT NULL
                        REFERENCES similarity_groups(id) ON DELETE CASCADE,
                    file_id   INTEGER NOT NULL
                        REFERENCES files(id) ON DELETE CASCADE,
                    distance  INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (group_id, file_id)
                );
                CREATE INDEX IF NOT EXISTS idx_simgroupmembers_group
                    ON similarity_group_members(group_id);
                CREATE INDEX IF NOT EXISTS idx_simgroupmembers_file
                    ON similarity_group_members(file_id);
                """
            )

        # Data Compression: add last_upload_sha256 to sync_config
        sync_cols = {
            r[1] for r in c.execute("PRAGMA table_info(sync_config)").fetchall()
        }
        if "last_upload_sha256" not in sync_cols:
            c.execute(
                "ALTER TABLE sync_config ADD COLUMN last_upload_sha256 TEXT"
            )
            c.commit()

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
        algo = "xxh128" if len(pixel_hash) == 32 else "sha256"
        self.conn.execute(
            "UPDATE files SET pixel_hash = ?, hash_algorithm = ?, thumbnail_path = ? WHERE id = ?",
            (pixel_hash, algo, thumbnail_path, file_id),
        )
        self.conn.commit()

    def update_pixel_hashes_batch(
        self, updates: list[tuple[int, str, str]]
    ) -> None:
        """Write pixel_hash and thumbnail_path for multiple files in one transaction.

        Each element of updates: (file_id, pixel_hash, thumbnail_path).
        """
        self.conn.executemany(
            "UPDATE files SET pixel_hash = ?, hash_algorithm = ?, thumbnail_path = ? WHERE id = ?",
            [
                (h, "xxh128" if len(h) == 32 else "sha256", t, fid)
                for fid, h, t in updates
            ],
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

    def get_all_duplicate_file_ids(
        self, session_id: int
    ) -> dict[str, list[int]]:
        """Return ``{pixel_hash: [file_id, ...]}`` for every duplicate group.

        One query replaces N sequential ``get_files_by_pixel_hash()`` calls.
        Singleton hashes (unique files) are excluded.
        """
        rows = self.conn.execute(
            """
            SELECT f.id, f.pixel_hash
            FROM files f
            WHERE f.session_id = ? AND f.pixel_hash IS NOT NULL
              AND f.status = 'active'
              AND f.pixel_hash IN (
                  SELECT pixel_hash FROM duplicate_groups
                  WHERE session_id = ?
              )
            ORDER BY f.pixel_hash
            """,
            (session_id, session_id),
        ).fetchall()
        groups: dict[str, list[int]] = {}
        for r in rows:
            groups.setdefault(r["pixel_hash"], []).append(r["id"])
        return groups

    # ------------------------------------------------------------------
    # Filtered duplicate queries (UX Redesign Phase 5 — Advanced Cleanup)
    # ------------------------------------------------------------------

    def _build_dup_group_clauses(
        self,
        session_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        extensions: Optional[list[str]] = None,
        min_copies: int = 2,
    ) -> tuple[str, list]:
        """Build WHERE clause and params for duplicate group queries.

        Returns:
            (where_sql, params) — params includes the HAVING threshold as
            the last element.
        """
        clauses = [
            "session_id = ?",
            "status = 'active'",
            "pixel_hash IS NOT NULL",
        ]
        params: list = [session_id]

        if date_from:
            clauses.append("modified_at >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("modified_at <= ?")
            params.append(date_to)
        if extensions:
            ext_conditions = []
            for ext in extensions:
                ext_lower = ext.lower()
                ext_conditions.append("LOWER(path) LIKE ?")
                params.append(f"%{ext_lower}")
            clauses.append(f"({' OR '.join(ext_conditions)})")

        where = " AND ".join(clauses)
        params.append(max(min_copies, 2))
        return where, params

    def get_duplicate_group_count(
        self,
        session_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        extensions: Optional[list[str]] = None,
        min_copies: int = 2,
    ) -> int:
        """Return the total number of duplicate groups matching the filters."""
        where, params = self._build_dup_group_clauses(
            session_id, date_from, date_to, extensions, min_copies,
        )
        sql = f"""
            SELECT COUNT(*) FROM (
                SELECT pixel_hash
                FROM files
                WHERE {where}
                GROUP BY pixel_hash
                HAVING COUNT(*) >= ?
            )
        """
        row = self.conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    def get_filtered_duplicate_groups(
        self,
        session_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        extensions: Optional[list[str]] = None,
        min_copies: int = 2,
        sort_by: str = "waste",
        sort_desc: bool = True,
        limit: int = 0,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """Return duplicate groups with optional filtering, sorting, and pagination.

        Args:
            session_id: Active session.
            date_from: ISO8601 lower bound on files.modified_at (inclusive).
            date_to: ISO8601 upper bound on files.modified_at (inclusive).
            extensions: List of lowercase extensions including dot (e.g. ['.jpg']).
            min_copies: Minimum file count per group (default 2).
            sort_by: 'waste' | 'copies' | 'path_length'.
            sort_desc: Descending sort (default True).
            limit: Maximum groups to return (0 = no limit).
            offset: Number of groups to skip (used with limit).

        Returns:
            Rows with: pixel_hash, file_count, total_size, oldest_date, newest_date.
        """
        where, params = self._build_dup_group_clauses(
            session_id, date_from, date_to, extensions, min_copies,
        )

        order_map = {
            "waste": "total_size",
            "copies": "file_count",
            "path_length": "min_path_len",
        }
        order_col = order_map.get(sort_by, "total_size")
        direction = "DESC" if sort_desc else "ASC"

        sql = f"""
            SELECT pixel_hash,
                   COUNT(*)        AS file_count,
                   SUM(size)       AS total_size,
                   MIN(modified_at) AS oldest_date,
                   MAX(modified_at) AS newest_date,
                   MIN(LENGTH(path)) AS min_path_len
            FROM files
            WHERE {where}
            GROUP BY pixel_hash
            HAVING COUNT(*) >= ?
            ORDER BY {order_col} {direction}
        """
        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        return self.conn.execute(sql, params).fetchall()

    def get_cluster_files(
        self, session_id: int, pixel_hash: str
    ) -> list[sqlite3.Row]:
        """Return all active files for a single pixel_hash cluster.

        Returns rows with: id, path, size, modified_at, thumbnail_path.
        """
        return self.conn.execute(
            """
            SELECT id, path, size, modified_at, thumbnail_path
            FROM files
            WHERE session_id = ? AND pixel_hash = ? AND status = 'active'
            ORDER BY size DESC, modified_at DESC
            """,
            (session_id, pixel_hash),
        ).fetchall()

    def get_full_dupe_folder_paths(self, session_id: int) -> set[str]:
        """Return folder paths where every file is a duplicate.

        A folder qualifies when ALL of its files have a pixel_hash that
        appears in at least one other file in the session.
        """
        dup_hashes = {
            r["pixel_hash"]
            for r in self.conn.execute(
                """
                SELECT pixel_hash FROM files
                WHERE session_id = ? AND status = 'active'
                      AND pixel_hash IS NOT NULL
                GROUP BY pixel_hash HAVING COUNT(*) > 1
                """,
                (session_id,),
            ).fetchall()
        }
        if not dup_hashes:
            return set()

        rows = self.conn.execute(
            """
            SELECT path, pixel_hash FROM files
            WHERE session_id = ? AND status = 'active'
                  AND pixel_hash IS NOT NULL
            """,
            (session_id,),
        ).fetchall()

        # Group files by parent folder, count total and duplicate
        from collections import defaultdict

        folder_total: dict[str, int] = defaultdict(int)
        folder_dup: dict[str, int] = defaultdict(int)
        for r in rows:
            folder = str(Path(r["path"]).parent)
            folder_total[folder] += 1
            if r["pixel_hash"] in dup_hashes:
                folder_dup[folder] += 1

        return {
            f for f, total in folder_total.items()
            if total > 0 and folder_dup.get(f, 0) == total
        }

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
            "last_upload_sha256",
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

    def get_max_scan_workers(self) -> int:
        """Return the configured max worker count (0 = auto-detect)."""
        row = self.get_app_config()
        if row is None:
            return 0
        try:
            return int(row["max_scan_workers"])
        except (KeyError, TypeError):
            return 0

    def get_perf_logging(self) -> bool:
        """Return True if performance telemetry is enabled in settings."""
        row = self.get_app_config()
        if row is None:
            return False
        try:
            return bool(row["perf_logging"])
        except (KeyError, TypeError):
            return False

    def upsert_app_config(self, **fields) -> None:
        """Insert or update the app_config singleton with the given fields."""
        allowed = {"language", "theme", "max_scan_workers", "perf_logging"}
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

    def get_family_treasure_count(self, session_id: int) -> int:
        """Return count of remote hashes that do NOT exist locally.

        These are the 'Family Treasures' — photos that family members have
        but the current user does not.
        """
        row = self.conn.execute(
            """
            SELECT COUNT(DISTINCT rf.pixel_hash) AS cnt
            FROM remote_files rf
            WHERE rf.pixel_hash NOT IN (
                SELECT pixel_hash FROM files
                WHERE session_id = ? AND status = 'active'
                      AND pixel_hash IS NOT NULL
            )
            """,
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # File actions (Pluggable Views — action planning)
    # ------------------------------------------------------------------

    def set_file_action(
        self,
        session_id: int,
        file_id: int,
        action: str,
        scope: str = "file",
        decided_at: Optional[str] = None,
    ) -> None:
        """Record a keep/delete/ignore decision for a single file."""
        self.conn.execute(
            """
            INSERT INTO file_actions (session_id, file_id, action, scope, decided_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, file_id) DO UPDATE SET
                action     = excluded.action,
                scope      = excluded.scope,
                decided_at = excluded.decided_at
            """,
            (session_id, file_id, action, scope, decided_at),
        )
        self.conn.commit()

    def set_file_actions_batch(
        self, rows: list[tuple[int, int, str, str, Optional[str]]]
    ) -> None:
        """Bulk-insert action decisions.

        Each tuple: (session_id, file_id, action, scope, decided_at).
        """
        self.conn.executemany(
            """
            INSERT INTO file_actions (session_id, file_id, action, scope, decided_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, file_id) DO UPDATE SET
                action     = excluded.action,
                scope      = excluded.scope,
                decided_at = excluded.decided_at
            """,
            rows,
        )
        self.conn.commit()

    def get_file_actions_for_session(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return all action rows for a session."""
        return self.conn.execute(
            "SELECT * FROM file_actions WHERE session_id = ?",
            (session_id,),
        ).fetchall()

    def get_decided_file_ids(self, session_id: int) -> set[int]:
        """Return the set of file_ids that have a decision in this session."""
        rows = self.conn.execute(
            "SELECT file_id FROM file_actions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return {r["file_id"] for r in rows}

    def clear_file_action(self, session_id: int, file_id: int) -> None:
        """Remove a single file's action decision (undo)."""
        self.conn.execute(
            "DELETE FROM file_actions WHERE session_id = ? AND file_id = ?",
            (session_id, file_id),
        )
        self.conn.commit()

    def clear_all_actions(self, session_id: int) -> None:
        """Remove all action decisions for a session (reset plan)."""
        self.conn.execute(
            "DELETE FROM file_actions WHERE session_id = ?",
            (session_id,),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Soft deletes (UX Redesign Phase 2 — nondestructive file removal)
    # ------------------------------------------------------------------

    def record_soft_delete(
        self,
        session_id: int,
        file_id: int,
        original_path: str,
        trash_path: str,
        deleted_at: str,
        expires_at: str,
    ) -> int:
        """Record a soft-deleted file in the database."""
        cur = self.conn.execute(
            """
            INSERT INTO soft_deletes
                (session_id, file_id, original_path, trash_path, deleted_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, file_id) DO UPDATE SET
                trash_path = excluded.trash_path,
                deleted_at = excluded.deleted_at,
                expires_at = excluded.expires_at,
                recovered_at = NULL
            """,
            (session_id, file_id, original_path, trash_path, deleted_at, expires_at),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def record_recovery(self, soft_delete_id: int, recovered_at: str) -> None:
        """Mark a soft-deleted file as recovered."""
        self.conn.execute(
            "UPDATE soft_deletes SET recovered_at = ? WHERE id = ?",
            (recovered_at, soft_delete_id),
        )
        self.conn.commit()

    def get_active_soft_deletes(self, session_id: int) -> list[sqlite3.Row]:
        """Return soft-deleted files that have NOT been recovered."""
        return self.conn.execute(
            """
            SELECT * FROM soft_deletes
            WHERE session_id = ? AND recovered_at IS NULL
            ORDER BY deleted_at DESC
            """,
            (session_id,),
        ).fetchall()

    def get_expired_soft_deletes(self, cutoff_iso: str) -> list[sqlite3.Row]:
        """Return soft-deleted files whose expires_at is before cutoff_iso."""
        return self.conn.execute(
            """
            SELECT * FROM soft_deletes
            WHERE recovered_at IS NULL AND expires_at < ?
            """,
            (cutoff_iso,),
        ).fetchall()

    # ------------------------------------------------------------------
    # Plan summary (UX Redesign Phase 2 — Plan Review impact totals)
    # ------------------------------------------------------------------

    def get_plan_summary(self, session_id: int) -> dict:
        """Return impact totals for the current plan.

        Returns:
            dict with keys: delete_count, delete_bytes, keep_count,
            ignore_count, folder_delete_count.
        """
        row = self.conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN fa.action = 'delete' THEN 1 ELSE 0 END), 0)
                    AS delete_count,
                COALESCE(SUM(CASE WHEN fa.action = 'delete' THEN f.size ELSE 0 END), 0)
                    AS delete_bytes,
                COALESCE(SUM(CASE WHEN fa.action = 'keep' THEN 1 ELSE 0 END), 0)
                    AS keep_count,
                COALESCE(SUM(CASE WHEN fa.action = 'ignore' THEN 1 ELSE 0 END), 0)
                    AS ignore_count,
                COALESCE(SUM(CASE WHEN fa.action = 'delete' AND fa.scope = 'folder'
                             THEN 1 ELSE 0 END), 0)
                    AS folder_delete_count
            FROM file_actions fa
            JOIN files f ON f.id = fa.file_id
            WHERE fa.session_id = ? AND fa.executed_at IS NULL
            """,
            (session_id,),
        ).fetchone()
        return {
            "delete_count": row["delete_count"],
            "delete_bytes": row["delete_bytes"],
            "keep_count": row["keep_count"],
            "ignore_count": row["ignore_count"],
            "folder_delete_count": row["folder_delete_count"],
        }

    def get_delete_actions_with_paths(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return file details for all pending delete actions in a session.

        Each row includes: file_id, path, size, pixel_hash, scope, decided_at.
        Used by the Plan Review screen to display the deletion list.
        """
        return self.conn.execute(
            """
            SELECT fa.id AS action_id, fa.file_id, fa.scope, fa.decided_at,
                   f.path, f.size, f.pixel_hash
            FROM file_actions fa
            JOIN files f ON f.id = fa.file_id
            WHERE fa.session_id = ? AND fa.action = 'delete'
                  AND fa.executed_at IS NULL
            ORDER BY f.path
            """,
            (session_id,),
        ).fetchall()

    def mark_file_action_executed(
        self, session_id: int, file_id: int, executed_at: str
    ) -> None:
        """Set executed_at timestamp on a file_action row."""
        self.conn.execute(
            """
            UPDATE file_actions SET executed_at = ?
            WHERE session_id = ? AND file_id = ?
            """,
            (executed_at, session_id, file_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Requests (UX Redesign Phase 4 — Family Discovery)
    # ------------------------------------------------------------------

    def create_request(
        self,
        session_id: int,
        pixel_hash: str,
        target_peer: str,
        requested_at: str,
    ) -> int:
        """Insert a photo request and return its id."""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO requests
                (session_id, pixel_hash, target_peer, requested_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, pixel_hash, target_peer, requested_at),
        )
        self.conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = self.conn.execute(
            """
            SELECT id FROM requests
            WHERE session_id = ? AND pixel_hash = ? AND target_peer = ?
            """,
            (session_id, pixel_hash, target_peer),
        ).fetchone()
        return row["id"]

    def create_requests_batch(
        self,
        rows: list[tuple],
    ) -> None:
        """Bulk-insert photo requests.

        Each element: (session_id, pixel_hash, target_peer, requested_at)
        """
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO requests
                (session_id, pixel_hash, target_peer, requested_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def get_requests_for_session(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return all requests for a session, ordered by requested_at."""
        return self.conn.execute(
            """
            SELECT * FROM requests
            WHERE session_id = ?
            ORDER BY requested_at DESC
            """,
            (session_id,),
        ).fetchall()

    def get_pending_requests_count(self, session_id: int) -> int:
        """Return count of pending requests for a session."""
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM requests
            WHERE session_id = ? AND status = 'pending'
            """,
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def update_request_status(
        self,
        request_id: int,
        status: str,
        responded_at: str | None = None,
        fulfilled_at: str | None = None,
    ) -> None:
        """Update the status of a request."""
        self.conn.execute(
            """
            UPDATE requests
            SET status = ?, responded_at = COALESCE(?, responded_at),
                fulfilled_at = COALESCE(?, fulfilled_at)
            WHERE id = ?
            """,
            (status, responded_at, fulfilled_at, request_id),
        )
        self.conn.commit()

    def cancel_request(self, request_id: int) -> None:
        """Cancel a pending request."""
        self.conn.execute(
            "UPDATE requests SET status = 'cancelled' WHERE id = ?",
            (request_id,),
        )
        self.conn.commit()

    def get_incoming_requests(self, local_username: str) -> list[sqlite3.Row]:
        """Return requests targeting the local user (from peer exports)."""
        return self.conn.execute(
            """
            SELECT * FROM requests
            WHERE target_peer = ? AND status = 'pending'
            ORDER BY requested_at DESC
            """,
            (local_username,),
        ).fetchall()

    def get_family_treasures(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return remote files that do NOT exist locally, with peer info.

        Used by the Family Discovery screen to show 'family treasures'.
        Each row includes: remote file details + peer username.
        """
        return self.conn.execute(
            """
            SELECT rf.id AS remote_file_id, rf.pixel_hash, rf.filename,
                   rf.path AS remote_path, rf.size, rf.modified_at,
                   rp.username AS peer_username
            FROM remote_files rf
            JOIN remote_peers rp ON rp.id = rf.peer_id
            WHERE rf.pixel_hash NOT IN (
                SELECT pixel_hash FROM files
                WHERE session_id = ? AND status = 'active'
                      AND pixel_hash IS NOT NULL
            )
            ORDER BY rp.username, rf.filename
            """,
            (session_id,),
        ).fetchall()

    def get_pending_requests_for_review(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return pending requests with peer info for plan review display."""
        return self.conn.execute(
            """
            SELECT r.id AS request_id, r.pixel_hash, r.target_peer,
                   r.requested_at, r.status
            FROM requests r
            WHERE r.session_id = ? AND r.status = 'pending'
            ORDER BY r.requested_at
            """,
            (session_id,),
        ).fetchall()

    def delete_request(
        self, session_id: int, pixel_hash: str, target_peer: str
    ) -> None:
        """Delete a request (used when toggling off in Family Discovery)."""
        self.conn.execute(
            """
            DELETE FROM requests
            WHERE session_id = ? AND pixel_hash = ? AND target_peer = ?
            """,
            (session_id, pixel_hash, target_peer),
        )
        self.conn.commit()

    def is_requested(
        self, session_id: int, pixel_hash: str, target_peer: str
    ) -> bool:
        """Check if a request already exists for this hash+peer combo."""
        row = self.conn.execute(
            """
            SELECT 1 FROM requests
            WHERE session_id = ? AND pixel_hash = ? AND target_peer = ?
                  AND status IN ('pending', 'approved')
            """,
            (session_id, pixel_hash, target_peer),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Perceptual hash + similarity groups (Similar Image Detection)
    # ------------------------------------------------------------------

    def update_perceptual_hashes_batch(
        self, updates: list[tuple[int, str, int, int]]
    ) -> None:
        """Write perceptual_hash, width, height for multiple files.

        Each element: (file_id, perceptual_hash, width, height).
        """
        self.conn.executemany(
            "UPDATE files SET perceptual_hash = ?, width = ?, height = ? "
            "WHERE id = ?",
            [(ph, w, h, fid) for fid, ph, w, h in updates],
        )
        self.conn.commit()

    def update_dual_hashes_batch(
        self, updates: list[tuple[int, str, str, str, int, int]]
    ) -> None:
        """Write pixel_hash, thumbnail, perceptual_hash, width, height for files
        that were skipped by the size pre-filter in Pass 2.

        Each element: (file_id, pixel_hash, thumbnail_path, perceptual_hash,
                        width, height).
        """
        self.conn.executemany(
            """UPDATE files
               SET pixel_hash = ?, hash_algorithm = ?,
                   thumbnail_path = ?,
                   perceptual_hash = ?, width = ?, height = ?
               WHERE id = ?""",
            [
                (
                    ph,
                    "xxh128" if len(ph) == 32 else "sha256",
                    thumb,
                    pph,
                    w,
                    h,
                    fid,
                )
                for fid, ph, thumb, pph, w, h in updates
            ],
        )
        self.conn.commit()

    def get_files_needing_hashes(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return files where perceptual_hash IS NULL — candidates for Pass 3.

        Includes files skipped by the size pre-filter (pixel_hash IS NULL)
        AND files already pixel-hashed (pixel_hash IS NOT NULL) that lack pHash.
        """
        return self.conn.execute(
            """
            SELECT * FROM files
            WHERE session_id = ? AND perceptual_hash IS NULL
                  AND status = 'active'
            ORDER BY path
            """,
            (session_id,),
        ).fetchall()

    def get_files_with_phash(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return all files that have a perceptual_hash set."""
        return self.conn.execute(
            """
            SELECT * FROM files
            WHERE session_id = ? AND perceptual_hash IS NOT NULL
                  AND status = 'active'
            ORDER BY pixel_hash, id
            """,
            (session_id,),
        ).fetchall()

    def create_similarity_group(
        self,
        session_id: int,
        created_at: str,
        representative_file_id: int,
        member_count: int = 0,
    ) -> int:
        """Insert a new similarity group and return its id."""
        cur = self.conn.execute(
            """
            INSERT INTO similarity_groups
                (session_id, created_at, representative_file_id, member_count)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, created_at, representative_file_id, member_count),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def add_similarity_group_members_batch(
        self, rows: list[tuple[int, int, int]]
    ) -> None:
        """Bulk-insert similarity group members.

        Each tuple: (group_id, file_id, distance).
        """
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO similarity_group_members
                (group_id, file_id, distance)
            VALUES (?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def clear_similarity_groups(self, session_id: int) -> None:
        """Delete all similarity groups (and their members via CASCADE)."""
        self.conn.execute(
            "DELETE FROM similarity_groups WHERE session_id = ?",
            (session_id,),
        )
        self.conn.commit()

    def get_similarity_groups(
        self, session_id: int
    ) -> list[sqlite3.Row]:
        """Return all similarity groups for a session."""
        return self.conn.execute(
            """
            SELECT sg.*, f.path AS representative_path
            FROM similarity_groups sg
            LEFT JOIN files f ON f.id = sg.representative_file_id
            WHERE sg.session_id = ?
            ORDER BY sg.member_count DESC, sg.id
            """,
            (session_id,),
        ).fetchall()

    def get_similarity_group_count(self, session_id: int) -> int:
        """Return count of similarity groups for a session."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM similarity_groups WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_similarity_group_members(
        self, group_id: int
    ) -> list[sqlite3.Row]:
        """Return all files in a similarity group with full file metadata."""
        return self.conn.execute(
            """
            SELECT sgm.group_id, sgm.distance,
                   f.*
            FROM similarity_group_members sgm
            JOIN files f ON f.id = sgm.file_id
            WHERE sgm.group_id = ?
            ORDER BY sgm.distance, f.id
            """,
            (group_id,),
        ).fetchall()

    def get_similarity_group_file_count(self, session_id: int) -> int:
        """Return total count of files across all similarity groups."""
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM similarity_group_members sgm
            JOIN similarity_groups sg ON sg.id = sgm.group_id
            WHERE sg.session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def update_similarity_group_status(
        self, group_id: int, status: str
    ) -> None:
        """Update the review status of a similarity group."""
        self.conn.execute(
            "UPDATE similarity_groups SET status = ? WHERE id = ?",
            (status, group_id),
        )
        self.conn.commit()

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
