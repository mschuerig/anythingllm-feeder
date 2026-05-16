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

CREATE TABLE IF NOT EXISTS uploads (
  source           TEXT NOT NULL,
  path             TEXT NOT NULL,
  sha256           TEXT NOT NULL,
  anythingllm_loc  TEXT NOT NULL,
  workspace_slug   TEXT NOT NULL,
  forage_status    TEXT,
  uploaded_at      TEXT NOT NULL,
  PRIMARY KEY (source, path)
);

CREATE INDEX IF NOT EXISTS uploads_source ON uploads(source);
"""


@dataclass
class Upload:
    source: str
    path: str
    sha256: str
    anythingllm_loc: str
    workspace_slug: str
    uploaded_at: str
    forage_status: str | None = None


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
def open_db(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        init_schema(conn)
        yield conn
    finally:
        conn.close()


def _row_to_upload(row: sqlite3.Row) -> Upload:
    return Upload(
        source=row["source"],
        path=row["path"],
        sha256=row["sha256"],
        anythingllm_loc=row["anythingllm_loc"],
        workspace_slug=row["workspace_slug"],
        uploaded_at=row["uploaded_at"],
        forage_status=row["forage_status"],
    )


def iter_uploads(conn: sqlite3.Connection) -> Iterator[Upload]:
    cur = conn.execute("SELECT * FROM uploads ORDER BY source, path")
    for row in cur:
        yield _row_to_upload(row)


def get_upload(
    conn: sqlite3.Connection, source: str, path: str
) -> Upload | None:
    row = conn.execute(
        "SELECT * FROM uploads WHERE source = ? AND path = ?", (source, path)
    ).fetchone()
    return _row_to_upload(row) if row else None


def upsert_upload(conn: sqlite3.Connection, upload: Upload) -> None:
    d = asdict(upload)
    cols = ", ".join(d.keys())
    placeholders = ", ".join(f":{k}" for k in d)
    updates = ", ".join(
        f"{k} = excluded.{k}" for k in d if k not in ("source", "path")
    )
    sql = (
        f"INSERT INTO uploads ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(source, path) DO UPDATE SET {updates}"
    )
    with conn:
        conn.execute(sql, d)


def delete_upload(conn: sqlite3.Connection, source: str, path: str) -> None:
    with conn:
        conn.execute(
            "DELETE FROM uploads WHERE source = ? AND path = ?", (source, path)
        )


def reset_db(db_path: Path) -> None:
    for suffix in ("", "-shm", "-wal", "-journal"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
