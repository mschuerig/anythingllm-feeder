from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from forage import config, db, hashing
from forage.extractors import ALL_EXTS, extractor_for


class Classification(str, Enum):
    NEW = "new"
    UNCHANGED = "unchanged"
    TOUCHED = "touched"
    CHANGED = "changed"


@dataclass
class WalkItem:
    source: str
    rel: str
    abs: Path
    classification: Classification
    mtime: float
    size: int
    sha256: str | None
    extractor: str | None
    prior: db.FileRow | None


def iter_source(
    source_root: Path, exts: Iterable[str] | None = None
) -> Iterator[tuple[str, Path, os.stat_result]]:
    """Yield (relpath, abspath, stat) for files under `source_root`.

    Skips dotfiles. Filters by suffix membership in `exts` (with leading dots,
    lowercased). When `exts` is None, defaults to all extractor-supported
    extensions.
    """
    allowed = (
        frozenset(e.lower() for e in exts) if exts is not None else ALL_EXTS
    )
    for p in source_root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        if name.startswith("."):
            continue
        if p.suffix.lower() not in allowed:
            continue
        # Skip files under any dot-prefixed directory.
        rel = p.relative_to(source_root).as_posix()
        if any(part.startswith(".") for part in rel.split("/")[:-1]):
            continue
        yield rel, p, p.stat()


def classify(
    prior: db.FileRow | None,
    mtime: float,
    size: int,
    abs_path: Path,
) -> tuple[Classification, str | None]:
    """Return classification and (if computed) the file's sha256."""
    if prior is None:
        return Classification.NEW, None
    if prior.mtime == mtime and prior.size == size:
        return Classification.UNCHANGED, None
    sha = hashing.sha256_file(abs_path)
    if prior.sha256 == sha:
        return Classification.TOUCHED, sha
    return Classification.CHANGED, sha


def walk_source(
    conn: sqlite3.Connection,
    source_cfg: config.Source,
    exts: Iterable[str] | None = None,
) -> Iterator[WalkItem]:
    """Walk one source and classify every eligible file against the db."""
    root = Path(source_cfg.path)
    for rel, abs_path, stat in iter_source(root, exts):
        prior = db.get_file(conn, source_cfg.name, rel)
        cls, sha = classify(prior, stat.st_mtime, stat.st_size, abs_path)
        yield WalkItem(
            source=source_cfg.name,
            rel=rel,
            abs=abs_path,
            classification=cls,
            mtime=stat.st_mtime,
            size=stat.st_size,
            sha256=sha,
            extractor=extractor_for(abs_path),
            prior=prior,
        )


def parse_ext_filter(value: str | None) -> frozenset[str] | None:
    """Convert a `--ext pdf,mp4` string to a `{'.pdf', '.mp4'}` set."""
    if value is None:
        return None
    raw = [v.strip().lower() for v in value.split(",") if v.strip()]
    if not raw:
        return None
    return frozenset(f".{e.lstrip('.')}" for e in raw)


def find_orphans(
    conn: sqlite3.Connection,
    sources: list[config.Source],
    *,
    source_filter: str | None = None,
) -> list[db.FileRow]:
    """Return rows whose source files no longer exist on disk.

    `source_filter` restricts the sweep to one source name. Rows whose
    `source` is unknown to `sources` are always treated as orphan (they
    belong to a source that was removed from the collection).
    """
    source_lookup = {s.name: Path(s.path) for s in sources}
    orphans: list[db.FileRow] = []
    for row in db.iter_files(conn):
        if source_filter is not None and row.source != source_filter:
            continue
        root = source_lookup.get(row.source)
        if root is None:
            orphans.append(row)
            continue
        if not (root / row.path).exists():
            orphans.append(row)
    return orphans
