from __future__ import annotations

import os
import sys
from pathlib import Path


def default_app_support(name: str) -> Path:
    """Return the platform-appropriate default state directory for ``name``.

    - macOS: ``~/Library/Application Support/<name>``
    - Windows: ``%LOCALAPPDATA%/<name>`` (falls back to ``~/AppData/Local/<name>``)
    - Linux / other Unix: ``$XDG_DATA_HOME/<name>`` per the XDG Base Directory
      Specification (falls back to ``~/.local/share/<name>``)
    """
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


def resolve_app_support(name: str, env_override: str) -> Path:
    """Resolve the state directory, honoring an environment override.

    If the environment variable ``env_override`` is set, its value (expanded
    for ``~``) is returned. Otherwise the platform default for ``name`` is
    returned.
    """
    raw = os.environ.get(env_override)
    if raw:
        return Path(raw).expanduser()
    return default_app_support(name)
