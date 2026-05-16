from __future__ import annotations

from pathlib import Path

import pytest

from ingest.cli import main


def _seed_ingest_collection(root: Path, name: str) -> None:
    coll = root / "collections" / name / "ingest"
    coll.mkdir(parents=True)
    (coll / "uploads.db").write_bytes(b"")
    (coll / "ingest.log").write_text("")


def test_purge_removes_toolkit_root(app_support: Path) -> None:
    _seed_ingest_collection(app_support, "news")
    (app_support / "ingest").mkdir(exist_ok=True)
    (app_support / "ingest" / "config.json").write_text("{}")

    rc = main(["purge", "--yes"])

    assert rc == 0
    assert not app_support.exists()


def test_purge_with_no_state_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "absent"
    monkeypatch.setenv("ANYTHINGLLM_FEEDER_APP_SUPPORT", str(target))

    rc = main(["purge", "--yes"])

    assert rc == 0
    assert not target.exists()


def test_purge_refuses_without_yes_when_non_interactive(
    app_support: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_ingest_collection(app_support, "news")

    rc = main(["purge"])

    assert rc == 2
    assert app_support.exists()
    err = capsys.readouterr().err
    assert "--yes" in err


def test_purge_uses_send2trash(
    app_support: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def _capture(path: str) -> None:
        calls.append(str(path))

    monkeypatch.setattr("ingest.commands.purge.send2trash", _capture)
    _seed_ingest_collection(app_support, "news")

    rc = main(["purge", "--yes"])

    assert rc == 0
    assert calls == [str(app_support)]
    assert app_support.exists()
