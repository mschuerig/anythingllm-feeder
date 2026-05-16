from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from forage import paths

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ConfigError(Exception):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def validate_name(name: str, kind: str = "name") -> None:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ConfigError(
            f"invalid {kind} {name!r}: must match {NAME_RE.pattern} "
            "(lowercase letters/digits/'-'/'_', starting with a letter or digit)"
        )


@dataclass
class Source:
    name: str
    path: str
    created_at: str

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(name=d["name"], path=d["path"], created_at=d["created_at"])

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CollectionConfig:
    name: str
    sources: list[Source] = field(default_factory=list)
    created_at: str = ""
    version: int = 1
    do_ocr: bool = True

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "name": self.name,
                "created_at": self.created_at,
                "do_ocr": self.do_ocr,
                "sources": [s.to_dict() for s in self.sources],
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "CollectionConfig":
        d = json.loads(text)
        return cls(
            name=d["name"],
            sources=[Source.from_dict(s) for s in d.get("sources", [])],
            created_at=d.get("created_at", ""),
            version=d.get("version", 1),
            do_ocr=bool(d.get("do_ocr", True)),
        )

    def source(self, name: str) -> Source | None:
        return next((s for s in self.sources if s.name == name), None)


@dataclass
class GlobalConfig:
    version: int = 1
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    defaults: dict = field(default_factory=lambda: {"orphans": "list"})

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "whisper_model": self.whisper_model,
                "defaults": self.defaults,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "GlobalConfig":
        d = json.loads(text)
        return cls(
            version=d.get("version", 1),
            whisper_model=d.get(
                "whisper_model", "mlx-community/whisper-large-v3-turbo"
            ),
            defaults=d.get("defaults", {"orphans": "list"}),
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


def load_collection(name: str) -> CollectionConfig:
    p = paths.collection_config_path(name)
    if not p.exists():
        raise ConfigError(f"collection {name!r} not found at {p}")
    return CollectionConfig.from_json(p.read_text())


def save_collection(cfg: CollectionConfig) -> None:
    p = paths.collection_config_path(cfg.name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cfg.to_json() + "\n")


def list_collections() -> list[str]:
    root = paths.collections_dir()
    if not root.exists():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and (p / "config.json").exists()
    )


def collection_exists(name: str) -> bool:
    return paths.collection_config_path(name).exists()


def parse_source_arg(value: str) -> tuple[str, Path]:
    """Parse a `--source name=path` argument."""
    if "=" not in value:
        raise ConfigError(f"--source must be in name=path form, got {value!r}")
    name, _, raw_path = value.partition("=")
    name = name.strip()
    raw_path = raw_path.strip()
    if not name:
        raise ConfigError(f"--source {value!r}: empty name")
    if not raw_path:
        raise ConfigError(f"--source {value!r}: empty path")
    validate_name(name, "source name")
    return name, Path(raw_path).expanduser().resolve()
