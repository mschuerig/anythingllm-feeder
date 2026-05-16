from __future__ import annotations

import argparse

from forage import config, paths
from forage.locks import collection_lock


def cmd_rename(args: argparse.Namespace) -> int:
    old_name = args.old_name
    new_name = args.new_name
    if old_name == new_name:
        raise config.ConfigError("old and new names are identical")
    config.validate_name(new_name, "collection name")
    if not config.collection_exists(old_name):
        raise config.ConfigError(f"collection {old_name!r} not found")
    if config.collection_exists(new_name):
        raise config.ConfigError(f"collection {new_name!r} already exists")

    with collection_lock(paths.collection_lock_path(old_name)):
        old_dir = paths.collection_dir(old_name)
        new_dir = paths.collection_dir(new_name)
        old_dir.rename(new_dir)
        cfg = config.load_collection(new_name)
        cfg.name = new_name
        config.save_collection(cfg)
    print(f"renamed {old_name!r} -> {new_name!r}")
    return 0
