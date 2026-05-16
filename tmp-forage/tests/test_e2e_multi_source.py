from __future__ import annotations

from pathlib import Path

import pytest

from forage import cli, config, db, extractors, paths
from forage.extractors.base import ExtractionResult


def run(*argv: str) -> int:
    return cli.main(list(argv))


class FakeDocling:
    name = "docling"
    def extract(self, src: Path) -> ExtractionResult:
        return ExtractionResult(
            markdown=f"# {src.name}\n\n{src.read_text()}",
            extractor=self.name,
        )


@pytest.fixture
def fake_docling(monkeypatch: pytest.MonkeyPatch) -> FakeDocling:
    fake = FakeDocling()
    monkeypatch.setattr(extractors, "get_docling", lambda *, do_ocr: fake)
    return fake


def test_multi_source_full_lifecycle(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str],
):
    a = tmp_path / "a"
    b = tmp_path / "b"
    c = tmp_path / "c"
    for d in (a, b, c):
        d.mkdir()
    (a / "one.md").write_text("alpha")
    (a / "sub").mkdir()
    (a / "sub" / "two.md").write_text("alpha-sub")
    (b / "three.md").write_text("beta")
    (c / "four.md").write_text("gamma")

    # Create with two sources
    assert run("create", "demo", "--source", f"a={a}", "--source", f"b={b}") == 0

    # Initial update
    capsys.readouterr()
    assert run("update", "demo") == 0
    out = capsys.readouterr().out
    assert "new=3" in out

    out_dir = paths.collection_output_dir("demo")
    assert (out_dir / "a" / "one.md").read_text().startswith("# one.md")
    assert (out_dir / "a" / "sub" / "two.md").exists()
    assert (out_dir / "b" / "three.md").exists()

    # Add a third source, only it should be new
    assert run("add-source", "demo", "c", str(c)) == 0
    capsys.readouterr()
    assert run("update", "demo") == 0
    out = capsys.readouterr().out
    assert "new=1" in out and "unchanged=3" in out

    # Modify a file, only that one re-extracts
    (a / "one.md").write_text("alpha v2")
    capsys.readouterr()
    assert run("update", "demo") == 0
    out = capsys.readouterr().out
    assert "changed=1" in out

    # Scope to one source via --source
    (a / "one.md").write_text("alpha v3")
    (c / "four.md").write_text("gamma v2")
    capsys.readouterr()
    assert run("update", "demo", "--source", "a") == 0
    out = capsys.readouterr().out
    assert "changed=1" in out  # only `a`
    # `c` still has the old content recorded
    with db.open_db(paths.collection_db_path("demo")) as conn:
        c_row = db.get_file(conn, "c", "four.md")
        assert c_row.sha256 is not None  # was recorded earlier

    # Orphan listing + deletion
    (a / "sub" / "two.md").unlink()
    capsys.readouterr()
    assert run("update", "demo") == 0
    out = capsys.readouterr().out
    assert "orphans (1)" in out and "a/sub/two.md" in out

    capsys.readouterr()
    assert run("update", "demo", "--orphans", "delete") == 0
    assert not (out_dir / "a" / "sub" / "two.md").exists()
    assert not (out_dir / "a" / "sub").exists()  # pruned parent

    # Repair check should be ok
    capsys.readouterr()
    assert run("repair", "demo") == 0
    assert "ok" in capsys.readouterr().out

    # Rebuild reconstructs from output files (3 outputs left: a/one, b/three, c/four)
    capsys.readouterr()
    assert run("repair", "demo", "--rebuild") == 0
    out = capsys.readouterr().out
    assert "3 recorded" in out

    # Remove a source with --delete-files
    capsys.readouterr()
    assert run("remove-source", "demo", "b", "--delete-files") == 0
    assert not paths.source_output_dir("demo", "b").exists()
    cfg = config.load_collection("demo")
    assert [s.name for s in cfg.sources] == ["a", "c"]

    # Rename collection
    capsys.readouterr()
    assert run("rename", "demo", "final") == 0
    assert paths.collection_dir("final").exists()
    assert not paths.collection_dir("demo").exists()
    assert config.load_collection("final").name == "final"
