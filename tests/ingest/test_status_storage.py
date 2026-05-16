from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.cli import main
from _helpers import FakeForageFile


def _write_doc(root: Path, rel: str, size: int) -> None:
    p = root / "documents" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


@pytest.fixture
def storage_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Fake AnythingLLM storage dir wired up via env override."""
    root = tmp_path / "anythingllm-storage"
    root.mkdir()
    monkeypatch.setenv("ANYTHINGLLM_STORAGE_DIR", str(root))
    return root


def test_status_human_includes_storage(
    ingest_home: Path,
    forage_home: Path,
    storage_dir: Path,
    fake_server,
    client_factory,
    make_forage_collection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After a sync, `ingest status` should report the per-collection bytes."""
    make_forage_collection(
        "demo",
        [
            FakeForageFile("notes", "a.md", "HA", "ok", "notes/a.md", content="# A\n"),
            FakeForageFile("notes", "b.md", "HB", "ok", "notes/b.md", content="# B\n"),
        ],
    )
    # Drive a sync to populate uploads.db.
    from ingest.sync import sync_collection
    sync_collection("demo", client=client_factory())

    # Whatever locations the fake server handed us, plant matching files on
    # disk so `documents_size` finds them.
    locs = list(fake_server.documents.keys())
    _write_doc(storage_dir, locs[0], 1000)
    _write_doc(storage_dir, locs[1], 500)
    (storage_dir / "lancedb" / "demo.lance").mkdir(parents=True)
    (storage_dir / "lancedb" / "demo.lance" / "data.lance").write_bytes(
        b"v" * 4096
    )
    (storage_dir / "vector-cache").mkdir()
    (storage_dir / "vector-cache" / "anycache.json").write_bytes(b"c" * 700)

    rc = main(["status", "demo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "storage in AnythingLLM" in out
    assert "documents:" in out
    assert "(2 files)" in out
    assert "vectors:" in out
    assert "attributable:" in out
    assert "shared:" in out  # vector-cache present


def test_status_json_includes_storage(
    ingest_home: Path,
    forage_home: Path,
    storage_dir: Path,
    fake_server,
    client_factory,
    make_forage_collection,
    capsys: pytest.CaptureFixture[str],
) -> None:
    make_forage_collection(
        "demo",
        [FakeForageFile("n", "a.md", "H1", "ok", "n/a.md", content="# A\n")],
    )
    from ingest.sync import sync_collection
    sync_collection("demo", client=client_factory())
    loc = next(iter(fake_server.documents))
    _write_doc(storage_dir, loc, 42)

    rc = main(["--json", "status", "demo"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "storage" in payload
    s = payload["storage"]
    assert s["documents_bytes"] == 42
    assert s["documents_count"] == 1
    assert s["documents_missing"] == 0
    assert s["lancedb_present"] is False  # we never created the lancedb dir
    assert s["attributable_bytes"] == 42


def test_status_silent_when_storage_dir_absent(
    ingest_home: Path,
    forage_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_server,
    client_factory,
    make_forage_collection,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If the resolved storage dir doesn't exist, the storage section is skipped
    and the rest of `ingest status` works fine."""
    make_forage_collection(
        "demo",
        [FakeForageFile("n", "a.md", "H1", "ok", "n/a.md")],
    )
    from ingest.sync import sync_collection
    sync_collection("demo", client=client_factory())

    monkeypatch.setenv(
        "ANYTHINGLLM_STORAGE_DIR", str(tmp_path / "does-not-exist")
    )
    rc = main(["status", "demo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "storage in AnythingLLM" not in out
    assert "new:" in out  # ordinary diff output is still there
