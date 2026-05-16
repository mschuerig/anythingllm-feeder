from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from forage import cli, config, db, extractors, paths
from forage.extractors.base import ExtractionResult, ExtractorError


def run(*argv: str) -> int:
    return cli.main(list(argv))


class FakeDocling:
    name = "docling"

    def __init__(self):
        self.calls: list[Path] = []

    def extract(self, src: Path) -> ExtractionResult:
        self.calls.append(src)
        return ExtractionResult(
            markdown=f"# {src.name}\n\n{src.read_text()}",
            extractor=self.name,
        )


class FailingDocling:
    name = "docling"

    def extract(self, src: Path) -> ExtractionResult:
        raise ExtractorError("boom")


@pytest.fixture
def fake_docling(monkeypatch: pytest.MonkeyPatch) -> FakeDocling:
    fake = FakeDocling()
    monkeypatch.setattr(extractors, "get_docling", lambda *, do_ocr: fake)
    return fake


@pytest.fixture
def failing_docling(monkeypatch: pytest.MonkeyPatch) -> FailingDocling:
    fake = FailingDocling()
    monkeypatch.setattr(extractors, "get_docling", lambda *, do_ocr: fake)
    return fake


def _seed(name: str, source_root: Path) -> None:
    rc = run("create", name, "--source", f"src={source_root}")
    assert rc == 0


def test_update_extracts_new_files(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "one.md").write_text("hello")
    (src / "sub").mkdir()
    (src / "sub" / "two.txt").write_text("world")
    _seed("demo", src)
    capsys.readouterr()

    rc = run("update", "demo")
    assert rc == 0
    out = capsys.readouterr().out
    assert "new=2" in out

    output_dir = paths.collection_output_dir("demo")
    assert (output_dir / "src" / "one.md").read_text().startswith("# one.md")
    assert (output_dir / "src" / "sub" / "two.md").read_text().startswith("# two.txt")

    # Repeat run: everything unchanged, no extractor calls.
    fake_docling.calls.clear()
    rc = run("update", "demo")
    assert rc == 0
    out = capsys.readouterr().out
    assert "unchanged=2" in out and "new=0" in out
    assert fake_docling.calls == []


def test_update_detects_change_and_touch(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "doc.md").write_text("v1")
    _seed("demo", src)
    assert run("update", "demo") == 0
    capsys.readouterr()
    fake_docling.calls.clear()

    # Touched (mtime changed, content same)
    p = src / "doc.md"
    new_mtime = time.time() + 10
    os.utime(p, (new_mtime, new_mtime))
    assert run("update", "demo") == 0
    out = capsys.readouterr().out
    assert "touched=1" in out
    assert fake_docling.calls == []

    # Changed (content differs)
    p.write_text("v2 longer content")
    assert run("update", "demo") == 0
    out = capsys.readouterr().out
    assert "changed=1" in out
    assert fake_docling.calls and fake_docling.calls[-1] == p

    out_md = paths.collection_output_dir("demo") / "src" / "doc.md"
    assert "v2 longer content" in out_md.read_text()


def test_update_orphan_list_then_delete(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    keep = src / "keep.md"
    gone = src / "gone.md"
    keep.write_text("keep")
    gone.write_text("gone")
    _seed("demo", src)
    assert run("update", "demo") == 0
    capsys.readouterr()

    gone.unlink()
    rc = run("update", "demo")
    assert rc == 0
    out = capsys.readouterr().out
    assert "orphans (1)" in out and "src/gone.md" in out
    # File row still present
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert db.get_file(conn, "src", "gone.md") is not None

    rc = run("update", "demo", "--orphans", "delete")
    assert rc == 0
    out = capsys.readouterr().out
    assert "orphans_deleted=1" in out
    out_dir = paths.collection_output_dir("demo")
    assert not (out_dir / "src" / "gone.md").exists()
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert db.get_file(conn, "src", "gone.md") is None


def test_update_ext_filter(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("md")
    (src / "b.txt").write_text("txt")
    _seed("demo", src)
    capsys.readouterr()

    rc = run("update", "demo", "--ext", "md")
    assert rc == 0
    out = capsys.readouterr().out
    assert "new=1" in out
    assert (paths.collection_output_dir("demo") / "src" / "a.md").exists()
    assert not (paths.collection_output_dir("demo") / "src" / "b.md").exists()


def test_update_dry_run_writes_nothing(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("hi")
    _seed("demo", src)
    capsys.readouterr()

    rc = run("update", "demo", "--dry-run")
    assert rc == 0
    out = capsys.readouterr().out
    assert "new=1" in out
    assert fake_docling.calls == []
    assert not (paths.collection_output_dir("demo") / "src" / "a.md").exists()
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert list(db.iter_files(conn)) == []


def test_update_records_failure(
    app_support: Path, tmp_path: Path,
    failing_docling: FailingDocling, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "boom.md").write_text("hi")
    _seed("demo", src)
    capsys.readouterr()

    rc = run("update", "demo")
    assert rc == 0
    out = capsys.readouterr().out
    assert "failed=1" in out
    with db.open_db(paths.collection_db_path("demo")) as conn:
        row = db.get_file(conn, "src", "boom.md")
    assert row.status == "failed"
    assert row.status_detail and "boom" in row.status_detail


def test_update_multi_source_isolates(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "x.md").write_text("a")
    (b / "x.md").write_text("b")
    rc = run("create", "demo", "--source", f"a={a}", "--source", f"b={b}")
    assert rc == 0
    capsys.readouterr()

    assert run("update", "demo") == 0
    out = capsys.readouterr().out
    assert "new=2" in out
    out_dir = paths.collection_output_dir("demo")
    assert (out_dir / "a" / "x.md").read_text().endswith("a")
    assert (out_dir / "b" / "x.md").read_text().endswith("b")

    # Scope to one source
    (a / "x.md").write_text("a updated")
    (b / "x.md").write_text("b updated")
    rc = run("update", "demo", "--source", "a")
    assert rc == 0
    out = capsys.readouterr().out
    # Only `a` processed
    assert "changed=1" in out
    assert "a updated" in (out_dir / "a" / "x.md").read_text()
    assert (out_dir / "b" / "x.md").read_text().endswith("b")


def test_update_video_enqueues_only(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    # Just create an empty file with a video extension; we never invoke ffprobe.
    (src / "clip.mp4").write_bytes(b"\x00")
    _seed("demo", src)
    capsys.readouterr()

    rc = run("update", "demo", "--defer-video")
    assert rc == 0
    out = capsys.readouterr().out
    assert "queued=1" in out
    with db.open_db(paths.collection_db_path("demo")) as conn:
        row = db.get_file(conn, "src", "clip.mp4")
        assert row.status == "pending"
        assert row.extractor == "mlx-whisper"
        assert db.queue_depth(conn, "pending") == 1


def test_update_passes_do_ocr_from_config(
    app_support: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("hi")
    _seed("demo", src)

    # Flip do_ocr off in the collection config.
    cfg = config.load_collection("demo")
    cfg.do_ocr = False
    config.save_collection(cfg)

    captured = {}
    def fake_get_docling(*, do_ocr: bool):
        captured["do_ocr"] = do_ocr
        return FakeDocling()
    monkeypatch.setattr(extractors, "get_docling", fake_get_docling)

    capsys.readouterr()
    rc = run("update", "demo")
    assert rc == 0
    assert captured == {"do_ocr": False}


def test_update_no_ocr_flag_overrides_collection_config(
    app_support: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """--no-ocr forces OCR off even when the collection has do_ocr=true,
    and must NOT persist back to config.json."""
    src = tmp_path / "src"; src.mkdir()
    (src / "a.md").write_text("hi")
    _seed("demo", src)

    # Collection config defaults to do_ocr=True.
    assert config.load_collection("demo").do_ocr is True

    captured: dict[str, bool] = {}
    def fake_get_docling(*, do_ocr: bool):
        captured["do_ocr"] = do_ocr
        return FakeDocling()
    monkeypatch.setattr(extractors, "get_docling", fake_get_docling)

    capsys.readouterr()
    rc = run("update", "demo", "--no-ocr")
    assert rc == 0
    assert captured == {"do_ocr": False}
    # The persisted config is untouched.
    assert config.load_collection("demo").do_ocr is True


def test_update_ocr_flag_overrides_collection_config(
    app_support: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """--ocr forces OCR on even when the collection has do_ocr=false,
    without writing back to config.json."""
    src = tmp_path / "src"; src.mkdir()
    (src / "a.md").write_text("hi")
    _seed("demo", src)

    cfg = config.load_collection("demo")
    cfg.do_ocr = False
    config.save_collection(cfg)

    captured: dict[str, bool] = {}
    def fake_get_docling(*, do_ocr: bool):
        captured["do_ocr"] = do_ocr
        return FakeDocling()
    monkeypatch.setattr(extractors, "get_docling", fake_get_docling)

    capsys.readouterr()
    rc = run("update", "demo", "--ocr")
    assert rc == 0
    assert captured == {"do_ocr": True}
    assert config.load_collection("demo").do_ocr is False


def test_update_all(
    app_support: Path, tmp_path: Path,
    fake_docling: FakeDocling, capsys: pytest.CaptureFixture[str]
):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "x.md").write_text("a")
    (b / "y.md").write_text("b")
    assert run("create", "one", "--source", f"src={a}") == 0
    assert run("create", "two", "--source", f"src={b}") == 0
    capsys.readouterr()

    rc = run("update", "--all")
    assert rc == 0
    out = capsys.readouterr().out
    assert "== one ==" in out and "== two ==" in out
