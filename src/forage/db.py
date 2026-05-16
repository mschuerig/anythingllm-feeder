from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
  source         TEXT    NOT NULL,
  path           TEXT    NOT NULL,
  sha256         TEXT,
  mtime          REAL,
  size           INTEGER,
  output_path    TEXT,
  extractor      TEXT,
  status         TEXT,
  status_detail  TEXT,
  extracted_at   TEXT,
  updated_at     TEXT,
  PRIMARY KEY (source, path)
);

CREATE INDEX IF NOT EXISTS files_status ON files(status);
CREATE INDEX IF NOT EXISTS files_source ON files(source);

CREATE TABLE IF NOT EXISTS queue (
  source        TEXT NOT NULL,
  path          TEXT NOT NULL,
  status        TEXT NOT NULL,
  error         TEXT,
  enqueued_at   TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT,
  PRIMARY KEY (source, path),
  FOREIGN KEY (source, path) REFERENCES files(source, path)
);

CREATE INDEX IF NOT EXISTS queue_status_enqueued ON queue(status, enqueued_at);
"""


@dataclass
class FileRow:
    source: str
    path: str
    sha256: str | None = None
    mtime: float | None = None
    size: int | None = None
    output_path: str | None = None
    extractor: str | None = None
    status: str | None = None
    status_detail: str | None = None
    extracted_at: str | None = None
    updated_at: str | None = None


@dataclass
class QueueRow:
    source: str
    path: str
    status: str
    error: str | None = None
    enqueued_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


@contextmanager
def open_db(db_path: Path):
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def reset_db(db_path: Path) -> None:
    """Delete the SQLite db and any sidecar journal/WAL files."""
    for suffix in ("", "-shm", "-wal", "-journal"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()


def integrity_check(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("PRAGMA integrity_check").fetchall()]


def _row_to_filerow(row: sqlite3.Row) -> FileRow:
    return FileRow(
        source=row["source"],
        path=row["path"],
        sha256=row["sha256"],
        mtime=row["mtime"],
        size=row["size"],
        output_path=row["output_path"],
        extractor=row["extractor"],
        status=row["status"],
        status_detail=row["status_detail"],
        extracted_at=row["extracted_at"],
        updated_at=row["updated_at"],
    )


def upsert_file(conn: sqlite3.Connection, row: FileRow) -> None:
    d = asdict(row)
    cols = ", ".join(d.keys())
    placeholders = ", ".join(f":{k}" for k in d)
    updates = ", ".join(
        f"{k} = excluded.{k}" for k in d if k not in ("source", "path")
    )
    sql = (
        f"INSERT INTO files ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(source, path) DO UPDATE SET {updates}"
    )
    with conn:
        conn.execute(sql, d)


def get_file(
    conn: sqlite3.Connection, source: str, path: str
) -> FileRow | None:
    row = conn.execute(
        "SELECT * FROM files WHERE source = ? AND path = ?", (source, path)
    ).fetchone()
    return _row_to_filerow(row) if row else None


def iter_files(
    conn: sqlite3.Connection, source: str | None = None
) -> Iterator[FileRow]:
    if source is None:
        cur = conn.execute("SELECT * FROM files ORDER BY source, path")
    else:
        cur = conn.execute(
            "SELECT * FROM files WHERE source = ? ORDER BY path", (source,)
        )
    for row in cur:
        yield _row_to_filerow(row)


def delete_file(conn: sqlite3.Connection, source: str, path: str) -> None:
    with conn:
        conn.execute(
            "DELETE FROM queue WHERE source = ? AND path = ?", (source, path)
        )
        conn.execute(
            "DELETE FROM files WHERE source = ? AND path = ?", (source, path)
        )


def delete_source_rows(conn: sqlite3.Connection, source: str) -> int:
    with conn:
        conn.execute("DELETE FROM queue WHERE source = ?", (source,))
        cur = conn.execute("DELETE FROM files WHERE source = ?", (source,))
        return cur.rowcount


def status_counts(
    conn: sqlite3.Connection, source: str | None = None
) -> dict[str, int]:
    if source is None:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM files GROUP BY status"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM files WHERE source = ? GROUP BY status",
            (source,),
        ).fetchall()
    return {r["status"]: r["n"] for r in rows if r["status"] is not None}


def queue_depth(conn: sqlite3.Connection, status: str = "pending") -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM queue WHERE status = ?", (status,)
    ).fetchone()
    return int(row["n"]) if row else 0


def enqueue(
    conn: sqlite3.Connection, source: str, path: str, now: str
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO queue (source, path, status, enqueued_at) "
            "VALUES (?, ?, 'pending', ?) "
            "ON CONFLICT(source, path) DO UPDATE SET "
            "  status = 'pending', enqueued_at = excluded.enqueued_at, "
            "  error = NULL, started_at = NULL, finished_at = NULL",
            (source, path, now),
        )


def update_queue(
    conn: sqlite3.Connection,
    source: str,
    path: str,
    status: str,
    *,
    error: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    fields: list[str] = ["status = ?"]
    params: list[object] = [status]
    if error is not None:
        fields.append("error = ?")
        params.append(error)
    if started_at is not None:
        fields.append("started_at = ?")
        params.append(started_at)
    if finished_at is not None:
        fields.append("finished_at = ?")
        params.append(finished_at)
    params.extend([source, path])
    with conn:
        conn.execute(
            f"UPDATE queue SET {', '.join(fields)} WHERE source = ? AND path = ?",
            params,
        )


def reset_running_to_pending(conn: sqlite3.Connection) -> int:
    """Flip any stale ``running`` queue rows back to ``pending``.

    Called under the collection lock at the start of a transcribe run: anything
    still marked ``running`` must be from a process that died (Ctrl-C, kill,
    power loss) without updating the row, so the file is safe to re-pick.
    """
    with conn:
        cur = conn.execute(
            "UPDATE queue SET status = 'pending', started_at = NULL "
            "WHERE status = 'running'"
        )
        return cur.rowcount


def dequeue_oldest(
    conn: sqlite3.Connection,
    *,
    limit: int = 1,
    include_failed: bool = False,
) -> list[sqlite3.Row]:
    statuses = ["pending"] + (["failed"] if include_failed else [])
    placeholders = ", ".join("?" for _ in statuses)
    return conn.execute(
        f"SELECT * FROM queue WHERE status IN ({placeholders}) "
        f"ORDER BY enqueued_at LIMIT ?",
        (*statuses, limit),
    ).fetchall()


def recent_failures(
    conn: sqlite3.Connection, limit: int = 10
) -> list[FileRow]:
    rows = conn.execute(
        "SELECT * FROM files WHERE status = 'failed' "
        "ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_filerow(r) for r in rows]


def recent_suspicious(
    conn: sqlite3.Connection, limit: int = 10
) -> list[FileRow]:
    rows = conn.execute(
        "SELECT * FROM files WHERE status = 'suspicious' "
        "ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_filerow(r) for r in rows]
