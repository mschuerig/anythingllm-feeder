from __future__ import annotations

from pathlib import Path

import pytest

from forage import cli, config, db, extractors, paths
from forage.extractors.base import ExtractionResult


def run(*argv: str) -> int:
    return cli.main(list(argv))


class FakeDocling:
    name = "docling"

    def __init__(self):
        self.calls: list[Path] = []

    def extract(self, src: Path) -> ExtractionResult:
        self.calls.append(src)
        return ExtractionResult(
            markdown=f"# {src.name}\n",
            extractor=self.name,
        )


@pytest.fixture
def fake_docling(monkeypatch: pytest.MonkeyPatch) -> FakeDocling:
    fake = FakeDocling()
    monkeypatch.setattr(extractors, "get_docling", lambda *, do_ocr: fake)
    return fake


def test_add_source(app_support: Path, tmp_path: Path,
                    capsys: pytest.CaptureFixture[str]):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    assert run("create", "demo", "--source", f"a={a}") == 0
    capsys.readouterr()

    rc = run("add-source", "demo", "b", str(b))
    assert rc == 0
    cfg = config.load_collection("demo")
    assert [s.name for s in cfg.sources] == ["a", "b"]
    assert paths.source_output_dir("demo", "b").is_dir()


def test_add_source_rejects_duplicate(
    app_support: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"
    a.mkdir()
    assert run("create", "demo", "--source", f"a={a}") == 0
    capsys.readouterr()
    rc = run("add-source", "demo", "a", str(a))
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


def test_add_source_invalid_dir(
    app_support: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"
    a.mkdir()
    assert run("create", "demo", "--source", f"a={a}") == 0
    capsys.readouterr()
    rc = run("add-source", "demo", "b", str(tmp_path / "nope"))
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err


def test_remove_source_delete_files(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "x.md").write_text("a")
    (b / "y.md").write_text("b")
    assert run("create", "demo", "--source", f"a={a}", "--source", f"b={b}") == 0
    assert run("update", "demo") == 0
    capsys.readouterr()

    rc = run("remove-source", "demo", "b", "--delete-files")
    assert rc == 0
    cfg = config.load_collection("demo")
    assert [s.name for s in cfg.sources] == ["a"]
    assert not paths.source_output_dir("demo", "b").exists()
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert list(db.iter_files(conn, "b")) == []
        assert len(list(db.iter_files(conn, "a"))) == 1


def test_remove_source_keep_files(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (b / "y.md").write_text("b")
    assert run("create", "demo", "--source", f"a={a}", "--source", f"b={b}") == 0
    assert run("update", "demo") == 0
    capsys.readouterr()

    rc = run("remove-source", "demo", "b", "--keep-files")
    assert rc == 0
    # Output retained but db rows gone.
    assert (paths.source_output_dir("demo", "b") / "y.md").exists()
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert list(db.iter_files(conn, "b")) == []


def test_set_source(app_support: Path, tmp_path: Path,
                    capsys: pytest.CaptureFixture[str]):
    a = tmp_path / "a"; a.mkdir()
    new_a = tmp_path / "new_a"; new_a.mkdir()
    assert run("create", "demo", "--source", f"a={a}") == 0
    capsys.readouterr()

    rc = run("set-source", "demo", "a", str(new_a))
    assert rc == 0
    cfg = config.load_collection("demo")
    assert cfg.source("a").path == str(new_a.resolve())


def test_rename(app_support: Path, tmp_path: Path,
                capsys: pytest.CaptureFixture[str]):
    a = tmp_path / "a"; a.mkdir()
    assert run("create", "demo", "--source", f"a={a}") == 0
    capsys.readouterr()

    rc = run("rename", "demo", "moved")
    assert rc == 0
    assert not paths.collection_dir("demo").exists()
    assert paths.collection_dir("moved").exists()
    assert config.load_collection("moved").name == "moved"


def test_rename_rejects_existing(
    app_support: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"; a.mkdir()
    assert run("create", "one", "--source", f"a={a}") == 0
    assert run("create", "two", "--source", f"a={a}") == 0
    capsys.readouterr()
    rc = run("rename", "one", "two")
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


def test_remove_collection_delete_files(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"; a.mkdir()
    (a / "x.md").write_text("a")
    assert run("create", "demo", "--source", f"a={a}") == 0
    assert run("update", "demo") == 0
    capsys.readouterr()

    rc = run("remove", "demo", "--delete-files")
    assert rc == 0
    assert not paths.collection_dir("demo").exists()


def test_remove_collection_keep_files(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"; a.mkdir()
    (a / "x.md").write_text("a")
    assert run("create", "demo", "--source", f"a={a}") == 0
    assert run("update", "demo") == 0
    capsys.readouterr()

    rc = run("remove", "demo", "--keep-files")
    assert rc == 0
    coll = paths.collection_dir("demo")
    assert coll.exists()
    assert (coll / "output").exists()
    assert not (coll / "config.json").exists()
    assert not (coll / "state.db").exists()


def test_lock_blocks_second_writer(
    app_support: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"; a.mkdir()
    assert run("create", "demo", "--source", f"a={a}") == 0
    capsys.readouterr()
    from forage.locks import CollectionLocked, collection_lock
    # Hold the lock manually; second writer must fail.
    with collection_lock(paths.collection_lock_path("demo")):
        rc = run("update", "demo")
    assert rc == 2
    err = capsys.readouterr().err
    assert "locked" in err
