from __future__ import annotations

import argparse
import sys
from pathlib import Path

from forage import config, db, paths


def _validate_source_path(p: Path) -> None:
    if not p.exists():
        raise config.ConfigError(f"source path does not exist: {p}")
    if not p.is_dir():
        raise config.ConfigError(f"source path is not a directory: {p}")


def cmd_create(args: argparse.Namespace) -> int:
    config.validate_name(args.name, "collection name")
    if config.collection_exists(args.name):
        print(f"error: collection {args.name!r} already exists", file=sys.stderr)
        return 1

    sources: list[config.Source] = []
    seen: set[str] = set()
    for raw in args.source:
        name, path = config.parse_source_arg(raw)
        if name in seen:
            raise config.ConfigError(f"duplicate source name {name!r}")
        seen.add(name)
        _validate_source_path(path)
        sources.append(
            config.Source(name=name, path=str(path), created_at=config.utc_now())
        )

    coll_dir = paths.collection_dir(args.name)
    coll_dir.mkdir(parents=True, exist_ok=False)
    paths.collection_output_dir(args.name).mkdir(parents=True, exist_ok=True)
    for s in sources:
        paths.source_output_dir(args.name, s.name).mkdir(parents=True, exist_ok=True)

    cfg = config.CollectionConfig(
        name=args.name, sources=sources, created_at=config.utc_now()
    )
    config.save_collection(cfg)
    with db.open_db(paths.collection_db_path(args.name)) as conn:
        db.init_schema(conn)
    print(f"created collection {args.name!r} at {coll_dir}")
    for s in sources:
        print(f"  source {s.name}: {s.path}")
    return 0
