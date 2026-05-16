from __future__ import annotations

import argparse
import sys

from ingest import config, forage_db, log, paths
from ingest.anythingllm import AnythingLLMClient, AnythingLLMError, resolve_timeout
from ingest.sync import sync_collection

_log = log.get_logger()


def _sync_one(
    name: str,
    *,
    settings: config.Settings,
    include_suspicious: bool,
    keep_orphans: bool,
    dry_run: bool,
    http_timeout: float | None,
) -> int:
    log_handler = None
    log_path = paths.collection_log_path(name)
    client: AnythingLLMClient | None = None
    try:
        log_handler = log.add_collection_log(log_path)
        if not dry_run:
            client = AnythingLLMClient(
                base_url=settings.base_url,
                api_key=settings.api_key,
                timeout=resolve_timeout(http_timeout),
            )
        result = sync_collection(
            name,
            client=client,
            include_suspicious=include_suspicious,
            keep_orphans=keep_orphans,
            dry_run=dry_run,
        )
    except forage_db.ForageStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except AnythingLLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
        if log_handler is not None:
            log.remove_handler(log_handler)

    _log.info(
        "%s: uploaded=%d changed=%d unchanged=%d orphans_deleted=%d "
        "orphans_kept=%d reconciled=%d failed=%d",
        name,
        result.uploaded,
        result.changed,
        result.unchanged,
        result.orphans_deleted,
        result.orphans_kept,
        result.reconciled,
        result.failed,
    )
    return 0 if result.failed == 0 else 2


def cmd_sync(args: argparse.Namespace) -> int:
    include_suspicious: bool = getattr(args, "include_suspicious", False)
    keep_orphans: bool = getattr(args, "keep_orphans", False)
    dry_run: bool = getattr(args, "dry_run", False)
    all_collections: bool = getattr(args, "all_collections", False)

    http_timeout: float | None = getattr(args, "http_timeout", None)
    try:
        settings = config.resolve_settings(
            url_override=getattr(args, "url", None),
            api_key_override=getattr(args, "api_key", None),
        )
    except config.ConfigError as exc:
        if dry_run:
            # dry-run does not contact the server; tolerate a missing API key
            settings = config.Settings(
                base_url="(dry-run)", api_key="(dry-run)"
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if all_collections:
        forage_root = paths.forage_app_support_dir() / "collections"
        if not forage_root.exists():
            print("no forage collections found", file=sys.stderr)
            return 0
        names = sorted(
            p.name
            for p in forage_root.iterdir()
            if p.is_dir() and (p / "config.json").exists()
        )
        rc = 0
        for n in names:
            code = _sync_one(
                n,
                settings=settings,
                include_suspicious=include_suspicious,
                keep_orphans=keep_orphans,
                dry_run=dry_run,
                http_timeout=http_timeout,
            )
            rc = max(rc, code)
        return rc

    name: str | None = args.name
    if not name:
        print("error: collection name required (or pass --all)", file=sys.stderr)
        return 2
    return _sync_one(
        name,
        settings=settings,
        include_suspicious=include_suspicious,
        keep_orphans=keep_orphans,
        dry_run=dry_run,
        http_timeout=http_timeout,
    )
