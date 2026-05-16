from __future__ import annotations

import argparse
import sys

from send2trash import send2trash

from forage import paths
from forage.locks import CollectionLocked, collection_lock


def _any_collection_locked() -> str | None:
    """Return the name of the first collection forage holds elsewhere, else None.

    Only looks at collections whose forage subdir already exists, so we don't
    materialize empty ``forage/`` dirs for ingest-only collections.
    """
    collections_root = paths.collections_dir()
    if not collections_root.exists():
        return None
    for coll_dir in sorted(collections_root.iterdir()):
        if not coll_dir.is_dir():
            continue
        forage_dir = paths.collection_dir(coll_dir.name)
        if not forage_dir.exists():
            continue
        try:
            with collection_lock(forage_dir / ".lock"):
                pass
        except CollectionLocked:
            return coll_dir.name
    return None


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n} TB"


def _dir_size(path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _print_summary(root) -> None:
    collections_root = paths.collections_dir()
    print(f"toolkit data root: {root}")

    forage_global = root / "forage"
    ingest_global = root / "ingest"
    if forage_global.exists():
        print(f"  forage config:   {_human_size(_dir_size(forage_global))}")
    if ingest_global.exists():
        print(f"  ingest config:   {_human_size(_dir_size(ingest_global))}")

    if not collections_root.exists():
        print("  no collections")
        return

    collections = sorted(
        d for d in collections_root.iterdir() if d.is_dir()
    )
    if not collections:
        print("  no collections")
        return
    print(f"  {len(collections)} collection(s):")
    for d in collections:
        forage_out = d / "forage" / "output"
        ingest_dir = d / "ingest"
        size = _dir_size(forage_out) + _dir_size(ingest_dir)
        marker = []
        if (d / "forage").exists():
            marker.append("forage")
        if ingest_dir.exists():
            marker.append("ingest")
        print(f"    {d.name:30s}  {_human_size(size):>10s}  [{','.join(marker)}]")


def cmd_purge(args: argparse.Namespace) -> int:
    root = paths.app_support_dir()
    if not root.exists():
        print(f"nothing to purge: {root} does not exist")
        return 0

    locked = _any_collection_locked()
    if locked is not None:
        print(
            f"error: collection {locked!r} is in use by another forage; "
            "wait for it to finish and try again",
            file=sys.stderr,
        )
        return 2

    _print_summary(root)
    print()
    print("This will move the entire toolkit data root to Trash.")
    print("It affects BOTH forage and ingest state for all collections.")
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
    return 0
