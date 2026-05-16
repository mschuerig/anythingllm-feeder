from __future__ import annotations

import argparse
import sys

from forage import config, log
from forage.commands.create import cmd_create
from forage.commands.info import cmd_info
from forage.commands.list_ import cmd_list
from forage.commands.remove import cmd_remove
from forage.commands.rename import cmd_rename
from forage.commands.repair import cmd_repair
from forage.commands.source import cmd_add_source, cmd_remove_source, cmd_set_source
from forage.commands.transcribe import cmd_transcribe
from forage.commands.update import cmd_update
from forage.locks import CollectionLocked


def _add_global_flags(p: argparse.ArgumentParser) -> None:
    # SUPPRESS defaults so a subparser flag doesn't clobber a value set by the
    # main parser when the user puts the flag before the subcommand.
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
    parser = argparse.ArgumentParser(prog="forage")
    _add_global_flags(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="create a new collection")
    p_create.add_argument("name")
    p_create.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="add a named source (repeatable, at least one required)",
    )
    _add_global_flags(p_create)

    p_list = sub.add_parser("list", help="list collections")
    _add_global_flags(p_list)

    p_info = sub.add_parser("info", help="show collection details")
    p_info.add_argument("name")
    _add_global_flags(p_info)

    p_update = sub.add_parser("update", help="walk sources and extract changed files")
    p_update.add_argument("name", nargs="?", help="collection name (omit with --all)")
    p_update.add_argument("--all", dest="all_collections", action="store_true")
    p_update.add_argument(
        "--source", dest="source_name",
        help="scope discovery + orphan sweep to one source",
    )
    p_update.add_argument("--ext", help="comma-separated extensions (no dots)")
    p_update.add_argument(
        "--orphans", choices=["list", "delete", "ignore"], default="list"
    )
    p_update.add_argument("--defer-video", dest="defer_video", action="store_true")
    p_update.add_argument("--dry-run", dest="dry_run", action="store_true")
    ocr = p_update.add_mutually_exclusive_group()
    ocr.add_argument(
        "--ocr",
        dest="do_ocr_override",
        action="store_const",
        const=True,
        help="force docling OCR on for this run (overrides the collection's do_ocr setting)",
    )
    ocr.add_argument(
        "--no-ocr",
        dest="do_ocr_override",
        action="store_const",
        const=False,
        help="force docling OCR off for this run (overrides the collection's do_ocr setting)",
    )
    _add_global_flags(p_update)

    p_tr = sub.add_parser("transcribe", help="drain transcription queue")
    p_tr.add_argument("name", nargs="?")
    p_tr.add_argument("--all", dest="all_collections", action="store_true")
    p_tr.add_argument("--limit", type=int)
    p_tr.add_argument("--time-limit", dest="time_limit")
    p_tr.add_argument("--retry-failed", dest="retry_failed", action="store_true")
    p_tr.add_argument("--dry-run", dest="dry_run", action="store_true")
    p_tr.add_argument(
        "--whisper-model",
        dest="whisper_model",
        metavar="MODEL",
        help=(
            "Hugging Face mlx-whisper model id for this run "
            "(overrides config.json's whisper_model)"
        ),
    )
    _add_global_flags(p_tr)

    p_repair = sub.add_parser("repair", help="check or rebuild state.db")
    p_repair.add_argument("name")
    grp = p_repair.add_mutually_exclusive_group()
    grp.add_argument("--check", action="store_true")
    grp.add_argument("--rebuild", action="store_true")
    _add_global_flags(p_repair)

    p_add = sub.add_parser("add-source", help="add a source to a collection")
    p_add.add_argument("collection")
    p_add.add_argument("name")
    p_add.add_argument("dir")
    _add_global_flags(p_add)

    p_rs = sub.add_parser("remove-source", help="remove a source from a collection")
    p_rs.add_argument("collection")
    p_rs.add_argument("name")
    grp2 = p_rs.add_mutually_exclusive_group()
    grp2.add_argument("--delete-files", dest="delete_files", action="store_true")
    grp2.add_argument("--keep-files", dest="keep_files", action="store_true")
    p_rs.add_argument("-y", "--yes", action="store_true")
    _add_global_flags(p_rs)

    p_ss = sub.add_parser("set-source", help="change a source's directory")
    p_ss.add_argument("collection")
    p_ss.add_argument("name")
    p_ss.add_argument("new_dir")
    _add_global_flags(p_ss)

    p_rn = sub.add_parser("rename", help="rename a collection")
    p_rn.add_argument("old_name")
    p_rn.add_argument("new_name")
    _add_global_flags(p_rn)

    p_rm = sub.add_parser("remove", help="remove a collection")
    p_rm.add_argument("name")
    grp3 = p_rm.add_mutually_exclusive_group()
    grp3.add_argument("--delete-files", dest="delete_files", action="store_true")
    grp3.add_argument("--keep-files", dest="keep_files", action="store_true")
    p_rm.add_argument("-y", "--yes", action="store_true")
    _add_global_flags(p_rm)

    return parser


def _not_implemented(cmd: str) -> int:
    print(f"error: '{cmd}' not yet implemented", file=sys.stderr)
    return 2


_HANDLERS = {
    "create": cmd_create,
    "list": cmd_list,
    "info": cmd_info,
    "repair": cmd_repair,
    "update": cmd_update,
    "transcribe": cmd_transcribe,
    "add-source": cmd_add_source,
    "remove-source": cmd_remove_source,
    "set-source": cmd_set_source,
    "rename": cmd_rename,
    "remove": cmd_remove,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log.setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )
    try:
        handler = _HANDLERS.get(args.command)
        if handler is None:
            return _not_implemented(args.command)
        return handler(args)
    except config.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except CollectionLocked as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
