from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

UPLOADABLE_STATUSES = ("ok",)
UPLOADABLE_STATUSES_WITH_SUSPICIOUS = ("ok", "suspicious")


class ForageStateError(Exception):
    pass


@dataclass(frozen=True)
class ForageFile:
    source: str
    path: str
    sha256: str | None
    output_path: str | None
    extractor: str | None
    status: str | None
    status_detail: str | None
    extracted_at: str | None


@contextmanager
def open_readonly(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open forage's state.db in read-only mode using the file: URI form.

    Forage uses WAL mode (see forage/SPEC.md), so concurrent reads while it
    is writing are safe. We never write here.
    """
    if not db_path.exists():
        raise ForageStateError(
            f"forage state not found at {db_path}. "
            "Has the collection been created and updated?"
        )
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_file(row: sqlite3.Row) -> ForageFile:
    return ForageFile(
        source=row["source"],
        path=row["path"],
        sha256=row["sha256"],
        output_path=row["output_path"],
        extractor=row["extractor"],
        status=row["status"],
        status_detail=row["status_detail"],
        extracted_at=row["extracted_at"],
    )


def iter_uploadable(
    conn: sqlite3.Connection, *, include_suspicious: bool = False
) -> Iterator[ForageFile]:
    """Yield rows whose extraction produced a usable Markdown output."""
    statuses = (
        UPLOADABLE_STATUSES_WITH_SUSPICIOUS
        if include_suspicious
        else UPLOADABLE_STATUSES
    )
    placeholders = ", ".join("?" for _ in statuses)
    cur = conn.execute(
        f"SELECT * FROM files WHERE status IN ({placeholders}) "
        "ORDER BY source, path",
        statuses,
    )
    for row in cur:
        yield _row_to_file(row)


def output_file_path(output_root: Path, row: ForageFile) -> Path:
    """Absolute path of the Markdown file forage produced for this row."""
    if not row.output_path:
        raise ForageStateError(
            f"row {row.source}/{row.path} has no output_path"
        )
    return output_root / row.output_path
