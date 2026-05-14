from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

API_PREFIX = "/api/v1"


class AnythingLLMError(Exception):
    """Base for all AnythingLLM client errors."""


class ServerUnreachable(AnythingLLMError):
    """The base URL refused the connection, timed out, or DNS failed."""


class AuthError(AnythingLLMError):
    """The API key was rejected (401/403)."""


class RemoteError(AnythingLLMError):
    """Non-2xx response with a message we should surface."""

    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"{status} from {url}: {body[:500]}")
        self.status = status
        self.url = url
        self.body = body


@dataclass(frozen=True)
class Workspace:
    slug: str
    name: str


@dataclass(frozen=True)
class UploadResult:
    """Outcome of a raw-text upload.

    `location` is the storage path AnythingLLM returns; it is what we pass
    to update-embeddings and remove-documents.
    """

    location: str
    title: str


class AnythingLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url + API_PREFIX,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AnythingLLMClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ----- low-level request helper ------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = path
        try:
            resp = self._client.request(method, url, json=json, params=params)
        except httpx.ConnectError as exc:
            raise ServerUnreachable(
                f"AnythingLLM not reachable at {self._base_url} — "
                "is the service running? "
                f"(connect error: {exc})"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ServerUnreachable(
                f"AnythingLLM at {self._base_url} did not respond in time: {exc}"
            ) from exc

        if resp.status_code in (401, 403):
            raise AuthError(
                f"AnythingLLM rejected the API key ({resp.status_code}). "
                "Generate a fresh key in Settings → Developer and re-export "
                "ANYTHINGLLM_API_KEY."
            )
        if resp.status_code >= 400:
            raise RemoteError(resp.status_code, str(resp.request.url), resp.text)
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # ----- endpoints ---------------------------------------------------

    def auth_check(self) -> bool:
        """Confirm the API key works. Returns True on 200.

        Raises ServerUnreachable / AuthError / RemoteError otherwise.
        """
        self._request("GET", "/auth")
        return True

    def list_workspaces(self) -> list[Workspace]:
        data = self._request("GET", "/workspaces") or {}
        out: list[Workspace] = []
        for w in data.get("workspaces", []):
            slug = w.get("slug")
            name = w.get("name") or slug
            if slug:
                out.append(Workspace(slug=slug, name=name))
        return out

    def create_workspace(self, name: str) -> Workspace:
        data = self._request("POST", "/workspace/new", json={"name": name}) or {}
        w = data.get("workspace") or {}
        slug = w.get("slug")
        if not slug:
            raise RemoteError(
                200,
                "/workspace/new",
                f"unexpected response shape: {data!r}",
            )
        return Workspace(slug=slug, name=w.get("name") or name)

    def ensure_workspace(self, slug: str, *, display_name: str) -> Workspace:
        """Find a workspace by slug, or create one named `display_name`."""
        for ws in self.list_workspaces():
            if ws.slug == slug:
                return ws
        return self.create_workspace(display_name)

    def upload_raw_text(
        self,
        *,
        text_content: str,
        title: str,
        doc_source: str | None = None,
        description: str | None = None,
        author: str | None = None,
    ) -> UploadResult:
        metadata: dict[str, Any] = {"title": title}
        if doc_source:
            metadata["docSource"] = doc_source
        if description:
            metadata["description"] = description
        if author:
            metadata["docAuthor"] = author
        body = {"textContent": text_content, "metadata": metadata}
        data = self._request("POST", "/document/raw-text", json=body) or {}
        docs = data.get("documents") or []
        if not docs:
            raise RemoteError(
                200,
                "/document/raw-text",
                f"upload succeeded but response had no documents: {data!r}",
            )
        doc = docs[0]
        loc = doc.get("location") or doc.get("name")
        if not loc:
            raise RemoteError(
                200,
                "/document/raw-text",
                f"upload response missing location/name: {doc!r}",
            )
        return UploadResult(location=loc, title=doc.get("title") or title)

    def embed_documents(
        self,
        workspace_slug: str,
        *,
        adds: Iterable[str] = (),
        deletes: Iterable[str] = (),
    ) -> None:
        body = {"adds": list(adds), "deletes": list(deletes)}
        if not body["adds"] and not body["deletes"]:
            return
        self._request(
            "POST",
            f"/workspace/{workspace_slug}/update-embeddings",
            json=body,
        )

    def remove_documents(self, locations: Iterable[str]) -> None:
        names = list(locations)
        if not names:
            return
        self._request(
            "DELETE",
            "/system/remove-documents",
            json={"names": names},
        )
