from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def app_support(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect FORAGE_APP_SUPPORT to a per-test temp directory."""
    target = tmp_path / "forage"
    target.mkdir()
    monkeypatch.setenv("FORAGE_APP_SUPPORT", str(target))
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
