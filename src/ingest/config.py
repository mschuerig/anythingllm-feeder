from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from _shared.timestamps import utc_now
from ingest import paths

__all__ = [
    "ConfigError",
    "utc_now",
    "DEFAULT_BASE_URL",
    "ENV_BASE_URL",
    "ENV_API_KEY",
    "ENV_STORAGE_DIR",
    "GlobalConfig",
    "Settings",
    "load_global",
    "save_global",
    "resolve_settings",
    "workspace_slug_for",
    "resolve_anythingllm_storage_dir",
]

DEFAULT_BASE_URL = "http://localhost:3001"
ENV_BASE_URL = "ANYTHINGLLM_URL"
ENV_API_KEY = "ANYTHINGLLM_API_KEY"
ENV_STORAGE_DIR = "ANYTHINGLLM_STORAGE_DIR"


class ConfigError(Exception):
    pass


@dataclass
class GlobalConfig:
    version: int = 1
    base_url: str = DEFAULT_BASE_URL
    anythingllm_storage_dir: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "base_url": self.base_url,
                "anythingllm_storage_dir": self.anythingllm_storage_dir,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "GlobalConfig":
        d = json.loads(text)
        return cls(
            version=d.get("version", 1),
            base_url=d.get("base_url", DEFAULT_BASE_URL),
            anythingllm_storage_dir=d.get("anythingllm_storage_dir"),
        )


def load_global() -> GlobalConfig:
    p = paths.global_config_path()
    if not p.exists():
        return GlobalConfig()
    return GlobalConfig.from_json(p.read_text())


def save_global(cfg: GlobalConfig) -> None:
    p = paths.global_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cfg.to_json() + "\n")


@dataclass
class Settings:
    base_url: str
    api_key: str


def resolve_settings(
    *,
    url_override: str | None = None,
    api_key_override: str | None = None,
) -> Settings:
    """Resolve base URL and API key.

    Precedence: explicit override (e.g. CLI flag) > env var > config.json >
    built-in default. API key is required for any operation that contacts the
    server, and is never persisted to disk.
    """
    cfg = load_global()
    base_url = (
        url_override
        if url_override is not None
        else os.environ.get(ENV_BASE_URL, cfg.base_url)
    ).rstrip("/")
    api_key = (
        api_key_override
        if api_key_override is not None
        else os.environ.get(ENV_API_KEY, "")
    ).strip()
    if not api_key:
        raise ConfigError(
            f"{ENV_API_KEY} is not set. Generate a key in AnythingLLM "
            "(Settings → Developer) and export it, or pass --api-key / "
            "--api-key-file."
        )
    return Settings(base_url=base_url, api_key=api_key)


def workspace_slug_for(collection: str) -> str:
    """AnythingLLM workspace slug for a forage collection.

    Forage already validates collection names against ``^[a-z0-9][a-z0-9_-]*$``
    which is also a valid AnythingLLM slug, so this is currently the identity
    function. Keep it as the single point of truth so any future slug munging
    has one place to live.
    """
    return collection


def resolve_anythingllm_storage_dir(
    *, override: str | None = None
) -> Path | None:
    """Locate AnythingLLM's storage directory, or None if not findable.

    Resolution order:

    1. ``override`` argument (e.g. from a CLI flag), if set.
    2. ``ANYTHINGLLM_STORAGE_DIR`` environment variable, if set.
    3. ``anythingllm_storage_dir`` in our global ``config.json``, if set.
    4. The platform default from ``paths.default_anythingllm_storage_dir()``.

    Returns the resolved path only if it exists on disk. Otherwise returns
    None, and callers (e.g. status reporting) should treat the feature as
    unavailable rather than failing the whole command.
    """
    raw = override or os.environ.get(ENV_STORAGE_DIR)
    if not raw:
        cfg = load_global()
        raw = cfg.anythingllm_storage_dir or None
    candidate = (
        Path(raw).expanduser() if raw else paths.default_anythingllm_storage_dir()
    )
    return candidate if candidate.exists() else None
