from __future__ import annotations

import argparse
import json

from forage import config


def cmd_list(args: argparse.Namespace) -> int:
    names = config.list_collections()
    if getattr(args, "as_json", False):
        out = []
        for n in names:
            try:
                cfg = config.load_collection(n)
            except config.ConfigError:
                continue
            out.append(
                {
                    "name": n,
                    "created_at": cfg.created_at,
                    "sources": [s.to_dict() for s in cfg.sources],
                    "source_count": len(cfg.sources),
                }
            )
        print(json.dumps(out, indent=2))
        return 0

    if not names:
        print("(no collections)")
        return 0
    for n in names:
        try:
            cfg = config.load_collection(n)
        except config.ConfigError as e:
            print(f"{n}  (error: {e})")
            continue
        srcs = ", ".join(s.name for s in cfg.sources) or "(no sources)"
        print(f"{n}  [{len(cfg.sources)} source(s): {srcs}]")
    return 0
