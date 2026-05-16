"""Disk-space accounting against AnythingLLM's `storage/` directory.

ingest writes nothing here; we only `stat` and walk subtrees. The storage
directory is located via `config.resolve_anythingllm_storage_dir()`; when
that returns None the caller should skip the storage report entirely.

Three numbers are reported:

* ``documents`` — exact, per-collection. Each row in our `uploads.db` has
  an ``anythingllm_loc`` like ``custom-documents/raw-<slug>-<uuid>.json``;
  we stat each one under ``<storage>/documents/``.
* ``lancedb`` — per-workspace, walking ``<storage>/lancedb/<slug>.lance/``.
  This is where the per-workspace vector tables live.
* ``vector_cache`` — global only. The on-disk cache filename is a UUIDv5
  not derivable cheaply from the document id; per-collection attribution
  would mean parsing every cache file once. Reported as a shared total.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageReport:
    storage_dir: Path
    documents_bytes: int
    documents_count: int
    documents_missing: int
    lancedb_bytes: int
    lancedb_present: bool
    vector_cache_bytes: int
    vector_cache_present: bool

    @property
    def attributable_bytes(self) -> int:
        return self.documents_bytes + self.lancedb_bytes


def format_bytes(n: int) -> str:
    """Human-readable size, like ``du -h``: B, KB, MB, GB, TB."""
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(n)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} {units[-1]}"  # unreachable


def _dir_size(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for p in root.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            # File vanished between rglob and stat — fine, just skip.
            continue
    return total


def documents_size(
    storage_dir: Path, locations: Iterable[str]
) -> tuple[int, int, int]:
    """Stat each location under ``<storage>/documents/``.

    Returns ``(total_bytes, count_present, count_missing)``. A location is
    "missing" if our `uploads.db` still references a file the user has
    already deleted in the AnythingLLM UI; we report it but don't crash.
    """
    docs_root = storage_dir / "documents"
    total = 0
    present = 0
    missing = 0
    for loc in locations:
        path = docs_root / loc
        try:
            total += path.stat().st_size
            present += 1
        except OSError:
            missing += 1
    return total, present, missing


def lancedb_size(storage_dir: Path, workspace_slug: str) -> tuple[int, bool]:
    """Size of ``<storage>/lancedb/<slug>.lance/``.

    Returns ``(bytes, present)``. If the workspace has never been embedded
    (or its slug is wrong), the directory is absent and bytes is 0.
    """
    ws_dir = storage_dir / "lancedb" / f"{workspace_slug}.lance"
    if not ws_dir.exists():
        return 0, False
    return _dir_size(ws_dir), True


def vector_cache_total(storage_dir: Path) -> tuple[int, bool]:
    """Total size of ``<storage>/vector-cache/`` (shared across workspaces).

    Returns ``(bytes, present)``.
    """
    cache_dir = storage_dir / "vector-cache"
    if not cache_dir.exists():
        return 0, False
    return _dir_size(cache_dir), True


def report(
    storage_dir: Path,
    *,
    document_locations: Iterable[str],
    workspace_slug: str,
) -> StorageReport:
    """Build a full report for one workspace + its documents."""
    doc_bytes, doc_count, doc_missing = documents_size(
        storage_dir, document_locations
    )
    lance_bytes, lance_present = lancedb_size(storage_dir, workspace_slug)
    cache_bytes, cache_present = vector_cache_total(storage_dir)
    return StorageReport(
        storage_dir=storage_dir,
        documents_bytes=doc_bytes,
        documents_count=doc_count,
        documents_missing=doc_missing,
        lancedb_bytes=lance_bytes,
        lancedb_present=lance_present,
        vector_cache_bytes=cache_bytes,
        vector_cache_present=cache_present,
    )
