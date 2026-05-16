from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_real_trash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``send2trash`` with ``shutil.rmtree`` for the whole forage suite.

    Without this, any test that exercises the purge code path (directly or
    indirectly) would deposit fixture dirs in the developer's actual Trash.
    """
    import shutil

    def _fake_send2trash(path: str | Path) -> None:
        shutil.rmtree(path)

    monkeypatch.setattr(
        "forage.commands.purge.send2trash", _fake_send2trash
    )


@pytest.fixture
def app_support(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ANYTHINGLLM_FEEDER_APP_SUPPORT to a per-test toolkit root."""
    target = tmp_path / "anythingllm-feeder"
    target.mkdir()
    monkeypatch.setenv("ANYTHINGLLM_FEEDER_APP_SUPPORT", str(target))
    return target


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    """Create a small synthetic source tree with a handful of text files."""
    root = tmp_path / "src"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "a" / "note.md").write_text("# hello\n")
    (root / "a" / "plain.txt").write_text("plain\n")
    (root / "b" / "deep" / "x").mkdir(parents=True)
    (root / "b" / "deep" / "x" / "doc.md").write_text("nested\n")
    return root
