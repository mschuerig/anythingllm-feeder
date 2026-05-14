from __future__ import annotations

import argparse
import sys

from ingest import config, log
from ingest.commands.check import cmd_check
from ingest.commands.list_ import cmd_list
from ingest.commands.reset import cmd_reset
from ingest.commands.status import cmd_status
from ingest.commands.sync import cmd_sync


def _add_global_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "-v", "--verbose", action="store_true", default=argparse.SUPPRESS
    )
    p.add_argument(
        "-q", "--quiet", action="store_true", default=argparse.SUPPRESS
    )
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="machine-readable JSON output where applicable",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest")
    _add_global_flags(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser(
        "sync", help="upload changed forage documents to AnythingLLM"
    )
    p_sync.add_argument("name", nargs="?", help="collection name (omit with --all)")
    p_sync.add_argument("--all", dest="all_collections", action="store_true")
    p_sync.add_argument(
        "--include-suspicious",
        dest="include_suspicious",
        action="store_true",
        help="also upload forage rows with status=suspicious",
    )
    p_sync.add_argument(
        "--keep-orphans",
        dest="keep_orphans",
        action="store_true",
        help="do not delete documents from AnythingLLM that forage no longer lists",
    )
    p_sync.add_argument("--dry-run", dest="dry_run", action="store_true")
    _add_global_flags(p_sync)

    p_status = sub.add_parser(
        "status", help="show what sync would do without uploading"
    )
    p_status.add_argument("name")
    p_status.add_argument(
        "--include-suspicious", dest="include_suspicious", action="store_true"
    )
    _add_global_flags(p_status)

    p_list = sub.add_parser(
        "list", help="list collections known to forage and our upload counts"
    )
    _add_global_flags(p_list)

    p_check = sub.add_parser(
        "check", help="verify AnythingLLM is reachable and the API key works"
    )
    _add_global_flags(p_check)

    p_reset = sub.add_parser(
        "reset", help="drop local uploads.db for a collection (no remote changes)"
    )
    p_reset.add_argument("name")
    p_reset.add_argument("-y", "--yes", action="store_true")
    _add_global_flags(p_reset)

    return parser


_HANDLERS = {
    "sync": cmd_sync,
    "status": cmd_status,
    "list": cmd_list,
    "check": cmd_check,
    "reset": cmd_reset,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log.setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )
    try:
        handler = _HANDLERS[args.command]
        return handler(args)
    except config.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
