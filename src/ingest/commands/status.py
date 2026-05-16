from __future__ import annotations

import argparse
import json
import sys

from ingest import config, forage_db, paths, state, storage, sync


def _build_storage_report(
    uploads: list[state.Upload],
    workspace_slug: str | None,
    *,
    storage_dir_override: str | None,
) -> storage.StorageReport | None:
    """Compute storage attribution if AnythingLLM's storage dir is findable.

    Returns None when there's nothing to attribute (no prior uploads, no
    known workspace slug) or when the storage directory isn't reachable —
    `status` should still print the diff in those cases.
    """
    if not uploads or not workspace_slug:
        return None
    storage_dir = config.resolve_anythingllm_storage_dir(
        override=storage_dir_override
    )
    if storage_dir is None:
        return None
    return storage.report(
        storage_dir,
        document_locations=[u.anythingllm_loc for u in uploads],
        workspace_slug=workspace_slug,
    )


def _print_storage_human(rep: storage.StorageReport) -> None:
    fb = storage.format_bytes
    print(f"storage in AnythingLLM ({rep.storage_dir}):")
    missing_note = (
        f"  ({rep.documents_missing} missing on disk)"
        if rep.documents_missing
        else ""
    )
    print(
        f"  documents:    {fb(rep.documents_bytes):>10}  "
        f"({rep.documents_count} files){missing_note}"
    )
    if rep.lancedb_present:
        print(f"  vectors:      {fb(rep.lancedb_bytes):>10}  (lancedb)")
    else:
        print("  vectors:           n/a  (workspace not embedded yet)")
    print(f"  attributable: {fb(rep.attributable_bytes):>10}")
    if rep.vector_cache_present:
        print(
            f"  shared:       {fb(rep.vector_cache_bytes):>10}  "
            "(vector-cache/, across all workspaces)"
        )


def cmd_status(args: argparse.Namespace) -> int:
    collection: str = args.name
    include_suspicious: bool = getattr(args, "include_suspicious", False)

    forage_db_path = paths.forage_collection_db_path(collection)
    uploads_db_path = paths.uploads_db_path(collection)

    try:
        with forage_db.open_readonly(forage_db_path) as fconn:
            forage_rows = list(
                forage_db.iter_uploadable(
                    fconn, include_suspicious=include_suspicious
                )
            )
    except forage_db.ForageStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with state.open_db(uploads_db_path) as uconn:
        prior = list(state.iter_uploads(uconn))

    diff = sync.compute_diff(forage_rows, prior)

    workspace_slug = prior[0].workspace_slug if prior else None
    storage_report = _build_storage_report(
        prior,
        workspace_slug,
        storage_dir_override=getattr(args, "storage_dir", None),
    )

    if getattr(args, "as_json", False):
        payload: dict[str, object] = {
            "collection": collection,
            "new": [f"{r.source}/{r.path}" for r in diff.new],
            "changed": [f"{r.source}/{r.path}" for r, _ in diff.changed],
            "unchanged": [f"{r.source}/{r.path}" for r in diff.unchanged],
            "orphans": [f"{u.source}/{u.path}" for u in diff.orphans],
        }
        if storage_report is not None:
            payload["storage"] = {
                "storage_dir": str(storage_report.storage_dir),
                "documents_bytes": storage_report.documents_bytes,
                "documents_count": storage_report.documents_count,
                "documents_missing": storage_report.documents_missing,
                "lancedb_bytes": storage_report.lancedb_bytes,
                "lancedb_present": storage_report.lancedb_present,
                "vector_cache_bytes": storage_report.vector_cache_bytes,
                "vector_cache_present": storage_report.vector_cache_present,
                "attributable_bytes": storage_report.attributable_bytes,
            }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"collection: {collection}")
    print(f"  new:       {len(diff.new)}")
    print(f"  changed:   {len(diff.changed)}")
    print(f"  unchanged: {len(diff.unchanged)}")
    print(f"  orphans:   {len(diff.orphans)}")
    if getattr(args, "verbose", False):
        for r in diff.new:
            print(f"    + {r.source}/{r.path}")
        for r, _ in diff.changed:
            print(f"    ~ {r.source}/{r.path}")
        for u in diff.orphans:
            print(f"    - {u.source}/{u.path}")
    if storage_report is not None:
        _print_storage_human(storage_report)
    return 0
