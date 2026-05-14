from __future__ import annotations

import argparse
import json

from forage import config, db, paths


def cmd_info(args: argparse.Namespace) -> int:
    cfg = config.load_collection(args.name)
    with db.open_db(paths.collection_db_path(args.name)) as conn:
        db.init_schema(conn)
        totals = db.status_counts(conn)
        per_source = {s.name: db.status_counts(conn, s.name) for s in cfg.sources}
        pending_q = db.queue_depth(conn, "pending")
        failures = db.recent_failures(conn, 10)
        suspicious = db.recent_suspicious(conn, 10)

    if getattr(args, "as_json", False):
        out = {
            "name": cfg.name,
            "created_at": cfg.created_at,
            "output_dir": str(paths.collection_output_dir(cfg.name)),
            "sources": [
                {**s.to_dict(), "status_counts": per_source.get(s.name, {})}
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
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"collection: {cfg.name}")
    print(f"created:    {cfg.created_at}")
    print(f"output:     {paths.collection_output_dir(cfg.name)}")
    print(f"sources ({len(cfg.sources)}):")
    for s in cfg.sources:
        counts = per_source.get(s.name, {})
        c = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "(empty)"
        print(f"  - {s.name}: {s.path}")
        print(f"      {c}")
    if totals:
        print("totals: " + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())))
    print(f"pending queue: {pending_q}")
    if failures:
        print(f"recent failures ({len(failures)}):")
        for f in failures:
            print(f"  - {f.source}/{f.path}: {f.status_detail or ''}")
    if suspicious:
        print(f"recent suspicious ({len(suspicious)}):")
        for f in suspicious:
            print(f"  - {f.source}/{f.path}: {f.status_detail or ''}")
    return 0
