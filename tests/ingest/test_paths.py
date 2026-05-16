from __future__ import annotations

from pathlib import Path

import pytest

from ingest import paths


def test_app_support_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANYTHINGLLM_FEEDER_APP_SUPPORT", str(tmp_path / "custom"))
    assert paths.app_support_dir() == tmp_path / "custom"


def test_derived_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANYTHINGLLM_FEEDER_APP_SUPPORT", str(tmp_path / "root"))
    assert paths.uploads_db_path("c1") == (
        tmp_path / "root" / "collections" / "c1" / "ingest" / "uploads.db"
    )
    assert paths.forage_collection_db_path("c1") == (
        tmp_path / "root" / "collections" / "c1" / "forage" / "state.db"
    )
    assert paths.global_config_path() == tmp_path / "root" / "ingest" / "config.json"
