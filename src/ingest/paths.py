from __future__ import annotations

import sys
from pathlib import Path

from _shared import appdirs

ENV_OVERRIDE = appdirs.ENV_OVERRIDE


def app_support_dir() -> Path:
    """The toolkit's shared data root (also used by forage)."""
    return appdirs.app_support_dir()


def global_config_path() -> Path:
    """ingest's top-level config (AnythingLLM URL, storage_dir)."""
    return app_support_dir() / "ingest" / "config.json"


def collections_dir() -> Path:
    return app_support_dir() / "collections"


def collection_dir(name: str) -> Path:
    """ingest's slice of a collection: ``collections/<name>/ingest``."""
    return collections_dir() / name / "ingest"


def uploads_db_path(name: str) -> Path:
    return collection_dir(name) / "uploads.db"


def collection_log_path(name: str) -> Path:
    return collection_dir(name) / "ingest.log"


def forage_collection_dir(name: str) -> Path:
    """forage's slice of a collection. Read-only from ingest's side."""
    return collections_dir() / name / "forage"


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
    return Path("/nonexistent/anythingllm/storage")
