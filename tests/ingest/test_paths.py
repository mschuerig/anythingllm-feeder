from __future__ import annotations

from pathlib import Path

import pytest

from ingest import paths


def test_app_support_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("INGEST_APP_SUPPORT", str(tmp_path / "custom"))
    assert paths.app_support_dir() == tmp_path / "custom"


def test_forage_app_support_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FORAGE_APP_SUPPORT", str(tmp_path / "fcustom"))
    assert paths.forage_app_support_dir() == tmp_path / "fcustom"


def test_derived_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("INGEST_APP_SUPPORT", str(tmp_path / "i"))
    monkeypatch.setenv("FORAGE_APP_SUPPORT", str(tmp_path / "f"))
    assert paths.uploads_db_path("c1") == tmp_path / "i" / "collections" / "c1" / "uploads.db"
    assert (
        paths.forage_collection_db_path("c1")
        == tmp_path / "f" / "collections" / "c1" / "state.db"
    )
