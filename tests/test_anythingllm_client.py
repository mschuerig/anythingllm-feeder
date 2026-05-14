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
    ws = client.create_workspace("forage-demo")
    assert ws.slug == "forage-demo"
    listed = client.list_workspaces()
    assert [w.slug for w in listed] == ["forage-demo"]


def test_upload_raw_text_and_embed(fake_server, client_factory) -> None:
    client = client_factory()
    client.create_workspace("forage-demo")
    res = client.upload_raw_text(
        text_content="hello",
        title="t",
        doc_source="forage://demo/s/a.md",
        description="extractor=docling",
    )
    assert res.location in fake_server.documents
    client.embed_documents("forage-demo", adds=[res.location])
    assert res.location in fake_server.embeddings["forage-demo"]


def test_remove_documents(fake_server, client_factory) -> None:
    client = client_factory()
    client.create_workspace("forage-demo")
    r = client.upload_raw_text(text_content="x", title="x")
    client.embed_documents("forage-demo", adds=[r.location])
    client.remove_documents([r.location])
    assert r.location not in fake_server.documents
    assert r.location not in fake_server.embeddings["forage-demo"]
