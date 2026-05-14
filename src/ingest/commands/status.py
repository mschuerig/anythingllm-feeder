from __future__ import annotations

import argparse
import json
import sys

from ingest import forage_db, paths, state, sync


def cmd_status(args: argparse.Namespace) -> int:
    collection: str = args.name
    include_suspicious: bool = getattr(args, "include_suspicious", False)

    forage_db_path = paths.forage_collection_db_path(collection)
    uploads_db_path = paths.uploads_db_path(collection)

    try:
        with forage_db.open_readonly(forage_db_path) as fconn:
            forage_rows = list(
                forage_db.iter_uploadable(
                    fconn, include_suspicious=include_suspicious
                )
            )
    except forage_db.ForageStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with state.open_db(uploads_db_path) as uconn:
        prior = list(state.iter_uploads(uconn))

    diff = sync.compute_diff(forage_rows, prior)

    if getattr(args, "as_json", False):
        payload = {
            "collection": collection,
            "new": [f"{r.source}/{r.path}" for r in diff.new],
            "changed": [f"{r.source}/{r.path}" for r, _ in diff.changed],
            "unchanged": [f"{r.source}/{r.path}" for r in diff.unchanged],
            "orphans": [f"{u.source}/{u.path}" for u in diff.orphans],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"collection: {collection}")
    print(f"  new:       {len(diff.new)}")
    print(f"  changed:   {len(diff.changed)}")
    print(f"  unchanged: {len(diff.unchanged)}")
    print(f"  orphans:   {len(diff.orphans)}")
    if getattr(args, "verbose", False):
        for r in diff.new:
            print(f"    + {r.source}/{r.path}")
        for r, _ in diff.changed:
            print(f"    ~ {r.source}/{r.path}")
        for u in diff.orphans:
            print(f"    - {u.source}/{u.path}")
    return 0
