from __future__ import annotations

from pathlib import Path

from ingest import paths, state
from ingest.sync import sync_collection
from _helpers import FakeAnythingLLM, FakeForageFile


def _files_v1() -> list[FakeForageFile]:
    return [
        FakeForageFile("notes", "a.md", sha256="HA", status="ok", output_path="notes/a.md", content="# A\n"),
        FakeForageFile("notes", "b.md", sha256="HB", status="ok", output_path="notes/b.md", content="# B\n"),
        FakeForageFile("notes", "c.md", sha256="HC", status="ok", output_path="notes/c.md", content="# C\n"),
    ]


def test_first_sync_uploads_everything(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    make_forage_collection("demo", _files_v1())
    client = client_factory()

    result = sync_collection("demo", client=client)
    assert result.uploaded == 3
    assert result.unchanged == 0
    assert result.failed == 0
    assert "demo" in fake_server.workspaces
    assert len(fake_server.documents) == 3
    assert len(fake_server.embeddings["demo"]) == 3

    # Local state mirrors what's remote.
    with state.open_db(paths.uploads_db_path("demo")) as conn:
        rows = list(state.iter_uploads(conn))
        assert {r.path for r in rows} == {"a.md", "b.md", "c.md"}
        assert all(r.workspace_slug == "demo" for r in rows)


def test_second_sync_is_idempotent(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    make_forage_collection("demo", _files_v1())
    sync_collection("demo", client=client_factory())
    fake_server.request_log.clear()

    result = sync_collection("demo", client=client_factory())
    assert result.uploaded == 0
    assert result.changed == 0
    assert result.unchanged == 3
    # No raw-text POSTs the second time.
    paths_hit = [p for _m, p in fake_server.request_log]
    assert "/api/v1/document/raw-text" not in paths_hit


def test_changed_file_replaces_remote_doc(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    make_forage_collection("demo", _files_v1())
    sync_collection("demo", client=client_factory())
    old_locations = set(fake_server.documents.keys())

    # Forage re-extracts b.md with a new hash.
    v2 = [
        FakeForageFile("notes", "a.md", "HA", "ok", "notes/a.md", content="# A\n"),
        FakeForageFile("notes", "b.md", "HB-NEW", "ok", "notes/b.md", content="# B v2\n"),
        FakeForageFile("notes", "c.md", "HC", "ok", "notes/c.md", content="# C\n"),
    ]
    make_forage_collection("demo", v2)

    result = sync_collection("demo", client=client_factory())
    assert result.changed == 1
    assert result.unchanged == 2
    assert result.failed == 0

    new_locations = set(fake_server.documents.keys())
    # The location of the changed doc has been replaced, not duplicated.
    assert len(new_locations) == 3
    assert old_locations - new_locations  # something was removed
    # And the replacement is embedded.
    assert new_locations == fake_server.embeddings["demo"]


def test_orphan_is_deleted_by_default(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    make_forage_collection("demo", _files_v1())
    sync_collection("demo", client=client_factory())

    # Forage drops c.md from its manifest.
    shrunk = [f for f in _files_v1() if f.path != "c.md"]
    make_forage_collection("demo", shrunk)

    result = sync_collection("demo", client=client_factory())
    assert result.orphans_deleted == 1
    assert result.orphans_kept == 0
    assert len(fake_server.documents) == 2

    with state.open_db(paths.uploads_db_path("demo")) as conn:
        paths_in_state = {r.path for r in state.iter_uploads(conn)}
    assert "c.md" not in paths_in_state


def test_keep_orphans_preserves_remote(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    make_forage_collection("demo", _files_v1())
    sync_collection("demo", client=client_factory())
    shrunk = [f for f in _files_v1() if f.path != "c.md"]
    make_forage_collection("demo", shrunk)

    result = sync_collection(
        "demo", client=client_factory(), keep_orphans=True
    )
    assert result.orphans_kept == 1
    assert result.orphans_deleted == 0
    assert len(fake_server.documents) == 3  # nothing removed remotely


def test_dry_run_makes_no_http_calls_and_no_state_changes(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    make_forage_collection,
) -> None:
    make_forage_collection("demo", _files_v1())
    result = sync_collection("demo", client=None, dry_run=True)
    assert result.uploaded == 0
    assert result.unchanged == 0
    # The fake server saw nothing — no client was even constructed.
    assert fake_server.request_log == []
    # No uploads.db rows were written.
    with state.open_db(paths.uploads_db_path("demo")) as conn:
        assert list(state.iter_uploads(conn)) == []


def test_suspicious_skipped_by_default(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    files = [
        FakeForageFile("notes", "ok.md", "H1", "ok", "notes/ok.md"),
        FakeForageFile("notes", "sus.md", "H2", "suspicious", "notes/sus.md"),
    ]
    make_forage_collection("demo", files)

    result = sync_collection("demo", client=client_factory())
    assert result.uploaded == 1
    assert len(fake_server.documents) == 1
    titles = [d.title for d in fake_server.documents.values()]
    assert any("ok" in t for t in titles)


def test_include_suspicious_uploads_them(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    files = [
        FakeForageFile("notes", "ok.md", "H1", "ok", "notes/ok.md"),
        FakeForageFile("notes", "sus.md", "H2", "suspicious", "notes/sus.md"),
    ]
    make_forage_collection("demo", files)

    result = sync_collection(
        "demo", client=client_factory(), include_suspicious=True
    )
    assert result.uploaded == 2


def test_suspicious_upload_is_not_orphaned_when_flag_toggled_off(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    """User uploads with --include-suspicious, then re-runs without it.
    The suspicious doc must NOT be deleted as a phantom orphan."""
    files = [
        FakeForageFile("notes", "ok.md", "H1", "ok", "notes/ok.md"),
        FakeForageFile("notes", "sus.md", "H2", "suspicious", "notes/sus.md"),
    ]
    make_forage_collection("demo", files)
    sync_collection(
        "demo", client=client_factory(), include_suspicious=True
    )
    assert len(fake_server.documents) == 2

    # Second run without the flag.
    result = sync_collection("demo", client=client_factory())
    assert result.unchanged == 1     # only ok.md is in the in-scope set
    assert result.orphans_deleted == 0
    assert len(fake_server.documents) == 2


def test_reconciles_untracked_remote_docs_on_sync(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    """Simulate a previous sync where /document/raw-text completed
    server-side but the response was lost (timeout). The doc exists in
    AnythingLLM, isn't in our uploads.db, and must be removed by the
    next sync before it gets duplicated."""
    make_forage_collection("demo", _files_v1())
    sync_collection("demo", client=client_factory())
    assert len(fake_server.documents) == 3

    # Stage a phantom: a forage:// doc for this collection that ingest
    # never recorded locally (mimics the timeout-then-server-completed
    # case). Use a different upload id so the location is distinct.
    client = client_factory()
    phantom = client.upload_raw_text(
        text_content="ghost",
        title="ghost",
        doc_source="forage://demo/notes/ghost.md",
    )
    assert phantom.location in fake_server.documents
    assert len(fake_server.documents) == 4

    # Re-run sync. Phantom is reconciled away; no new uploads needed.
    result = sync_collection("demo", client=client_factory())
    assert result.reconciled == 1
    assert result.uploaded == 0
    assert result.unchanged == 3
    assert phantom.location not in fake_server.documents
    assert len(fake_server.documents) == 3


def test_reconciliation_leaves_other_collections_alone(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    """A forage:// doc tagged for collection 'other' must NOT be touched
    when we sync collection 'demo'."""
    make_forage_collection("demo", _files_v1())
    sync_collection("demo", client=client_factory())

    client = client_factory()
    other = client.upload_raw_text(
        text_content="x",
        title="x",
        doc_source="forage://other/s/a.md",
    )
    assert other.location in fake_server.documents

    result = sync_collection("demo", client=client_factory())
    assert result.reconciled == 0
    assert other.location in fake_server.documents


def test_uploads_land_in_per_source_folder(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    """Sync must move each upload from custom-documents/ into a folder
    named {workspace_slug}-{source} before embedding it."""
    files = [
        FakeForageFile("notes", "a.md", "HA", "ok", "notes/a.md"),
        FakeForageFile("notes", "b.md", "HB", "ok", "notes/b.md"),
        FakeForageFile("drafts", "x.md", "HX", "ok", "drafts/x.md"),
    ]
    make_forage_collection("demo", files)

    result = sync_collection("demo", client=client_factory())
    assert result.uploaded == 3

    # Every document now lives under its per-source folder, not in
    # custom-documents/.
    for loc in fake_server.documents:
        assert not loc.startswith("custom-documents/")
    folders = {loc.split("/", 1)[0] for loc in fake_server.documents}
    assert folders == {"demo-notes", "demo-drafts"}

    # And the embeddings reference the moved locations, not the original
    # custom-documents/ ones.
    assert fake_server.embeddings["demo"] == set(
        fake_server.documents.keys()
    )

    # uploads.db points at the new locations too.
    with state.open_db(paths.uploads_db_path("demo")) as conn:
        rows = list(state.iter_uploads(conn))
        assert all(
            r.anythingllm_loc.startswith("demo-")
            for r in rows
        )


def test_target_folder_created_once_per_source_per_run(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    """Each (collection, source) folder is created at most once per sync,
    even with many uploads going into it."""
    files = [
        FakeForageFile("notes", f"f{i}.md", f"H{i}", "ok", f"notes/f{i}.md")
        for i in range(5)
    ]
    make_forage_collection("demo", files)
    sync_collection("demo", client=client_factory())

    create_calls = [
        p for m, p in fake_server.request_log
        if m == "POST" and p == "/api/v1/document/create-folder"
    ]
    assert len(create_calls) == 1  # one source → one create-folder call


def test_failed_extraction_causes_orphan_deletion(
    ingest_home: Path,
    forage_home: Path,
    fake_server: FakeAnythingLLM,
    client_factory,
    make_forage_collection,
) -> None:
    """If a previously-uploaded doc flips to status=failed in forage,
    it must be removed from AnythingLLM (no longer trusted)."""
    files = [
        FakeForageFile("notes", "a.md", "H1", "ok", "notes/a.md"),
    ]
    make_forage_collection("demo", files)
    sync_collection("demo", client=client_factory())
    assert len(fake_server.documents) == 1

    # Re-extraction failed; forage now lists the row as 'failed'.
    files2 = [
        FakeForageFile("notes", "a.md", "H1", "failed", "notes/a.md"),
    ]
    make_forage_collection("demo", files2)
    result = sync_collection("demo", client=client_factory())
    assert result.orphans_deleted == 1
    assert len(fake_server.documents) == 0
