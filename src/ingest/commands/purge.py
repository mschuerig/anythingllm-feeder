from __future__ import annotations

import argparse
import sys

from send2trash import send2trash

from ingest import paths

# Re-use forage's summary + lock-detection helpers so the two purge commands
# behave identically. Importing across tools is unusual; justified here because
# both share one data root and `purge` is intentionally a synonym.
from forage.commands.purge import _any_collection_locked, _print_summary


def cmd_purge(args: argparse.Namespace) -> int:
    root = paths.app_support_dir()
    if not root.exists():
        print(f"nothing to purge: {root} does not exist")
        return 0

    locked = _any_collection_locked()
    if locked is not None:
        print(
            f"error: collection {locked!r} is in use by forage; "
            "wait for it to finish and try again",
            file=sys.stderr,
        )
        return 2

    _print_summary(root)
    print()
    print("This will move the entire toolkit data root to Trash.")
    print("It affects BOTH forage and ingest state for all collections.")
    print("Documents already in AnythingLLM are NOT touched.")
    print("(Recover via Finder → Trash → Put Back.)")

    if not getattr(args, "yes", False):
        if not sys.stdin.isatty():
            print(
                "error: non-interactive run: pass -y/--yes to confirm",
                file=sys.stderr,
            )
            return 2
        try:
            ans = input("Proceed? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in {"y", "yes"}:
            print("aborted")
            return 1

    send2trash(str(root))
    print(f"moved {root} to Trash")
    print(
        "note: downloaded model weights at ~/.cache/huggingface/hub/ are "
        "NOT removed (shared with other Hugging Face tools)."
    )
    return 0
