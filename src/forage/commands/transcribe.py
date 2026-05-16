from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

from forage import config, db, extractors, log, paths
from forage.extractors import whisper as whisper_mod
from forage.extractors.base import ExtractorError
from forage.extractors.whisper import NoAudioStream


def _resolve_whisper_model(args: argparse.Namespace) -> str | None:
    """Pick the whisper model id for this run.

    Precedence: --whisper-model > global config.json whisper_model > default.
    Returns ``None`` to mean "use the extractor's built-in default" so the
    default cache key stays ``"mlx-whisper"`` and existing test stubs work.
    """
    explicit = getattr(args, "whisper_model", None)
    if explicit:
        return explicit
    configured = config.load_global().whisper_model
    if configured and configured != whisper_mod.DEFAULT_MODEL:
        return configured
    return None
from forage.locks import collection_lock
from forage.output import output_relpath, write_atomic


_DUR_RE = re.compile(r"^\s*(\d+)\s*([smhSMH]?)\s*$")


def parse_duration(s: str) -> float:
    """Parse '4h', '90m', '3600s' or bare seconds into a float."""
    m = _DUR_RE.match(s)
    if not m:
        raise config.ConfigError(f"invalid duration: {s!r}")
    n = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    return n * {"s": 1, "m": 60, "h": 3600}[unit]


def cmd_transcribe(args: argparse.Namespace) -> int:
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
            rc |= cmd_transcribe(args)
            args.name = None
            args.all_collections = True
        return rc
    if not args.name:
        raise config.ConfigError("collection name required (or pass --all)")
    return _drain(args.name, args)


def _drain(coll_name: str, args: argparse.Namespace) -> int:
    cfg = config.load_collection(coll_name)
    db_path = paths.collection_db_path(coll_name)
    output_dir = paths.collection_output_dir(coll_name)
    log_handler = log.add_collection_log(paths.collection_log_path(coll_name))
    logger = log.get_logger()
    logger.info(
        "transcribe %s: limit=%s time_limit=%s retry_failed=%s dry_run=%s",
        coll_name, args.limit, args.time_limit,
        args.retry_failed, args.dry_run,
    )

    deadline: float | None = None
    if args.time_limit:
        deadline = time.monotonic() + parse_duration(args.time_limit)
    limit: int | None = args.limit
    whisper_model: str | None = _resolve_whisper_model(args)
    if whisper_model is not None:
        logger.info("using whisper model: %s", whisper_model)

    stats = {"done": 0, "failed": 0, "no_audio": 0, "suspicious": 0,
             "skipped": 0, "dry": 0}

    try:
        with collection_lock(paths.collection_lock_path(coll_name)), \
                db.open_db(db_path) as conn:
            if args.dry_run:
                # Read-only: list pending entries (and failed if requested).
                rows = db.dequeue_oldest(
                    conn,
                    limit=limit if limit is not None else 10_000,
                    include_failed=args.retry_failed,
                )
                for row in rows:
                    print(f"[dry-run] would transcribe {row['source']}/{row['path']}")
                    stats["dry"] += 1
            else:
                processed = 0
                while True:
                    if limit is not None and processed >= limit:
                        break
                    if deadline is not None and time.monotonic() > deadline:
                        logger.info("time limit reached after %d items", processed)
                        break
                    rows = db.dequeue_oldest(
                        conn, limit=1, include_failed=args.retry_failed
                    )
                    if not rows:
                        break
                    row = rows[0]
                    source, rel = row["source"], row["path"]
                    result = transcribe_one(
                        conn, cfg, source, rel, output_dir, logger,
                        whisper_model=whisper_model,
                    )
                    stats[result] = stats.get(result, 0) + 1
                    processed += 1
    finally:
        logger.info(
            "transcribe %s done: done=%d suspicious=%d no_audio=%d failed=%d "
            "skipped=%d dry=%d",
            coll_name, stats["done"], stats["suspicious"], stats["no_audio"],
            stats["failed"], stats["skipped"], stats["dry"],
        )
        log.remove_handler(log_handler)

    print(
        f"{coll_name}: done={stats['done']} suspicious={stats['suspicious']} "
        f"no_audio={stats['no_audio']} failed={stats['failed']} "
        f"skipped={stats['skipped']}"
        + (f" dry={stats['dry']}" if stats['dry'] else "")
    )
    return 0


def transcribe_one(
    conn: sqlite3.Connection,
    cfg: config.CollectionConfig,
    source: str,
    rel: str,
    output_dir: Path,
    logger,
    *,
    whisper_model: str | None = None,
) -> str:
    """Transcribe one queue entry. Updates `files` and `queue` rows.

    Returns one of: 'done', 'suspicious', 'no_audio', 'failed', 'skipped'.
    """
    rel_key = f"{source}/{rel}"
    src_cfg = cfg.source(source)
    if src_cfg is None:
        logger.warning("skipping %s: source removed", rel_key)
        db.update_queue(
            conn, source, rel, "failed",
            error="source removed", finished_at=config.utc_now(),
        )
        return "skipped"
    src_abs = Path(src_cfg.path) / rel
    if not src_abs.exists():
        logger.warning("skipping %s: source file missing", rel_key)
        db.update_queue(
            conn, source, rel, "failed",
            error="source file missing", finished_at=config.utc_now(),
        )
        return "skipped"

    started = config.utc_now()
    db.update_queue(conn, source, rel, "running", started_at=started)
    logger.info("running  %s", rel_key)

    try:
        extractor = extractors.get_whisper(model=whisper_model)
        result = extractor.extract(src_abs)
    except NoAudioStream as e:
        finished = config.utc_now()
        prior = db.get_file(conn, source, rel) or db.FileRow(
            source=source, path=rel, extractor="mlx-whisper"
        )
        prior.status = "no_audio"
        prior.status_detail = str(e)
        prior.output_path = None
        prior.updated_at = finished
        db.upsert_file(conn, prior)
        db.update_queue(conn, source, rel, "done", finished_at=finished)
        logger.info("no_audio %s", rel_key)
        return "no_audio"
    except Exception as e:
        finished = config.utc_now()
        prior = db.get_file(conn, source, rel) or db.FileRow(
            source=source, path=rel, extractor="mlx-whisper"
        )
        prior.status = "failed"
        prior.status_detail = str(e)
        prior.updated_at = finished
        db.upsert_file(conn, prior)
        db.update_queue(
            conn, source, rel, "failed", error=str(e), finished_at=finished
        )
        logger.exception("failed   %s", rel_key)
        return "failed"

    out_rel = output_relpath(source, rel)
    out_path = output_dir / out_rel
    write_atomic(out_path, result.markdown)

    finished = config.utc_now()
    prior = db.get_file(conn, source, rel) or db.FileRow(
        source=source, path=rel, extractor="mlx-whisper"
    )
    prior.output_path = out_rel
    prior.extractor = "mlx-whisper"
    if result.suspicious_reasons:
        prior.status = "suspicious"
        prior.status_detail = "; ".join(result.suspicious_reasons)
        outcome = "suspicious"
    else:
        prior.status = "ok"
        prior.status_detail = None
        outcome = "done"
    prior.extracted_at = finished
    prior.updated_at = finished
    db.upsert_file(conn, prior)
    db.update_queue(conn, source, rel, "done", finished_at=finished)
    logger.info("%s %s", outcome, rel_key)
    return outcome
