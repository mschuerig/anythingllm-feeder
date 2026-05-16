from __future__ import annotations

from pathlib import Path

import pytest

from forage import paths


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ANYTHINGLLM_FEEDER_APP_SUPPORT", "XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.delenv(k, raising=False)


def test_default_on_macos(monkeypatch: pytest.MonkeyPatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr("sys.platform", "darwin")
    assert paths.app_support_dir() == (
        Path.home() / "Library" / "Application Support" / "anythingllm-feeder"
    )


def test_default_on_linux_uses_xdg_default(monkeypatch: pytest.MonkeyPatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr("sys.platform", "linux")
    assert paths.app_support_dir() == (
        Path.home() / ".local" / "share" / "anythingllm-feeder"
    )


def test_default_on_linux_respects_xdg_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _clear_env(monkeypatch)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert paths.app_support_dir() == tmp_path / "xdg" / "anythingllm-feeder"


def test_default_on_windows_uses_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _clear_env(monkeypatch)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.app_support_dir() == tmp_path / "Local" / "anythingllm-feeder"


def test_default_on_windows_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch
):
    _clear_env(monkeypatch)
    monkeypatch.setattr("sys.platform", "win32")
    assert paths.app_support_dir() == (
        Path.home() / "AppData" / "Local" / "anythingllm-feeder"
    )


def test_env_override_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("ANYTHINGLLM_FEEDER_APP_SUPPORT", str(tmp_path / "explicit"))
    assert paths.app_support_dir() == tmp_path / "explicit"


def test_collection_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """forage state lives under collections/<name>/forage/."""
    monkeypatch.setenv("ANYTHINGLLM_FEEDER_APP_SUPPORT", str(tmp_path / "root"))
    assert paths.collection_dir("news") == tmp_path / "root" / "collections" / "news" / "forage"
    assert paths.collection_db_path("news") == (
        tmp_path / "root" / "collections" / "news" / "forage" / "state.db"
    )
    assert paths.global_config_path() == tmp_path / "root" / "forage" / "config.json"
