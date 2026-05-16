from __future__ import annotations

from pathlib import Path

from _shared import appdirs

ENV_OVERRIDE = appdirs.ENV_OVERRIDE


def app_support_dir() -> Path:
    """The toolkit's shared data root (also used by ingest)."""
    return appdirs.app_support_dir()


def global_config_path() -> Path:
    """forage's top-level config (whisper_model, defaults)."""
    return app_support_dir() / "forage" / "config.json"


def collections_dir() -> Path:
    """Shared collections root: ``<toolkit>/collections``."""
    return app_support_dir() / "collections"


def collection_dir(name: str) -> Path:
    """forage's slice of a collection: ``collections/<name>/forage``."""
    return collections_dir() / name / "forage"


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
