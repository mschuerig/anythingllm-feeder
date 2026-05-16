from __future__ import annotations

from pathlib import Path

from ingest import storage


def _make_fake_anythingllm_storage(
    root: Path,
    *,
    docs: dict[str, int],          # location -> size in bytes
    lance_files: dict[str, int] | None = None,
    cache_files: dict[str, int] | None = None,
) -> Path:
    """Build a `storage/` tree shaped like AnythingLLM's, for tests."""
    docs_root = root / "documents"
    docs_root.mkdir(parents=True, exist_ok=True)
    for loc, size in docs.items():
        f = docs_root / loc
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * size)
    if lance_files:
        lance_root = root / "lancedb"
        for rel, size in lance_files.items():
            f = lance_root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"y" * size)
    if cache_files:
        cache_root = root / "vector-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        for rel, size in cache_files.items():
            (cache_root / rel).write_bytes(b"z" * size)
    return root


def test_format_bytes() -> None:
    assert storage.format_bytes(0) == "0 B"
    assert storage.format_bytes(1023) == "1023 B"
    assert storage.format_bytes(1024) == "1.0 KB"
    assert storage.format_bytes(1024 * 1024) == "1.0 MB"
    assert storage.format_bytes(int(1.5 * 1024 * 1024)) == "1.5 MB"
    assert storage.format_bytes(2 * 1024**3) == "2.0 GB"


def test_documents_size_counts_present_and_missing(tmp_path: Path) -> None:
    root = _make_fake_anythingllm_storage(
        tmp_path / "storage",
        docs={
            "custom-documents/a.json": 100,
            "custom-documents/b.json": 250,
        },
    )
    total, present, missing = storage.documents_size(
        root,
        [
            "custom-documents/a.json",
            "custom-documents/b.json",
            "custom-documents/gone.json",
        ],
    )
    assert total == 350
    assert present == 2
    assert missing == 1


def test_lancedb_size_per_workspace(tmp_path: Path) -> None:
    root = _make_fake_anythingllm_storage(
        tmp_path / "storage",
        docs={},
        lance_files={
            "forage-news.lance/data/v1.lance": 1024,
            "forage-news.lance/_versions/manifest": 64,
            # A different workspace shouldn't count.
            "other.lance/data/v1.lance": 9999,
        },
    )
    size, present = storage.lancedb_size(root, "forage-news")
    assert present is True
    assert size == 1024 + 64

    size_missing, present_missing = storage.lancedb_size(root, "no-such-ws")
    assert present_missing is False
    assert size_missing == 0


def test_vector_cache_total(tmp_path: Path) -> None:
    root = _make_fake_anythingllm_storage(
        tmp_path / "storage",
        docs={},
        cache_files={"a.json": 200, "b.json": 300, "c.json": 100},
    )
    total, present = storage.vector_cache_total(root)
    assert present is True
    assert total == 600


def test_vector_cache_absent_when_dir_missing(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    total, present = storage.vector_cache_total(root)
    assert present is False
    assert total == 0


def test_report_combines_all_three(tmp_path: Path) -> None:
    root = _make_fake_anythingllm_storage(
        tmp_path / "storage",
        docs={"custom-documents/a.json": 100, "custom-documents/b.json": 50},
        lance_files={"forage-news.lance/x": 500},
        cache_files={"a.json": 999},
    )
    rep = storage.report(
        root,
        document_locations=[
            "custom-documents/a.json",
            "custom-documents/b.json",
        ],
        workspace_slug="forage-news",
    )
    assert rep.documents_bytes == 150
    assert rep.documents_count == 2
    assert rep.documents_missing == 0
    assert rep.lancedb_bytes == 500
    assert rep.lancedb_present is True
    assert rep.vector_cache_bytes == 999
    assert rep.vector_cache_present is True
    assert rep.attributable_bytes == 650
