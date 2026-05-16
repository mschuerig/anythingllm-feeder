from __future__ import annotations

import argparse
import json
import sys

from ingest import paths, state


def _list_collections() -> list[dict[str, object]]:
    """Return collections visible to ingest: those known to forage,
    each annotated with whether ingest has any upload state for it.
    """
    out: list[dict[str, object]] = []
    forage_root = paths.forage_app_support_dir() / "collections"
    if not forage_root.exists():
        return out
    for d in sorted(forage_root.iterdir()):
        if not d.is_dir():
            continue
        cfg = d / "config.json"
        if not cfg.exists():
            continue
        name = d.name
        uploads_db = paths.uploads_db_path(name)
        upload_count = 0
        if uploads_db.exists():
            with state.open_db(uploads_db) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM uploads"
                ).fetchone()
                upload_count = int(row["n"])
        out.append(
            {
                "name": name,
                "uploads": upload_count,
                "forage_dir": str(d),
            }
        )
    return out


def cmd_list(args: argparse.Namespace) -> int:
    rows = _list_collections()
    if getattr(args, "as_json", False):
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no forage collections found", file=sys.stderr)
        return 0
    for r in rows:
        print(f"{r['name']:30s}  uploads={r['uploads']}")
    return 0
