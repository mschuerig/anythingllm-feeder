from __future__ import annotations

import argparse
import json

from forage import config, db, paths
from forage.commands.repair import check_collection


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run a read-only consistency check across every collection.

    Exits 0 when every collection is clean, 1 when any collection reports
    issues. Designed as the first thing to run after a restore-from-backup
    or "something looks off" scenario; see ``IN_CASE_OF_ERRORS.md``.
    """
    rows: list[dict[str, object]] = []
    any_warn = False

    names = config.list_collections()
    if not names:
        if getattr(args, "as_json", False):
            print(json.dumps([], indent=2))
        else:
            print("no collections")
        return 0

    for name in names:
        try:
            cfg = config.load_collection(name)
        except config.ConfigError as exc:
            rows.append({"name": name, "status": "WARN", "reason": str(exc)})
            any_warn = True
            continue

        db_path = paths.collection_db_path(name)
        issues = check_collection(cfg, db_path)

        counts: dict[str, int] = {}
        if db_path.exists():
            with db.open_db(db_path) as conn:
                counts = db.status_counts(conn)

        files_total = sum(counts.values())
        suspicious = counts.get("suspicious", 0)
        failed = counts.get("failed", 0)

        if issues:
            any_warn = True
            rows.append(
                {
                    "name": name,
                    "status": "WARN",
                    "issues": issues,
                    "files": files_total,
                    "suspicious": suspicious,
                    "failed": failed,
                }
            )
        else:
            rows.append(
                {
                    "name": name,
                    "status": "ok",
                    "files": files_total,
                    "suspicious": suspicious,
                    "failed": failed,
                }
            )

    if getattr(args, "as_json", False):
        print(json.dumps(rows, indent=2))
        return 1 if any_warn else 0

    width = max(len(r["name"]) for r in rows)
    for r in rows:
        name = r["name"]
        if r["status"] == "ok":
            print(
                f"{name:{width}s}  ok    "
                f"({r['files']} files, {r['suspicious']} suspicious, {r['failed']} failed)"
            )
        else:
            files = r.get("files", 0)
            issues = r.get("issues") or [r.get("reason", "unknown error")]
            head = issues[0]
            extra = f" (+{len(issues) - 1} more)" if len(issues) > 1 else ""
            print(
                f"{name:{width}s}  WARN  "
                f"({files} files, {r.get('suspicious', 0)} suspicious, "
                f"{r.get('failed', 0)} failed)  {head}{extra}"
            )

    return 1 if any_warn else 0
