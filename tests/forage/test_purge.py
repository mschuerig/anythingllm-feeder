from __future__ import annotations

from pathlib import Path

import pytest

from forage import paths
from forage.cli import main
from forage.locks import collection_lock


def _seed_collection(app_support: Path, name: str) -> Path:
    """Create a forage slice of a collection in the new layout."""
    coll = app_support / "collections" / name / "forage"
    (coll / "output" / "src").mkdir(parents=True)
    (coll / "output" / "src" / "doc.md").write_text("hi\n")
    (coll / "state.db").write_bytes(b"")
    (coll / "config.json").write_text("{}")
    return coll


def test_purge_removes_toolkit_root(app_support: Path) -> None:
    _seed_collection(app_support, "news")
    (app_support / "forage" / "config.json").parent.mkdir(parents=True, exist_ok=True)
    (app_support / "forage" / "config.json").write_text("{}")
    (app_support / "ingest" / "config.json").parent.mkdir(parents=True, exist_ok=True)
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


def test_purge_refuses_when_collection_locked(
    app_support: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    coll = _seed_collection(app_support, "news")

    with collection_lock(coll / ".lock"):
        rc = main(["purge", "--yes"])

    assert rc == 2
    assert app_support.exists()  # nothing removed
    err = capsys.readouterr().err
    assert "in use" in err
    assert "news" in err


def test_purge_refuses_without_yes_when_non_interactive(
    app_support: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_collection(app_support, "news")

    # stdin is not a TTY under pytest; without --yes this should bail.
    rc = main(["purge"])

    assert rc == 2
    assert app_support.exists()
    err = capsys.readouterr().err
    assert "--yes" in err


def test_purge_prints_summary(
    app_support: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_collection(app_support, "news")
    _seed_collection(app_support, "papers")

    rc = main(["purge", "--yes"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "2 collection(s)" in out
    assert "news" in out
    assert "papers" in out
    assert "Trash" in out
    assert "huggingface" in out
    assert "NOT removed" in out


def test_purge_uses_send2trash(
    app_support: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fake send2trash is installed by the autouse fixture; verify call."""
    calls: list[str] = []

    def _capture(path: str) -> None:
        calls.append(str(path))
        # Don't actually remove; assert and let test cleanup handle it.

    monkeypatch.setattr("forage.commands.purge.send2trash", _capture)
    _seed_collection(app_support, "news")

    rc = main(["purge", "--yes"])

    assert rc == 0
    assert calls == [str(app_support)]
    assert app_support.exists()  # not actually removed by our stub
