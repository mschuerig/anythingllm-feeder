from __future__ import annotations

from pathlib import Path

from ingest import state


def test_init_and_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "uploads.db"
    with state.open_db(db) as conn:
        assert list(state.iter_uploads(conn)) == []
        u = state.Upload(
            source="s",
            path="a.md",
            sha256="HASH",
            anythingllm_loc="custom-documents/x.json",
            workspace_slug="forage-c",
            uploaded_at="2026-05-15T00:00:00Z",
            forage_status="ok",
        )
        state.upsert_upload(conn, u)
        got = state.get_upload(conn, "s", "a.md")
        assert got == u

        # upsert: change sha and location
        u2 = state.Upload(
            source="s",
            path="a.md",
            sha256="HASH2",
            anythingllm_loc="custom-documents/y.json",
            workspace_slug="forage-c",
            uploaded_at="2026-05-15T01:00:00Z",
            forage_status="ok",
        )
        state.upsert_upload(conn, u2)
        got2 = state.get_upload(conn, "s", "a.md")
        assert got2 == u2
        assert len(list(state.iter_uploads(conn))) == 1

        state.delete_upload(conn, "s", "a.md")
        assert state.get_upload(conn, "s", "a.md") is None


def test_reset_removes_files(tmp_path: Path) -> None:
    db = tmp_path / "uploads.db"
    with state.open_db(db) as conn:
        state.upsert_upload(
            conn,
            state.Upload(
                source="s",
                path="a",
                sha256="h",
                anythingllm_loc="loc",
                workspace_slug="w",
                uploaded_at="t",
            ),
        )
    state.reset_db(db)
    assert not db.exists()
