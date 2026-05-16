from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "anythingllm-feeder"
ENV_OVERRIDE = "ANYTHINGLLM_FEEDER_APP_SUPPORT"


def default_app_support() -> Path:
    """Platform-appropriate default location for the toolkit's data root.

    - macOS: ``~/Library/Application Support/anythingllm-feeder``
    - Windows: ``%LOCALAPPDATA%/anythingllm-feeder``
      (falls back to ``~/AppData/Local/anythingllm-feeder``)
    - Linux / other Unix: ``$XDG_DATA_HOME/anythingllm-feeder`` per the XDG
      Base Directory Specification (falls back to
      ``~/.local/share/anythingllm-feeder``)

    forage and ingest both live under this single root; see ``forage.paths``
    and ``ingest.paths`` for the per-tool layout.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def app_support_dir() -> Path:
    """Return the toolkit's data root, honoring ``ANYTHINGLLM_FEEDER_APP_SUPPORT``."""
    raw = os.environ.get(ENV_OVERRIDE)
    if raw:
        return Path(raw).expanduser()
    return default_app_support()
