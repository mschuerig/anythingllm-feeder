from __future__ import annotations

import sys
from pathlib import Path

from _shared.appdirs import resolve_app_support

ENV_OVERRIDE = "INGEST_APP_SUPPORT"
FORAGE_ENV_OVERRIDE = "FORAGE_APP_SUPPORT"


def app_support_dir() -> Path:
    """Directory holding ingest's own state (uploads.db, logs, config)."""
    return resolve_app_support("ingest", ENV_OVERRIDE)


def forage_app_support_dir() -> Path:
    """Directory where forage keeps its state. Read-only from our side."""
    return resolve_app_support("forage", FORAGE_ENV_OVERRIDE)


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
