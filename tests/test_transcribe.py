from __future__ import annotations

from pathlib import Path

import pytest

from forage import cli, config, db, extractors, paths
from forage.extractors.base import ExtractionResult, ExtractorError
from forage.extractors.whisper import NoAudioStream


def run(*argv: str) -> int:
    return cli.main(list(argv))


class FakeWhisper:
    name = "mlx-whisper"

    def __init__(self, behavior=None):
        self.behavior = behavior or (lambda src: ExtractionResult(
            markdown=f"# T\n{src.name}\n", extractor=self.name,
        ))
        self.calls: list[Path] = []

    def extract(self, src: Path) -> ExtractionResult:
        self.calls.append(src)
        return self.behavior(src)


@pytest.fixture
def fake_whisper(monkeypatch: pytest.MonkeyPatch) -> FakeWhisper:
    fake = FakeWhisper()
    monkeypatch.setattr(extractors, "_REGISTRY", {"mlx-whisper": fake})
    return fake


def _seed_video_in_queue(name: str, src_root: Path) -> Path:
    """Create a collection with one video already enqueued."""
    video = src_root / "clip.mp4"
    video.write_bytes(b"\x00")
    assert run("create", name, "--source", f"src={src_root}") == 0
    # Insert into files + queue directly to avoid invoking ffprobe in update.
    with db.open_db(paths.collection_db_path(name)) as conn:
        db.upsert_file(conn, db.FileRow(
            source="src", path="clip.mp4",
            mtime=video.stat().st_mtime, size=video.stat().st_size,
            output_path="src/clip.md", extractor="mlx-whisper",
            status="pending",
        ))
        db.enqueue(conn, "src", "clip.mp4", config.utc_now())
    return video


def test_transcribe_success(
    app_support: Path, tmp_path: Path,
    fake_whisper: FakeWhisper, capsys: pytest.CaptureFixture[str]
):
    src_root = tmp_path / "src"; src_root.mkdir()
    _seed_video_in_queue("demo", src_root)
    capsys.readouterr()

    rc = run("transcribe", "demo")
    assert rc == 0
    out = capsys.readouterr().out
    assert "done=1" in out

    md = paths.collection_output_dir("demo") / "src" / "clip.md"
    assert md.read_text().startswith("# T")
    with db.open_db(paths.collection_db_path("demo")) as conn:
        row = db.get_file(conn, "src", "clip.mp4")
        assert row.status == "ok"
        assert db.queue_depth(conn, "pending") == 0
        assert db.queue_depth(conn, "done") == 1


def test_transcribe_suspicious(
    app_support: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    src_root = tmp_path / "src"; src_root.mkdir()
    fake = FakeWhisper(behavior=lambda src: ExtractionResult(
        markdown="# Maybe\n",
        extractor="mlx-whisper",
        suspicious_reasons=["repetition: X"],
    ))
    monkeypatch.setattr(extractors, "_REGISTRY", {"mlx-whisper": fake})
    _seed_video_in_queue("demo", src_root)
    capsys.readouterr()

    rc = run("transcribe", "demo")
    assert rc == 0
    assert "suspicious=1" in capsys.readouterr().out
    with db.open_db(paths.collection_db_path("demo")) as conn:
        row = db.get_file(conn, "src", "clip.mp4")
        assert row.status == "suspicious"
        assert "repetition" in row.status_detail


def test_transcribe_no_audio(
    app_support: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    src_root = tmp_path / "src"; src_root.mkdir()
    def behavior(src):
        raise NoAudioStream(f"no audio: {src}")
    fake = FakeWhisper(behavior=behavior)
    monkeypatch.setattr(extractors, "_REGISTRY", {"mlx-whisper": fake})
    _seed_video_in_queue("demo", src_root)
    capsys.readouterr()

    rc = run("transcribe", "demo")
    assert rc == 0
    assert "no_audio=1" in capsys.readouterr().out
    with db.open_db(paths.collection_db_path("demo")) as conn:
        row = db.get_file(conn, "src", "clip.mp4")
        assert row.status == "no_audio"


def test_transcribe_failed_and_retry(
    app_support: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    src_root = tmp_path / "src"; src_root.mkdir()
    def boom(src):
        raise ExtractorError("oops")
    fake = FakeWhisper(behavior=boom)
    monkeypatch.setattr(extractors, "_REGISTRY", {"mlx-whisper": fake})
    _seed_video_in_queue("demo", src_root)
    capsys.readouterr()

    rc = run("transcribe", "demo")
    assert rc == 0
    out = capsys.readouterr().out
    assert "failed=1" in out
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert db.queue_depth(conn, "failed") == 1
    # Re-run without --retry-failed: nothing to do.
    rc = run("transcribe", "demo")
    assert rc == 0
    assert "failed=0" in capsys.readouterr().out

    # Now succeed on retry.
    monkeypatch.setattr(extractors, "_REGISTRY", {"mlx-whisper": FakeWhisper()})
    rc = run("transcribe", "demo", "--retry-failed")
    assert rc == 0
    assert "done=1" in capsys.readouterr().out


def test_transcribe_limit(
    app_support: Path, tmp_path: Path,
    fake_whisper: FakeWhisper, capsys: pytest.CaptureFixture[str]
):
    src_root = tmp_path / "src"; src_root.mkdir()
    for n in (1, 2, 3):
        (src_root / f"c{n}.mp4").write_bytes(b"\x00")
    assert run("create", "demo", "--source", f"src={src_root}") == 0
    with db.open_db(paths.collection_db_path("demo")) as conn:
        for n in (1, 2, 3):
            db.upsert_file(conn, db.FileRow(
                source="src", path=f"c{n}.mp4",
                output_path=f"src/c{n}.md", extractor="mlx-whisper",
                status="pending",
            ))
            db.enqueue(conn, "src", f"c{n}.mp4", config.utc_now())
    capsys.readouterr()

    rc = run("transcribe", "demo", "--limit", "2")
    assert rc == 0
    assert "done=2" in capsys.readouterr().out
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert db.queue_depth(conn, "pending") == 1


def test_transcribe_dry_run(
    app_support: Path, tmp_path: Path,
    fake_whisper: FakeWhisper, capsys: pytest.CaptureFixture[str]
):
    src_root = tmp_path / "src"; src_root.mkdir()
    _seed_video_in_queue("demo", src_root)
    capsys.readouterr()

    rc = run("transcribe", "demo", "--dry-run")
    assert rc == 0
    out = capsys.readouterr().out
    assert "would transcribe" in out
    # Queue untouched
    with db.open_db(paths.collection_db_path("demo")) as conn:
        assert db.queue_depth(conn, "pending") == 1
    assert fake_whisper.calls == []
