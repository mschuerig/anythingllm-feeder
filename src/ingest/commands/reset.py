from __future__ import annotations

import argparse
import sys

from ingest import paths, state


def cmd_reset(args: argparse.Namespace) -> int:
    name: str = args.name
    if not getattr(args, "yes", False):
        print(
            f"This drops ingest's local upload state for collection "
            f"{name!r}. Documents already in AnythingLLM are NOT touched. "
            "Re-run with -y to confirm.",
            file=sys.stderr,
        )
        return 2
    db = paths.uploads_db_path(name)
    if not db.exists():
        print(f"no uploads.db for {name}", file=sys.stderr)
        return 0
    state.reset_db(db)
    print(f"reset uploads.db for {name}")
    return 0
