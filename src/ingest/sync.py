from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ingest import config, forage_db, log, paths, state
from ingest.anythingllm import AnythingLLMClient
from ingest.forage_db import ForageFile

_log = log.get_logger()


@dataclass
class Diff:
    new: list[ForageFile] = field(default_factory=list)
    changed: list[tuple[ForageFile, state.Upload]] = field(default_factory=list)
    unchanged: list[ForageFile] = field(default_factory=list)
    orphans: list[state.Upload] = field(default_factory=list)


@dataclass
class SyncResult:
    uploaded: int = 0
    changed: int = 0
    unchanged: int = 0
    orphans_deleted: int = 0
    orphans_kept: int = 0
    failed: int = 0
    reconciled: int = 0


def compute_diff(
    forage_rows: list[ForageFile],
    uploads: list[state.Upload],
    *,
    keep_alive_keys: set[tuple[str, str]] | None = None,
) -> Diff:
    """Classify each forage row vs. each prior upload.

    new        — in forage_rows, not yet uploaded
    changed    — uploaded before, sha256 now differs
    unchanged  — uploaded before, sha256 matches
    orphans    — previously uploaded; either gone from forage entirely, or
                 forage no longer considers it uploadable in any mode.

    `keep_alive_keys`, if given, lists `(source, path)` tuples that should
    NOT be treated as orphans even when absent from `forage_rows`. The sync
    layer uses this to protect previously-uploaded `suspicious` documents
    from deletion when the user runs without `--include-suspicious`.
    """
    uploads_by_key = {(u.source, u.path): u for u in uploads}
    diff = Diff()
    seen_keys: set[tuple[str, str]] = set()
    for row in forage_rows:
        key = (row.source, row.path)
        seen_keys.add(key)
        prior = uploads_by_key.get(key)
        if prior is None:
            diff.new.append(row)
        elif (row.sha256 or "") != prior.sha256:
            diff.changed.append((row, prior))
        else:
            diff.unchanged.append(row)
    keep = keep_alive_keys or set()
    for key, upload in uploads_by_key.items():
        if key in seen_keys or key in keep:
            continue
        diff.orphans.append(upload)
    return diff


def _doc_source(collection: str, row: ForageFile) -> str:
    return f"forage://{collection}/{row.source}/{row.path}"


def _target_folder(workspace_slug: str, source: str) -> str:
    """Documents-folder name for one (collection, source) pair.

    Example: workspace ``news`` + source ``archive`` → folder ``news-archive``.
    The collection prefix keeps folders unique across collections that share
    a source name.
    """
    return f"{workspace_slug}-{source}"


_CUSTOM = "custom-documents/"


def _move_into_folder(
    client: AnythingLLMClient,
    src_location: str,
    target_folder: str,
    *,
    ensured_folders: set[str],
) -> str:
    """Move a freshly uploaded document into ``target_folder``.

    Returns the new location. The folder is created on first use per sync run
    (tracked via ``ensured_folders``). Must be called BEFORE embedding —
    AnythingLLM's move endpoint silently skips embedded files.
    """
    if not src_location.startswith(_CUSTOM):
        return src_location
    filename = src_location[len(_CUSTOM):]
    dst_location = f"{target_folder}/{filename}"
    if target_folder not in ensured_folders:
        client.create_folder(target_folder)
        ensured_folders.add(target_folder)
    client.move_files([(src_location, dst_location)])
    return dst_location


def _doc_title(row: ForageFile) -> str:
    stem = Path(row.path).stem
    return f"{row.source}/{stem}" if stem else f"{row.source}/{row.path}"


def _doc_description(row: ForageFile) -> str:
    parts = [f"extractor={row.extractor or 'unknown'}"]
    if row.sha256:
        parts.append(f"sha256={row.sha256}")
    if row.status and row.status != "ok":
        parts.append(f"status={row.status}")
    return "; ".join(parts)


def _read_markdown(output_root: Path, row: ForageFile) -> str:
    return forage_db.output_file_path(output_root, row).read_text(
        encoding="utf-8"
    )


def sync_collection(
    collection: str,
    *,
    client: AnythingLLMClient | None,
    include_suspicious: bool = False,
    keep_orphans: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    """Run the full sync for one forage collection.

    `client` may be None when `dry_run=True` — no HTTP is attempted in that
    case. When `dry_run=False`, `client` must be set.
    """
    if not dry_run and client is None:
        raise ValueError("client is required unless dry_run=True")

    forage_db_path = paths.forage_collection_db_path(collection)
    output_root = paths.forage_collection_output_dir(collection)
    uploads_db_path = paths.uploads_db_path(collection)

    with forage_db.open_readonly(forage_db_path) as fconn:
        forage_rows = list(
            forage_db.iter_uploadable(
                fconn, include_suspicious=include_suspicious
            )
        )
        # All rows forage currently considers uploadable in any mode.
        # Used to protect suspicious uploads from accidental deletion when
        # the user runs without --include-suspicious.
        keep_alive_keys = {
            (r.source, r.path)
            for r in forage_db.iter_uploadable(fconn, include_suspicious=True)
        }

    with state.open_db(uploads_db_path) as uconn:
        prior_uploads = list(state.iter_uploads(uconn))
        diff = compute_diff(
            forage_rows, prior_uploads, keep_alive_keys=keep_alive_keys
        )

        _log.info(
            "collection %s: new=%d changed=%d unchanged=%d orphans=%d",
            collection,
            len(diff.new),
            len(diff.changed),
            len(diff.unchanged),
            len(diff.orphans),
        )

        result = SyncResult(unchanged=len(diff.unchanged))

        if dry_run:
            _summarize_dry_run(diff)
            return result

        slug = config.workspace_slug_for(collection)
        ws = client.ensure_workspace(slug, display_name=slug)
        _log.debug("workspace: slug=%s name=%s", ws.slug, ws.name)

        result.reconciled = _reconcile_remote(
            collection, client=client, known_locs={u.anythingllm_loc for u in prior_uploads}
        )

        ensured_folders: set[str] = set()

        for row in diff.new:
            try:
                _upload_one(
                    collection,
                    row,
                    output_root=output_root,
                    client=client,
                    uconn=uconn,
                    workspace_slug=ws.slug,
                    ensured_folders=ensured_folders,
                )
                result.uploaded += 1
            except Exception as exc:
                _log.error("upload failed: %s/%s: %s", row.source, row.path, exc)
                result.failed += 1

        for row, prior in diff.changed:
            try:
                client.embed_documents(
                    ws.slug, deletes=[prior.anythingllm_loc]
                )
                client.remove_documents([prior.anythingllm_loc])
                _upload_one(
                    collection,
                    row,
                    output_root=output_root,
                    client=client,
                    uconn=uconn,
                    workspace_slug=ws.slug,
                    ensured_folders=ensured_folders,
                )
                result.changed += 1
            except Exception as exc:
                _log.error("replace failed: %s/%s: %s", row.source, row.path, exc)
                result.failed += 1

        for orphan in diff.orphans:
            if keep_orphans:
                _log.info(
                    "keeping orphan in AnythingLLM: %s/%s",
                    orphan.source,
                    orphan.path,
                )
                result.orphans_kept += 1
                continue
            try:
                client.embed_documents(
                    orphan.workspace_slug, deletes=[orphan.anythingllm_loc]
                )
                client.remove_documents([orphan.anythingllm_loc])
                state.delete_upload(uconn, orphan.source, orphan.path)
                _log.info("removed orphan: %s/%s", orphan.source, orphan.path)
                result.orphans_deleted += 1
            except Exception as exc:
                _log.error(
                    "orphan removal failed: %s/%s: %s",
                    orphan.source,
                    orphan.path,
                    exc,
                )
                result.failed += 1

        return result


def _reconcile_remote(
    collection: str,
    *,
    client: AnythingLLMClient,
    known_locs: set[str],
) -> int:
    """Delete forage:// documents AnythingLLM holds that we don't track.

    These typically come from a previous run where /document/raw-text
    completed server-side after our HTTP client gave up — the server kept
    the document; we never recorded it. Re-running sync would otherwise
    upload a fresh copy alongside it.
    """
    prefix = f"forage://{collection}/"
    stale: list[str] = []
    for entry in client.list_documents():
        if not entry.doc_source or not entry.doc_source.startswith(prefix):
            continue
        if entry.location in known_locs:
            continue
        stale.append(entry.location)
    if not stale:
        return 0
    client.remove_documents(stale)
    _log.info(
        "reconciled %d untracked remote doc(s) for collection %s",
        len(stale),
        collection,
    )
    return len(stale)


def _upload_one(
    collection: str,
    row: ForageFile,
    *,
    output_root: Path,
    client: AnythingLLMClient,
    uconn,
    workspace_slug: str,
    ensured_folders: set[str],
) -> None:
    text = _read_markdown(output_root, row)
    upload = client.upload_raw_text(
        text_content=text,
        title=_doc_title(row),
        doc_source=_doc_source(collection, row),
        description=_doc_description(row),
    )
    final_location = _move_into_folder(
        client,
        upload.location,
        _target_folder(workspace_slug, row.source),
        ensured_folders=ensured_folders,
    )
    client.embed_documents(workspace_slug, adds=[final_location])
    state.upsert_upload(
        uconn,
        state.Upload(
            source=row.source,
            path=row.path,
            sha256=row.sha256 or "",
            anythingllm_loc=final_location,
            workspace_slug=workspace_slug,
            uploaded_at=config.utc_now(),
            forage_status=row.status,
        ),
    )
    _log.info("uploaded: %s/%s -> %s", row.source, row.path, final_location)


def _summarize_dry_run(diff: Diff) -> None:
    for row in diff.new:
        _log.info("would upload: %s/%s", row.source, row.path)
    for row, _prior in diff.changed:
        _log.info("would replace: %s/%s", row.source, row.path)
    for orphan in diff.orphans:
        _log.info("would remove orphan: %s/%s", orphan.source, orphan.path)
