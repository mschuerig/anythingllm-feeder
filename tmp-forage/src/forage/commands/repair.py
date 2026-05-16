from __future__ import annotations

import argparse
from pathlib import Path

from forage import config, db, hashing, log, paths
from forage.extractors import extractor_for
from forage.locks import collection_lock
from forage.log import get_logger
from forage.output import output_relpath


def cmd_repair(args: argparse.Namespace) -> int:
    cfg = config.load_collection(args.name)
    db_path = paths.collection_db_path(args.name)
    handler = log.add_collection_log(paths.collection_log_path(cfg.name))
    try:
        if args.rebuild:
            return _rebuild(cfg, db_path)
        return _check(cfg, db_path)
    finally:
        log.remove_handler(handler)


def _check(cfg: config.CollectionConfig, db_path: Path) -> int:
    issues: list[str] = []

    if not db_path.exists():
        print(f"state.db missing at {db_path}")
        return 1

    output_dir = paths.collection_output_dir(cfg.name)
    cfg_source_names = {s.name for s in cfg.sources}

    with db.open_db(db_path) as conn:
        results = db.integrity_check(conn)
        if not (len(results) == 1 and results[0] == "ok"):
            for r in results:
                issues.append(f"integrity: {r}")

        rows_by_source: dict[str, list[db.FileRow]] = {}
        for row in db.iter_files(conn):
            rows_by_source.setdefault(row.source, []).append(row)

    output_files_seen: set[Path] = set()
    for source_cfg in cfg.sources:
        source_root = Path(source_cfg.path)
        rows = rows_by_source.get(source_cfg.name, [])
        for row in rows:
            src_file = source_root / row.path
            if not src_file.exists():
                issues.append(f"missing source: {source_cfg.name}/{row.path}")
            if row.output_path:
                out_file = output_dir / row.output_path
                if out_file.exists():
                    output_files_seen.add(out_file.resolve())
                else:
                    issues.append(f"missing output: {row.output_path}")

        source_out_root = paths.source_output_dir(cfg.name, source_cfg.name)
        if source_out_root.exists():
            for out in source_out_root.rglob("*.md"):
                if out.resolve() not in output_files_seen:
                    rel = out.relative_to(output_dir)
                    issues.append(f"orphan output: {rel}")

    for source_name in rows_by_source:
        if source_name not in cfg_source_names:
            issues.append(f"unknown source in db: {source_name}")

    if not issues:
        print("ok")
        return 0
    for i in issues:
        print(i)
    return 1


def _rebuild(cfg: config.CollectionConfig, db_path: Path) -> int:
    log = get_logger()
    log.info("rebuilding %s", db_path)
    output_dir = paths.collection_output_dir(cfg.name)

    n_recorded = 0
    n_unextracted = 0
    n_missing_sources = 0
    now = config.utc_now()

    with collection_lock(paths.collection_lock_path(cfg.name)):
        db.reset_db(db_path)
        with db.open_db(db_path) as conn:
            db.init_schema(conn)
            for source_cfg in cfg.sources:
                source_root = Path(source_cfg.path)
                if not source_root.is_dir():
                    print(
                        f"warning: source {source_cfg.name!r} path missing: {source_root}"
                    )
                    n_missing_sources += 1
                    continue
                for src_file in _walk(source_root):
                    if extractor_for(src_file) is None:
                        continue
                    rel = src_file.relative_to(source_root).as_posix()
                    ext_name = extractor_for(src_file)
                    stat = src_file.stat()
                    out_rel = output_relpath(source_cfg.name, rel)
                    out_file = output_dir / out_rel
                    if out_file.exists():
                        sha = hashing.sha256_file(src_file)
                        db.upsert_file(
                            conn,
                            db.FileRow(
                                source=source_cfg.name,
                                path=rel,
                                sha256=sha,
                                mtime=stat.st_mtime,
                                size=stat.st_size,
                                output_path=out_rel,
                                extractor=ext_name,
                                status="ok",
                                extracted_at=now,
                                updated_at=now,
                            ),
                        )
                        n_recorded += 1
                    else:
                        n_unextracted += 1

    print(
        f"rebuilt {db_path.name}: {n_recorded} recorded, "
        f"{n_unextracted} unextracted"
        + (
            f", {n_missing_sources} missing source path(s)"
            if n_missing_sources
            else ""
        )
    )
    return 0


def _walk(root: Path):
    for p in root.rglob("*"):
        if p.is_file():
            yield p
