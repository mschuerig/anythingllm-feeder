from __future__ import annotations

from pathlib import Path

import pytest

from forage import db, paths
from forage.cli import main


def _seed_clean(app_support: Path, name: str, source_root: Path) -> None:
    """Create a minimal but consistent collection: config, state.db, one output file."""
    coll = paths.collection_dir(name)
    (coll / "output" / "src").mkdir(parents=True)
    out_file = coll / "output" / "src" / "doc.md"
    out_file.write_text("hi\n")
    cfg_path = paths.collection_config_path(name)
    cfg_path.write_text(
        '{"version":1,"name":"' + name + '","created_at":"2026-05-15T00:00:00Z",'
        '"do_ocr":true,"sources":[{"name":"src","path":"' + str(source_root)
        + '","created_at":"2026-05-15T00:00:00Z"}]}\n'
    )
    src_file = source_root / "doc.txt"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text("source\n")

    db_path = paths.collection_db_path(name)
    with db.open_db(db_path) as conn:
        db.init_schema(conn)
        db.upsert_file(
            conn,
            db.FileRow(
                source="src",
                path="doc.txt",
                sha256="a" * 64,
                mtime=0.0,
                size=1,
                output_path="src/doc.md",
                extractor="docling",
                status="ok",
                extracted_at="2026-05-15T00:00:00Z",
                updated_at="2026-05-15T00:00:00Z",
            ),
        )


def _seed_with_missing_output(app_support: Path, name: str, source_root: Path) -> None:
    _seed_clean(app_support, name, source_root)
    out_file = paths.collection_output_dir(name) / "src" / "doc.md"
    out_file.unlink()


def test_doctor_no_collections(app_support: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["doctor"])
    assert rc == 0
    assert "no collections" in capsys.readouterr().out


def test_doctor_reports_ok(
    app_support: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_clean(app_support, "news", tmp_path / "src")

    rc = main(["doctor"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "news" in out
    assert "ok" in out


def test_doctor_reports_warn_and_exits_nonzero(
    app_support: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_clean(app_support, "good", tmp_path / "src-good")
    _seed_with_missing_output(app_support, "bad", tmp_path / "src-bad")

    rc = main(["doctor"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "good" in out
    assert "bad" in out
    assert "WARN" in out
    assert "missing output" in out
