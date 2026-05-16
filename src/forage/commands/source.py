from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from forage import config, db, paths
from forage.locks import collection_lock


def _validate_dir(p: Path) -> None:
    if not p.exists():
        raise config.ConfigError(f"directory does not exist: {p}")
    if not p.is_dir():
        raise config.ConfigError(f"not a directory: {p}")


def cmd_add_source(args: argparse.Namespace) -> int:
    cfg = config.load_collection(args.collection)
    config.validate_name(args.name, "source name")
    if cfg.source(args.name) is not None:
        raise config.ConfigError(
            f"source {args.name!r} already exists in collection {cfg.name!r}"
        )
    new_path = Path(args.dir).expanduser().resolve()
    _validate_dir(new_path)
    with collection_lock(paths.collection_lock_path(cfg.name)):
        cfg.sources.append(
            config.Source(
                name=args.name, path=str(new_path), created_at=config.utc_now()
            )
        )
        config.save_collection(cfg)
        paths.source_output_dir(cfg.name, args.name).mkdir(
            parents=True, exist_ok=True
        )
    print(
        f"added source {args.name!r} ({new_path}) to collection {cfg.name!r}"
    )
    return 0


def _resolve_files_decision(
    args: argparse.Namespace, prompt: str
) -> bool:
    """Return True to delete files, False to keep them."""
    if args.delete_files:
        return True
    if args.keep_files:
        return False
    if not sys.stdin.isatty():
        raise config.ConfigError(
            "non-interactive run: pass --delete-files or --keep-files"
        )
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        ans = ""
    return ans in {"y", "yes"}


def cmd_remove_source(args: argparse.Namespace) -> int:
    cfg = config.load_collection(args.collection)
    src = cfg.source(args.name)
    if src is None:
        raise config.ConfigError(
            f"source {args.name!r} not found in collection {cfg.name!r}"
        )

    delete = _resolve_files_decision(
        args, f"Delete output files for source {args.name!r}? [y/N] "
    )

    with collection_lock(paths.collection_lock_path(cfg.name)):
        out_dir = paths.source_output_dir(cfg.name, args.name)
        if delete and out_dir.exists():
            shutil.rmtree(out_dir)
        cfg.sources = [s for s in cfg.sources if s.name != args.name]
        config.save_collection(cfg)
        db_path = paths.collection_db_path(cfg.name)
        if db_path.exists():
            with db.open_db(db_path) as conn:
                n = db.delete_source_rows(conn, args.name)
        else:
            n = 0
    print(
        f"removed source {args.name!r} from {cfg.name!r}: "
        f"{n} row(s) dropped, output {'deleted' if delete else 'kept'}"
    )
    return 0


def cmd_set_source(args: argparse.Namespace) -> int:
    cfg = config.load_collection(args.collection)
    src = cfg.source(args.name)
    if src is None:
        raise config.ConfigError(
            f"source {args.name!r} not found in collection {cfg.name!r}"
        )
    new_path = Path(args.new_dir).expanduser().resolve()
    _validate_dir(new_path)
    with collection_lock(paths.collection_lock_path(cfg.name)):
        src.path = str(new_path)
        config.save_collection(cfg)
    print(
        f"set source {args.name!r} of {cfg.name!r} to {new_path}"
    )
    return 0
