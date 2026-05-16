from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class FakeForageFile:
    source: str
    path: str
    sha256: str
    status: str
    output_path: str
    extractor: str = "docling"
    content: str = "# fake\n"


def create_forage_state(
    forage_home: Path, collection: str, files: Iterable[FakeForageFile]
) -> None:
    """Build a minimal forage state.db + output tree for one collection.

    Matches forage/SPEC.md schema closely enough for our reader. Calling
    repeatedly for the same collection replaces the previous state.db.

    ``forage_home`` is the toolkit data root (the single
    ``anythingllm-feeder/`` parent); state lives under
    ``<root>/collections/<name>/forage/``.
    """
    coll_dir = forage_home / "collections" / collection / "forage"
    output_dir = coll_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = coll_dir / "state.db"
    for suffix in ("", "-shm", "-wal", "-journal"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    (coll_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "name": collection,
                "created_at": "2026-05-15T00:00:00Z",
                "do_ocr": True,
                "sources": [],
            }
        )
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE files (
              source         TEXT NOT NULL,
              path           TEXT NOT NULL,
              sha256         TEXT,
              mtime          REAL,
              size           INTEGER,
              output_path    TEXT,
              extractor      TEXT,
              status         TEXT,
              status_detail  TEXT,
              extracted_at   TEXT,
              updated_at     TEXT,
              PRIMARY KEY (source, path)
            );
            """
        )
        for f in files:
            conn.execute(
                "INSERT INTO files (source, path, sha256, output_path, "
                "extractor, status, extracted_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f.source,
                    f.path,
                    f.sha256,
                    f.output_path,
                    f.extractor,
                    f.status,
                    "2026-05-15T00:00:00Z",
                    "2026-05-15T00:00:00Z",
                ),
            )
            out_path = output_dir / f.output_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(f.content)
        conn.commit()
    finally:
        conn.close()


@dataclass
class FakeDoc:
    location: str
    title: str
    text: str
    doc_source: str | None = None


class FakeAnythingLLM:
    """In-memory stand-in for AnythingLLM's REST API.

    Plug into httpx via `MockTransport(server.handle)`.
    """

    def __init__(self) -> None:
        self.workspaces: dict[str, str] = {}
        self.documents: dict[str, FakeDoc] = {}
        self.embeddings: dict[str, set[str]] = {}
        self.folders: set[str] = {"custom-documents"}
        self.next_doc_id = 0
        self.request_log: list[tuple[str, str]] = []

    def _is_embedded(self, location: str) -> bool:
        return any(location in s for s in self.embeddings.values())

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.request_log.append((request.method, request.url.path))
        if request.headers.get("Authorization") != "Bearer test-key":
            return httpx.Response(401, json={"error": "bad key"})
        path = request.url.path
        method = request.method

        if path == "/api/v1/auth" and method == "GET":
            return httpx.Response(200, json={"authenticated": True})

        if path == "/api/v1/workspaces" and method == "GET":
            return httpx.Response(
                200,
                json={
                    "workspaces": [
                        {"slug": s, "name": n}
                        for s, n in self.workspaces.items()
                    ]
                },
            )

        if path == "/api/v1/workspace/new" and method == "POST":
            body = json.loads(request.content)
            name = body["name"]
            slug = name.lower().replace(" ", "-")
            self.workspaces[slug] = name
            self.embeddings.setdefault(slug, set())
            return httpx.Response(
                200, json={"workspace": {"slug": slug, "name": name}}
            )

        if path == "/api/v1/document/raw-text" and method == "POST":
            body = json.loads(request.content)
            text = body["textContent"]
            meta = body.get("metadata") or {}
            self.next_doc_id += 1
            loc = f"custom-documents/anythingllm-{self.next_doc_id}.json"
            self.documents[loc] = FakeDoc(
                location=loc,
                title=meta.get("title", ""),
                text=text,
                doc_source=meta.get("docSource"),
            )
            return httpx.Response(
                200,
                json={
                    "documents": [
                        {"location": loc, "title": meta.get("title", "")}
                    ]
                },
            )

        if path == "/api/v1/documents" and method == "GET":
            by_folder: dict[str, list[dict]] = {}
            for loc, doc in self.documents.items():
                folder, _, fname = loc.partition("/")
                by_folder.setdefault(folder, []).append(
                    {
                        "name": fname,
                        "type": "file",
                        "title": doc.title,
                        "docSource": doc.doc_source,
                    }
                )
            return httpx.Response(
                200,
                json={
                    "localFiles": {
                        "name": "documents",
                        "type": "folder",
                        "items": [
                            {
                                "name": folder,
                                "type": "folder",
                                "items": items,
                            }
                            for folder, items in by_folder.items()
                        ],
                    }
                },
            )

        if (
            path.startswith("/api/v1/workspace/")
            and path.endswith("/update-embeddings")
            and method == "POST"
        ):
            slug = path.split("/")[4]
            body = json.loads(request.content)
            embeds = self.embeddings.setdefault(slug, set())
            for loc in body.get("adds", []):
                embeds.add(loc)
            for loc in body.get("deletes", []):
                embeds.discard(loc)
            return httpx.Response(200, json={"workspace": {"slug": slug}})

        if path == "/api/v1/system/remove-documents" and method == "DELETE":
            body = json.loads(request.content)
            for name in body.get("names", []):
                self.documents.pop(name, None)
                for embeds in self.embeddings.values():
                    embeds.discard(name)
            return httpx.Response(200, json={"success": True})

        if path == "/api/v1/document/create-folder" and method == "POST":
            body = json.loads(request.content)
            name = body["name"]
            if name in self.folders:
                return httpx.Response(
                    500,
                    json={
                        "success": False,
                        "message": "Folder by that name already exists",
                    },
                )
            self.folders.add(name)
            return httpx.Response(200, json={"success": True, "message": None})

        if path == "/api/v1/document/move-files" and method == "POST":
            body = json.loads(request.content)
            for entry in body.get("files", []):
                src, dst = entry["from"], entry["to"]
                # Mirror the real server: silently skip if embedded somewhere.
                if self._is_embedded(src):
                    continue
                doc = self.documents.pop(src, None)
                if doc is None:
                    continue
                self.documents[dst] = FakeDoc(
                    location=dst,
                    title=doc.title,
                    text=doc.text,
                    doc_source=doc.doc_source,
                )
            return httpx.Response(200, json={"success": True, "message": None})

        return httpx.Response(404, json={"error": f"no route for {method} {path}"})
