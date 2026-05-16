from __future__ import annotations

import argparse
import sys
from pathlib import Path

import shtab

from ingest import config, log
from ingest.commands.check import cmd_check
from ingest.commands.list_ import cmd_list
from ingest.commands.purge import cmd_purge
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
    p.add_argument(
        "--url",
        dest="url",
        default=argparse.SUPPRESS,
        help="AnythingLLM base URL (overrides ANYTHINGLLM_URL and config.json)",
    )
    p.add_argument(
        "--api-key",
        dest="api_key",
        default=argparse.SUPPRESS,
        help=(
            "AnythingLLM API key (overrides ANYTHINGLLM_API_KEY). "
            "Visible in shell history and `ps`; prefer --api-key-file "
            "or the env var for sensitive uses."
        ),
    )
    p.add_argument(
        "--api-key-file",
        dest="api_key_file",
        default=argparse.SUPPRESS,
        help="read the API key from this file (one line, trimmed)",
    )
    p.add_argument(
        "--storage-dir",
        dest="storage_dir",
        default=argparse.SUPPRESS,
        help=(
            "AnythingLLM storage directory for the disk-usage report "
            "(overrides ANYTHINGLLM_STORAGE_DIR and config.json)"
        ),
    )
    p.add_argument(
        "--http-timeout",
        dest="http_timeout",
        type=float,
        default=argparse.SUPPRESS,
        help=(
            "read/write timeout in seconds for AnythingLLM HTTP calls "
            "(overrides INGEST_HTTP_TIMEOUT; default 300). Connect timeout "
            "is fixed at 5 s."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingest")
    _add_global_flags(parser)
    shtab.add_argument_to(parser, ["--print-completion"])
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

    p_purge = sub.add_parser(
        "purge",
        help="delete ALL ingest state (every collection's uploads.db and logs)",
    )
    p_purge.add_argument("-y", "--yes", action="store_true")
    _add_global_flags(p_purge)

    return parser


_HANDLERS = {
    "sync": cmd_sync,
    "status": cmd_status,
    "list": cmd_list,
    "check": cmd_check,
    "reset": cmd_reset,
    "purge": cmd_purge,
}


def _resolve_api_key_file(args: argparse.Namespace) -> None:
    """If --api-key-file is set and --api-key isn't, read the file in.

    Trims trailing whitespace so files with a trailing newline (the common
    case from ``echo "$KEY" > key.txt``) work.
    """
    path = getattr(args, "api_key_file", None)
    if path and not getattr(args, "api_key", None):
        try:
            args.api_key = Path(path).read_text().strip()
        except OSError as exc:
            raise config.ConfigError(
                f"could not read --api-key-file {path}: {exc}"
            ) from exc
        if not args.api_key:
            raise config.ConfigError(
                f"--api-key-file {path} is empty"
            )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log.setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )
    try:
        _resolve_api_key_file(args)
        if (
            getattr(args, "api_key", None)
            and not getattr(args, "api_key_file", None)
            and not getattr(args, "quiet", False)
        ):
            print(
                "note: --api-key is visible in shell history and `ps`. "
                "Consider --api-key-file or the ANYTHINGLLM_API_KEY env var.",
                file=sys.stderr,
            )
        handler = _HANDLERS[args.command]
        return handler(args)
    except config.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
