from __future__ import annotations

import argparse
import json
import sys

from ingest import config, log
from ingest.anythingllm import (
    AnythingLLMClient,
    AnythingLLMError,
    resolve_timeout,
)

_log = log.get_logger()


def cmd_check(args: argparse.Namespace) -> int:
    """Probe the local AnythingLLM and confirm the API key works."""
    try:
        settings = config.resolve_settings(
            url_override=getattr(args, "url", None),
            api_key_override=getattr(args, "api_key", None),
        )
    except config.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    as_json = getattr(args, "as_json", False)
    payload: dict[str, object] = {
        "base_url": settings.base_url,
    }
    try:
        with AnythingLLMClient(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=resolve_timeout(getattr(args, "http_timeout", None)),
        ) as client:
            client.auth_check()
            workspaces = client.list_workspaces()
    except AnythingLLMError as exc:
        payload["ok"] = False
        payload["error"] = str(exc)
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    payload["ok"] = True
    payload["workspaces"] = [
        {"slug": w.slug, "name": w.name} for w in workspaces
    ]
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"AnythingLLM at {settings.base_url}: ok")
        print(f"workspaces: {len(workspaces)}")
        for w in workspaces:
            print(f"  - {w.slug}  ({w.name})")
    return 0
