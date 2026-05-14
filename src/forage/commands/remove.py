from __future__ import annotations

import argparse
import shutil
import sys

from forage import config, paths
from forage.locks import collection_lock


def _resolve_files_decision(args: argparse.Namespace, prompt: str) -> bool:
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


def cmd_remove(args: argparse.Namespace) -> int:
    cfg = config.load_collection(args.name)  # raises if not found
    coll_dir = paths.collection_dir(cfg.name)
    delete = _resolve_files_decision(args, "Delete output files too? [y/N] ")

    with collection_lock(paths.collection_lock_path(cfg.name)):
        if delete:
            shutil.rmtree(coll_dir)
        else:
            # Keep output/ but discard everything else.
            for child in coll_dir.iterdir():
                if child.name == "output":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    if delete:
        print(f"removed collection {cfg.name!r} (output files deleted)")
    else:
        print(
            f"removed collection {cfg.name!r} metadata; "
            f"output retained at {coll_dir / 'output'}"
        )
    return 0
