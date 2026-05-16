from __future__ import annotations

from ingest import state
from ingest.forage_db import ForageFile
from ingest.sync import compute_diff


def _f(source: str, path: str, sha: str, status: str = "ok") -> ForageFile:
    return ForageFile(
        source=source,
        path=path,
        sha256=sha,
        output_path=f"{source}/{path}",
        extractor="docling",
        status=status,
        status_detail=None,
        extracted_at="2026-05-15T00:00:00Z",
    )


def _u(source: str, path: str, sha: str) -> state.Upload:
    return state.Upload(
        source=source,
        path=path,
        sha256=sha,
        anythingllm_loc=f"custom-documents/{source}-{path}.json",
        workspace_slug="c",
        uploaded_at="2026-05-15T00:00:00Z",
        forage_status="ok",
    )


def test_classifies_new_changed_unchanged_orphan() -> None:
    forage_rows = [
        _f("s", "a.md", "AAA"),       # new
        _f("s", "b.md", "BBB-new"),   # changed
        _f("s", "c.md", "CCC"),       # unchanged
    ]
    uploads = [
        _u("s", "b.md", "BBB-old"),
        _u("s", "c.md", "CCC"),
        _u("s", "z.md", "ZZZ"),       # orphan
    ]
    diff = compute_diff(forage_rows, uploads)
    assert [r.path for r in diff.new] == ["a.md"]
    assert [r.path for r, _ in diff.changed] == ["b.md"]
    assert [r.path for r in diff.unchanged] == ["c.md"]
    assert [u.path for u in diff.orphans] == ["z.md"]


def test_keep_alive_keys_protects_from_orphan_deletion() -> None:
    """A suspicious doc the user previously uploaded should NOT be treated
    as an orphan when they re-run without --include-suspicious."""
    forage_rows = [_f("s", "ok.md", "OK")]  # only the 'ok' row
    uploads = [
        _u("s", "ok.md", "OK"),
        _u("s", "sus.md", "SUS"),
    ]
    # The suspicious row is still in forage's manifest at status=suspicious;
    # the sync layer includes its key in keep_alive_keys.
    keep_alive = {("s", "ok.md"), ("s", "sus.md")}
    diff = compute_diff(forage_rows, uploads, keep_alive_keys=keep_alive)
    assert diff.orphans == []
    assert [r.path for r in diff.unchanged] == ["ok.md"]
