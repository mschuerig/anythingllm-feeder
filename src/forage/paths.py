from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_OVERRIDE = "FORAGE_APP_SUPPORT"


def _default_app_support() -> Path:
    """Return the platform-appropriate default state directory.

    - macOS: ``~/Library/Application Support/forage``
    - Windows: ``%LOCALAPPDATA%/forage`` (falls back to ``~/AppData/Local/forage``)
    - Linux / other Unix: ``$XDG_DATA_HOME/forage`` per the XDG Base Directory
      Specification (falls back to ``~/.local/share/forage``)
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "forage"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "forage"
        return Path.home() / "AppData" / "Local" / "forage"
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "forage"
    return Path.home() / ".local" / "share" / "forage"


def app_support_dir() -> Path:
    """Return the directory holding all forage state.

    Honors the ``FORAGE_APP_SUPPORT`` environment variable for overrides
    (used by the test suite); otherwise falls back to the platform default.
    """
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    return _default_app_support()


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
