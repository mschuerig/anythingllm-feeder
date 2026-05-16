from __future__ import annotations

from pathlib import Path

import pytest

from forage import cli, config, db, paths


def run(*argv: str) -> int:
    return cli.main(list(argv))


def _seed_collection(source_tree: Path, name: str = "demo") -> None:
    rc = run("create", name, "--source", f"only={source_tree}")
    assert rc == 0


def test_check_ok_on_empty_collection(
    app_support: Path, source_tree: Path, capsys: pytest.CaptureFixture[str]
):
    _seed_collection(source_tree)
    capsys.readouterr()
    rc = run("repair", "demo")
    assert rc == 0
    assert "ok" in capsys.readouterr().out


def test_check_detects_missing_source_and_orphan_output(
    app_support: Path, source_tree: Path, capsys: pytest.CaptureFixture[str]
):
    _seed_collection(source_tree)
    db_path = paths.collection_db_path("demo")
    out_dir = paths.collection_output_dir("demo")

    with db.open_db(db_path) as conn:
        db.upsert_file(
            conn,
            db.FileRow(
                source="only",
                path="ghost.md",
                sha256="x",
                output_path="only/ghost.md",
                extractor="docling",
                status="ok",
            ),
        )
    # And drop an orphan output file
    orphan = out_dir / "only" / "orphan.md"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("nope\n")

    capsys.readouterr()
    rc = run("repair", "demo")
    assert rc == 1
    out = capsys.readouterr().out
    assert "missing source: only/ghost.md" in out
    assert "missing output: only/ghost.md" in out
    assert "orphan output:" in out and "orphan.md" in out


def test_rebuild_reconstructs_from_disk(
    app_support: Path, source_tree: Path, capsys: pytest.CaptureFixture[str]
):
    _seed_collection(source_tree)
    db_path = paths.collection_db_path("demo")
    out_dir = paths.collection_output_dir("demo")

    # Simulate prior successful extraction of `a/note.md` by placing its output.
    (out_dir / "only" / "a").mkdir(parents=True, exist_ok=True)
    (out_dir / "only" / "a" / "note.md").write_text("# hello\n")

    # Also create some junk in the db that rebuild should wipe.
    with db.open_db(db_path) as conn:
        db.upsert_file(
            conn, db.FileRow(source="only", path="ghost.md", status="ok")
        )

    capsys.readouterr()
    rc = run("repair", "demo", "--rebuild")
    assert rc == 0
    out = capsys.readouterr().out
    assert "rebuilt" in out

    with db.open_db(db_path) as conn:
        rows = list(db.iter_files(conn, "only"))
    paths_in_db = {r.path for r in rows}
    # Source tree has note.md, plain.txt, deep/x/doc.md — only note.md has output.
    assert paths_in_db == {"a/note.md"}
    note_row = next(r for r in rows if r.path == "a/note.md")
    assert note_row.status == "ok"
    assert note_row.output_path == "only/a/note.md"
    assert note_row.sha256 is not None
