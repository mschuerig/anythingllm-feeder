from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from forage import config, db, paths


def _dir_size(root: Path) -> int:
    """Total size in bytes of all regular files under `root`, recursively.

    Returns 0 if the path does not exist. Symlinks are not followed.
    """
    if not root.exists():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except FileNotFoundError:
                # File vanished between scan and stat; ignore.
                continue
    return total


def _file_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except FileNotFoundError:
        return 0


def _human_bytes(n: int) -> str:
    """Format a byte count using binary (IEC) units."""
    if n < 1024:
        return f"{n} B"
    units = ("KiB", "MiB", "GiB", "TiB", "PiB")
    value = float(n)
    for unit in units:
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} EiB"


def cmd_info(args: argparse.Namespace) -> int:
    cfg = config.load_collection(args.name)
    with db.open_db(paths.collection_db_path(args.name)) as conn:
        db.init_schema(conn)
        totals = db.status_counts(conn)
        per_source = {s.name: db.status_counts(conn, s.name) for s in cfg.sources}
        pending_q = db.queue_depth(conn, "pending")
        failures = db.recent_failures(conn, 10)
        suspicious = db.recent_suspicious(conn, 10)

    coll_dir = paths.collection_dir(cfg.name)
    output_dir = paths.collection_output_dir(cfg.name)
    per_source_bytes = {
        s.name: _dir_size(paths.source_output_dir(cfg.name, s.name))
        for s in cfg.sources
    }
    output_bytes = _dir_size(output_dir)
    db_bytes = _file_size(paths.collection_db_path(cfg.name))
    log_bytes = _file_size(paths.collection_log_path(cfg.name))
    total_bytes = _dir_size(coll_dir)

    if getattr(args, "as_json", False):
        out = {
            "name": cfg.name,
            "created_at": cfg.created_at,
            "output_dir": str(output_dir),
            "sources": [
                {
                    **s.to_dict(),
                    "status_counts": per_source.get(s.name, {}),
                    "output_bytes": per_source_bytes.get(s.name, 0),
                }
                for s in cfg.sources
            ],
            "totals": totals,
            "pending_queue": pending_q,
            "recent_failures": [
                {"source": f.source, "path": f.path, "detail": f.status_detail}
                for f in failures
            ],
            "recent_suspicious": [
                {"source": f.source, "path": f.path, "detail": f.status_detail}
                for f in suspicious
            ],
            "storage_bytes": {
                "total": total_bytes,
                "output": output_bytes,
                "db": db_bytes,
                "log": log_bytes,
            },
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"collection: {cfg.name}")
    print(f"created:    {cfg.created_at}")
    print(f"output:     {output_dir}")
    print(f"sources ({len(cfg.sources)}):")
    for s in cfg.sources:
        counts = per_source.get(s.name, {})
        c = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "(empty)"
        print(f"  - {s.name}: {s.path}")
        print(f"      {c}")
        print(f"      output: {_human_bytes(per_source_bytes.get(s.name, 0))}")
    if totals:
        print("totals: " + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())))
    print(f"pending queue: {pending_q}")
    print(
        f"storage: {_human_bytes(total_bytes)} total "
        f"(output {_human_bytes(output_bytes)}, "
        f"db {_human_bytes(db_bytes)}, "
        f"log {_human_bytes(log_bytes)})"
    )
    if failures:
        print(f"recent failures ({len(failures)}):")
        for f in failures:
            print(f"  - {f.source}/{f.path}: {f.status_detail or ''}")
    if suspicious:
        print(f"recent suspicious ({len(suspicious)}):")
        for f in suspicious:
            print(f"  - {f.source}/{f.path}: {f.status_detail or ''}")
    return 0
