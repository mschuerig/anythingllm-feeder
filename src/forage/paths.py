from __future__ import annotations

from pathlib import Path

from _shared.appdirs import resolve_app_support

ENV_OVERRIDE = "FORAGE_APP_SUPPORT"


def app_support_dir() -> Path:
    """Return the directory holding all forage state.

    Honors the ``FORAGE_APP_SUPPORT`` environment variable for overrides
    (used by the test suite); otherwise falls back to the platform default.
    """
    return resolve_app_support("forage", ENV_OVERRIDE)


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
