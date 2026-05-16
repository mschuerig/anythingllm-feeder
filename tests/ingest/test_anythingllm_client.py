from __future__ import annotations

import httpx
import pytest

from ingest.anythingllm import (
    AnythingLLMClient,
    AuthError,
    RemoteError,
    ServerUnreachable,
)


def test_auth_check_ok(fake_server, client_factory) -> None:
    client = client_factory()
    assert client.auth_check() is True


def test_bad_key_raises_auth_error(fake_server) -> None:
    transport = httpx.MockTransport(fake_server.handle)
    with AnythingLLMClient(
        base_url="http://x", api_key="wrong-key", transport=transport
    ) as c:
        with pytest.raises(AuthError):
            c.auth_check()


def test_unreachable_server_surfaces_clear_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(boom)
    with AnythingLLMClient(
        base_url="http://localhost:9", api_key="k", transport=transport
    ) as c:
        with pytest.raises(ServerUnreachable, match="not reachable"):
            c.auth_check()


def test_remote_error_carries_body() -> None:
    def err(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    with AnythingLLMClient(
        base_url="http://x",
        api_key="k",
        transport=httpx.MockTransport(err),
    ) as c:
        with pytest.raises(RemoteError) as exc:
            c.list_workspaces()
        assert exc.value.status == 500
        assert "boom" in exc.value.body


def test_create_and_list_workspace(fake_server, client_factory) -> None:
    client = client_factory()
    assert client.list_workspaces() == []
    ws = client.create_workspace("demo")
    assert ws.slug == "demo"
    listed = client.list_workspaces()
    assert [w.slug for w in listed] == ["demo"]


def test_upload_raw_text_and_embed(fake_server, client_factory) -> None:
    client = client_factory()
    client.create_workspace("demo")
    res = client.upload_raw_text(
        text_content="hello",
        title="t",
        doc_source="forage://demo/s/a.md",
        description="extractor=docling",
    )
    assert res.location in fake_server.documents
    client.embed_documents("demo", adds=[res.location])
    assert res.location in fake_server.embeddings["demo"]


def test_remove_documents(fake_server, client_factory) -> None:
    client = client_factory()
    client.create_workspace("demo")
    r = client.upload_raw_text(text_content="x", title="x")
    client.embed_documents("demo", adds=[r.location])
    client.remove_documents([r.location])
    assert r.location not in fake_server.documents
    assert r.location not in fake_server.embeddings["demo"]


def test_list_documents_surfaces_locations_and_doc_source(
    fake_server, client_factory
) -> None:
    client = client_factory()
    r1 = client.upload_raw_text(
        text_content="x", title="x", doc_source="forage://demo/s/a.md"
    )
    r2 = client.upload_raw_text(text_content="y", title="y")  # no docSource
    entries = list(client.list_documents())
    by_loc = {e.location: e for e in entries}
    assert r1.location in by_loc
    assert by_loc[r1.location].doc_source == "forage://demo/s/a.md"
    assert r2.location in by_loc
    assert by_loc[r2.location].doc_source is None


def test_create_folder_is_idempotent(fake_server, client_factory) -> None:
    client = client_factory()
    client.create_folder("demo-notes")
    # Second call must not raise even though AnythingLLM returns HTTP 500
    # with "Folder by that name already exists".
    client.create_folder("demo-notes")
    assert "demo-notes" in fake_server.folders


def test_create_folder_propagates_other_errors(fake_server, client_factory) -> None:
    # An unrelated 500 should still bubble up as RemoteError.
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"success": False, "message": "disk full"})

    with AnythingLLMClient(
        base_url="http://x",
        api_key="k",
        transport=httpx.MockTransport(boom),
    ) as c:
        with pytest.raises(RemoteError, match="disk full"):
            c.create_folder("anything")


def test_move_files_renames_locations(fake_server, client_factory) -> None:
    client = client_factory()
    up = client.upload_raw_text(text_content="x", title="x")
    assert up.location.startswith("custom-documents/")
    filename = up.location.split("/", 1)[1]
    client.create_folder("target")
    client.move_files([(up.location, f"target/{filename}")])
    assert up.location not in fake_server.documents
    assert f"target/{filename}" in fake_server.documents


def test_move_files_silently_skips_embedded_docs(
    fake_server, client_factory
) -> None:
    """Mirrors the real server: a doc already embedded in a workspace is
    not moved. This is why sync must move BEFORE embedding."""
    client = client_factory()
    client.create_workspace("demo")
    up = client.upload_raw_text(text_content="x", title="x")
    client.embed_documents("demo", adds=[up.location])  # embed first
    client.create_folder("target")
    filename = up.location.split("/", 1)[1]
    client.move_files([(up.location, f"target/{filename}")])
    # Move was a no-op because the file is embedded.
    assert up.location in fake_server.documents
    assert f"target/{filename}" not in fake_server.documents
