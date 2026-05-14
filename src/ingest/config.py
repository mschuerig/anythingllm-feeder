from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from ingest import paths

DEFAULT_BASE_URL = "http://localhost:3001"
ENV_BASE_URL = "ANYTHINGLLM_URL"
ENV_API_KEY = "ANYTHINGLLM_API_KEY"


class ConfigError(Exception):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


@dataclass
class GlobalConfig:
    version: int = 1
    base_url: str = DEFAULT_BASE_URL
    workspace_prefix: str = "forage-"

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "base_url": self.base_url,
                "workspace_prefix": self.workspace_prefix,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "GlobalConfig":
        d = json.loads(text)
        return cls(
            version=d.get("version", 1),
            base_url=d.get("base_url", DEFAULT_BASE_URL),
            workspace_prefix=d.get("workspace_prefix", "forage-"),
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
    workspace_prefix: str


def resolve_settings() -> Settings:
    """Resolve base URL, API key, and workspace prefix from config + env.

    Env vars override config. API key is required and never persisted to disk.
    """
    cfg = load_global()
    base_url = os.environ.get(ENV_BASE_URL, cfg.base_url).rstrip("/")
    api_key = os.environ.get(ENV_API_KEY, "").strip()
    if not api_key:
        raise ConfigError(
            f"{ENV_API_KEY} is not set. Generate a key in AnythingLLM "
            "(Settings → Developer) and export it."
        )
    return Settings(
        base_url=base_url,
        api_key=api_key,
        workspace_prefix=cfg.workspace_prefix,
    )


def workspace_slug_for(collection: str, *, prefix: str) -> str:
    """Derive an AnythingLLM workspace slug for a forage collection."""
    return f"{prefix}{collection}"
