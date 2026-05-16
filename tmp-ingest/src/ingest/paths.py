from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_OVERRIDE = "INGEST_APP_SUPPORT"
FORAGE_ENV_OVERRIDE = "FORAGE_APP_SUPPORT"


def _default_app_support(name: str) -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / name
        return Path.home() / "AppData" / "Local" / name
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / name
    return Path.home() / ".local" / "share" / name


def app_support_dir() -> Path:
    """Directory holding ingest's own state (uploads.db, logs, config)."""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    return _default_app_support("ingest")


def forage_app_support_dir() -> Path:
    """Directory where forage keeps its state. Read-only from our side."""
    override = os.environ.get(FORAGE_ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    return _default_app_support("forage")


def global_config_path() -> Path:
    return app_support_dir() / "config.json"


def collections_dir() -> Path:
    return app_support_dir() / "collections"


def collection_dir(name: str) -> Path:
    return collections_dir() / name


def uploads_db_path(name: str) -> Path:
    return collection_dir(name) / "uploads.db"


def collection_log_path(name: str) -> Path:
    return collection_dir(name) / "ingest.log"


def forage_collection_dir(name: str) -> Path:
    return forage_app_support_dir() / "collections" / name


def forage_collection_db_path(name: str) -> Path:
    return forage_collection_dir(name) / "state.db"


def forage_collection_output_dir(name: str) -> Path:
    return forage_collection_dir(name) / "output"


def forage_collection_config_path(name: str) -> Path:
    return forage_collection_dir(name) / "config.json"


ANYTHINGLLM_STORAGE_ENV = "ANYTHINGLLM_STORAGE_DIR"


def default_anythingllm_storage_dir() -> Path:
    """Best-guess path to AnythingLLM's `storage/` directory.

    The macOS desktop app keeps everything under
    ``~/Library/Application Support/anythingllm-desktop/storage/``.
    Other installations (Docker, server, Linux desktop) live elsewhere and
    must override via config or env. We only know how to guess for macOS
    desktop; on other platforms the resolver returns a placeholder that
    will simply fail the `exists()` check and the caller will skip.
    """
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "anythingllm-desktop"
            / "storage"
        )
    # No reliable default elsewhere; resolve_anythingllm_storage_dir will
    # treat a non-existing path as "not configured".
    return Path("/nonexistent/anythingllm/storage")
