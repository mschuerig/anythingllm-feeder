from __future__ import annotations

import os
from pathlib import Path

DEFAULT_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "forage"
ENV_OVERRIDE = "FORAGE_APP_SUPPORT"


def app_support_dir() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    return DEFAULT_APP_SUPPORT


def global_config_path() -> Path:
    return app_support_dir() / "config.json"


def collections_dir() -> Path:
    return app_support_dir() / "collections"


def collection_dir(name: str) -> Path:
    return collections_dir() / name


def collection_config_path(name: str) -> Path:
    return collection_dir(name) / "config.json"


def collection_db_path(name: str) -> Path:
    return collection_dir(name) / "state.db"


def collection_log_path(name: str) -> Path:
    return collection_dir(name) / "extract.log"


def collection_output_dir(name: str) -> Path:
    return collection_dir(name) / "output"


def collection_lock_path(name: str) -> Path:
    return collection_dir(name) / ".lock"


def source_output_dir(collection: str, source: str) -> Path:
    return collection_output_dir(collection) / source
