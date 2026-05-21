from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from forage import config, db, extractors, log, paths, walk
from forage.extractors.base import ExtractorError
from forage.locks import collection_lock
from forage.output import output_relpath, write_atomic


@dataclass
class UpdateStats:
    new: int = 0
    changed: int = 0
    touched: int = 0
    unchanged: int = 0
    failed: int = 0
    queued: int = 0
    skipped: int = 0
    orphans_listed: int = 0
    orphans_deleted: int = 0


def cmd_update(args: argparse.Namespace) -> int:
    if args.all_collections:
        if args.name:
            raise config.ConfigError("'--all' cannot be combined with a name")
        names = config.list_collections()
        if not names:
            print("(no collections)")
            return 0
        rc = 0
        for n in names:
            print(f"== {n} ==")
            args.name = n
            args.all_collections = False
            rc |= cmd_update(args)
            args.name = None
            args.all_collections = True
        return rc

    if not args.name:
        raise config.ConfigError("collection name required (or pass --all)")

    cfg = config.load_collection(args.name)

    # Per-run override of the collection's persisted do_ocr setting.
    # Mutate the in-memory cfg only; we never call save_collection here.
    ocr_override = getattr(args, "do_ocr_override", None)
    if ocr_override is not None:
        cfg.do_ocr = ocr_override

    if args.source_name:
        if cfg.source(args.source_name) is None:
            raise config.ConfigError(
                f"unknown source: {args.source_name} in collection {cfg.name}"
            )
        sources_to_walk = [cfg.source(args.source_name)]
    else:
        sources_to_walk = list(cfg.sources)

    ext_filter = walk.parse_ext_filter(getattr(args, "ext", None))
    db_path = paths.collection_db_path(cfg.name)
    output_dir = paths.collection_output_dir(cfg.name)
    log_handler = log.add_collection_log(paths.collection_log_path(cfg.name))
    logger = log.get_logger()
    logger.info(
        "update %s: argv=%s source=%s ext=%s defer_video=%s dry_run=%s "
        "orphans=%s do_ocr=%s",
        cfg.name, sys.argv[1:], args.source_name, args.ext,
        args.defer_video, args.dry_run, args.orphans, cfg.do_ocr,
    )

    stats = UpdateStats()
    try:
        with collection_lock(paths.collection_lock_path(cfg.name)), \
                db.open_db(db_path) as conn:
            db.init_schema(conn)
            for source_cfg in sources_to_walk:
                for item in walk.walk_source(conn, source_cfg, ext_filter):
                    _process_item(args, conn, cfg, source_cfg, item,
                                  output_dir, stats, logger)
            _handle_orphans(args, conn, output_dir, cfg, stats, logger)
    finally:
        logger.info(
            "update %s done: new=%d changed=%d touched=%d unchanged=%d "
            "failed=%d queued=%d skipped=%d orphans_listed=%d orphans_deleted=%d",
            cfg.name, stats.new, stats.changed, stats.touched, stats.unchanged,
            stats.failed, stats.queued, stats.skipped, stats.orphans_listed,
            stats.orphans_deleted,
        )
        log.remove_handler(log_handler)

    _print_summary(cfg.name, stats)
    return 0


def _process_item(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    cfg: config.CollectionConfig,
    source_cfg: config.Source,
    item: walk.WalkItem,
    output_dir: Path,
    stats: UpdateStats,
    logger,
) -> None:
    coll_name = cfg.name
    rel_key = f"{item.source}/{item.rel}"

    if item.classification is walk.Classification.UNCHANGED:
        stats.unchanged += 1
        logger.debug("unchanged %s", rel_key)
        return

    if item.classification is walk.Classification.TOUCHED:
        stats.touched += 1
        logger.info("touched  %s", rel_key)
        if args.dry_run:
            return
        prior = item.prior
        prior.mtime = item.mtime
        prior.size = item.size
        prior.sha256 = item.sha256
        prior.updated_at = config.utc_now()
        db.upsert_file(conn, prior)
        return

    if item.extractor is None:
        stats.skipped += 1
        logger.debug("skip (unsupported) %s", rel_key)
        return

    out_rel = output_relpath(source_cfg.name, item.rel)
    now = config.utc_now()

    if item.extractor == "mlx-whisper":
        if args.dry_run:
            stats.queued += 1
            logger.info("[dry-run] queue %s", rel_key)
            return
        row = db.FileRow(
            source=item.source, path=item.rel,
            sha256=item.sha256, mtime=item.mtime, size=item.size,
            output_path=out_rel, extractor="mlx-whisper",
            status="pending", status_detail=None,
            updated_at=now,
        )
        db.upsert_file(conn, row)
        db.enqueue(conn, item.source, item.rel, now)
        stats.queued += 1
        logger.info("queued   %s", rel_key)
        if not args.defer_video:
            from forage.commands.transcribe import transcribe_one
            outcome = transcribe_one(
                conn, cfg, item.source, item.rel, output_dir, logger
            )
            if outcome == "failed":
                stats.failed += 1
        return

    # docling extractor — synchronous
    if args.dry_run:
        if item.classification is walk.Classification.NEW:
            stats.new += 1
            logger.info("[dry-run] new %s", rel_key)
        else:
            stats.changed += 1
            logger.info("[dry-run] changed %s", rel_key)
        return

    out_path = output_dir / out_rel
    try:
        extractor = extractors.get_docling(do_ocr=cfg.do_ocr)
        result = extractor.extract(item.abs)
        write_atomic(out_path, result.markdown)
        sha = item.sha256
        if sha is None:
            from forage import hashing
            sha = hashing.sha256_file(item.abs)
        db.upsert_file(
            conn,
            db.FileRow(
                source=item.source, path=item.rel,
                sha256=sha, mtime=item.mtime, size=item.size,
                output_path=out_rel, extractor=result.extractor,
                status="ok", status_detail=None,
                extracted_at=now, updated_at=now,
            ),
        )
        if item.classification is walk.Classification.NEW:
            stats.new += 1
            logger.info("new      %s", rel_key)
        else:
            stats.changed += 1
            logger.info("changed  %s", rel_key)
    except (ExtractorError, Exception) as e:
        logger.exception("failed   %s", rel_key)
        db.upsert_file(
            conn,
            db.FileRow(
                source=item.source, path=item.rel,
                sha256=item.sha256, mtime=item.mtime, size=item.size,
                output_path=None, extractor="docling",
                status="failed", status_detail=str(e),
                updated_at=now,
            ),
        )
        stats.failed += 1


def _handle_orphans(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    output_dir: Path,
    cfg: config.CollectionConfig,
    stats: UpdateStats,
    logger,
) -> None:
    orphans = walk.find_orphans(
        conn, list(cfg.sources), source_filter=args.source_name
    )
    if not orphans:
        return

    mode = args.orphans
    if mode == "ignore":
        return

    if mode == "list":
        print(f"orphans ({len(orphans)}):")
        for o in orphans:
            out_str = ""
            if o.output_path:
                out_str = f" (output: {output_dir / o.output_path})"
            print(f"  - {o.source}/{o.path}{out_str}")
        stats.orphans_listed = len(orphans)
        return

    # delete
    for o in orphans:
        if args.dry_run:
            logger.info("[dry-run] delete orphan %s/%s", o.source, o.path)
            continue
        if o.output_path:
            out_file = output_dir / o.output_path
            if out_file.exists():
                out_file.unlink()
                _prune_empty_parents(out_file.parent, output_dir)
        db.delete_file(conn, o.source, o.path)
        logger.info("deleted orphan %s/%s", o.source, o.path)
    stats.orphans_deleted = len(orphans)


def _prune_empty_parents(start: Path, stop: Path) -> None:
    p = start
    while p != stop and p.is_dir():
        try:
            p.rmdir()
        except OSError:
            return
        p = p.parent


def _print_summary(coll_name: str, s: UpdateStats) -> None:
    parts = [
        f"new={s.new}", f"changed={s.changed}", f"touched={s.touched}",
        f"unchanged={s.unchanged}", f"queued={s.queued}",
        f"failed={s.failed}", f"skipped={s.skipped}",
    ]
    if s.orphans_listed:
        parts.append(f"orphans_listed={s.orphans_listed}")
    if s.orphans_deleted:
        parts.append(f"orphans_deleted={s.orphans_deleted}")
    print(f"{coll_name}: " + " ".join(parts))
