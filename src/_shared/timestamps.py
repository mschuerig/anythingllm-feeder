from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> str:
    """ISO 8601 UTC timestamp with second precision, e.g. ``2026-05-16T12:34:56Z``."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
