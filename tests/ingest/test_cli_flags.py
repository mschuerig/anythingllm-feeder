from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ingest import anythingllm, config
from ingest.cli import main


def test_resolve_settings_cli_overrides_env_and_config(
    ingest_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANYTHINGLLM_URL", "http://from-env:1")
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "env-key")
    settings = config.resolve_settings(
        url_override="http://from-flag:2", api_key_override="flag-key"
    )
    assert settings.base_url == "http://from-flag:2"
    assert settings.api_key == "flag-key"


def test_resolve_settings_env_wins_when_no_override(
    ingest_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANYTHINGLLM_URL", "http://from-env:1")
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "env-key")
    settings = config.resolve_settings()
    assert settings.base_url == "http://from-env:1"
    assert settings.api_key == "env-key"


def test_resolve_settings_strips_trailing_slash_on_override(
    ingest_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "k")
    settings = config.resolve_settings(url_override="http://x:9/")
    assert settings.base_url == "http://x:9"


def test_resolve_settings_missing_key_after_override(
    ingest_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="--api-key"):
        config.resolve_settings()


def test_resolve_storage_dir_override_wins(
    ingest_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_dir = tmp_path / "from-env"
    env_dir.mkdir()
    flag_dir = tmp_path / "from-flag"
    flag_dir.mkdir()
    monkeypatch.setenv("ANYTHINGLLM_STORAGE_DIR", str(env_dir))
    resolved = config.resolve_anythingllm_storage_dir(override=str(flag_dir))
    assert resolved == flag_dir


def test_resolve_timeout_override_wins() -> None:
    t = anythingllm.resolve_timeout(io_timeout_override=42.0)
    assert t.read == 42.0
    assert t.connect == anythingllm.DEFAULT_CONNECT_TIMEOUT


def test_api_key_file_is_read_in(
    ingest_home: Path,
    forage_home: Path,
    tmp_path: Path,
    fake_server,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--api-key-file` should read the file, strip trailing whitespace,
    and not trigger the --api-key security note."""
    key_file = tmp_path / "key"
    key_file.write_text("test-key\n")
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    monkeypatch.setenv("ANYTHINGLLM_URL", "http://localhost:0")

    # Patch the client so cmd_check uses our fake transport.
    import ingest.commands.check as check_mod

    real_client = anythingllm.AnythingLLMClient

    def factory(**kw):
        return real_client(
            transport=httpx.MockTransport(fake_server.handle), **kw
        )

    monkeypatch.setattr(check_mod, "AnythingLLMClient", factory)

    rc = main(["check", "--api-key-file", str(key_file)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "shell history" not in err  # security note must NOT fire


def test_api_key_file_missing_errors(
    ingest_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["check", "--api-key-file", "/nonexistent/key"])
    assert rc == 1
    assert "could not read --api-key-file" in capsys.readouterr().err


def test_api_key_file_empty_errors(
    ingest_home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.write_text("   \n")
    rc = main(["check", "--api-key-file", str(empty)])
    assert rc == 1
    assert "is empty" in capsys.readouterr().err


def test_inline_api_key_prints_security_note(
    ingest_home: Path,
    forage_home: Path,
    fake_server,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    monkeypatch.setenv("ANYTHINGLLM_URL", "http://localhost:0")
    import ingest.commands.check as check_mod
    real_client = anythingllm.AnythingLLMClient

    def factory(**kw):
        return real_client(
            transport=httpx.MockTransport(fake_server.handle), **kw
        )

    monkeypatch.setattr(check_mod, "AnythingLLMClient", factory)

    rc = main(["check", "--api-key", "test-key"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "shell history" in err


def test_inline_api_key_note_suppressed_under_quiet(
    ingest_home: Path,
    forage_home: Path,
    fake_server,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    monkeypatch.setenv("ANYTHINGLLM_URL", "http://localhost:0")
    import ingest.commands.check as check_mod
    real_client = anythingllm.AnythingLLMClient

    def factory(**kw):
        return real_client(
            transport=httpx.MockTransport(fake_server.handle), **kw
        )

    monkeypatch.setattr(check_mod, "AnythingLLMClient", factory)

    rc = main(["-q", "check", "--api-key", "test-key"])
    assert rc == 0
    assert "shell history" not in capsys.readouterr().err
