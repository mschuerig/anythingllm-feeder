from __future__ import annotations

from pathlib import Path

from forage import db


def make_db(tmp_path: Path) -> Path:
    p = tmp_path / "state.db"
    with db.open_db(p) as conn:
        db.init_schema(conn)
    return p


def test_schema_version_recorded(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert row["value"] == str(db.SCHEMA_VERSION)


def test_upsert_and_get_file(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        row = db.FileRow(
            source="a",
            path="x/y.pdf",
            sha256="deadbeef",
            mtime=1.0,
            size=42,
            output_path="a/x/y.md",
            extractor="docling",
            status="ok",
            extracted_at="2026-05-14T00:00:00Z",
            updated_at="2026-05-14T00:00:00Z",
        )
        db.upsert_file(conn, row)
        got = db.get_file(conn, "a", "x/y.pdf")
        assert got == row

        # Update: new sha + status
        row2 = db.FileRow(
            source="a",
            path="x/y.pdf",
            sha256="cafef00d",
            mtime=2.0,
            size=43,
            output_path="a/x/y.md",
            extractor="docling",
            status="ok",
            extracted_at="2026-05-14T01:00:00Z",
            updated_at="2026-05-14T01:00:00Z",
        )
        db.upsert_file(conn, row2)
        got = db.get_file(conn, "a", "x/y.pdf")
        assert got.sha256 == "cafef00d"
        assert got.size == 43


def test_composite_pk_allows_same_path_in_two_sources(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        db.upsert_file(conn, db.FileRow(source="a", path="dup.pdf", status="ok"))
        db.upsert_file(conn, db.FileRow(source="b", path="dup.pdf", status="ok"))
        assert len(list(db.iter_files(conn))) == 2
        assert len(list(db.iter_files(conn, "a"))) == 1


def test_status_counts(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        db.upsert_file(conn, db.FileRow(source="a", path="1", status="ok"))
        db.upsert_file(conn, db.FileRow(source="a", path="2", status="ok"))
        db.upsert_file(conn, db.FileRow(source="a", path="3", status="failed"))
        db.upsert_file(conn, db.FileRow(source="b", path="1", status="ok"))
        assert db.status_counts(conn) == {"ok": 3, "failed": 1}
        assert db.status_counts(conn, "a") == {"ok": 2, "failed": 1}
        assert db.status_counts(conn, "b") == {"ok": 1}


def test_queue_lifecycle(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        db.upsert_file(conn, db.FileRow(source="a", path="v.mp4", status="pending"))
        db.enqueue(conn, "a", "v.mp4", "2026-05-14T00:00:00Z")
        assert db.queue_depth(conn, "pending") == 1
        row = db.dequeue_oldest(conn, limit=1)[0]
        assert row["source"] == "a" and row["path"] == "v.mp4"
        db.update_queue(conn, "a", "v.mp4", "running",
                        started_at="2026-05-14T00:00:10Z")
        db.update_queue(conn, "a", "v.mp4", "done",
                        finished_at="2026-05-14T00:00:20Z")
        assert db.queue_depth(conn, "pending") == 0
        assert db.queue_depth(conn, "done") == 1


def test_delete_file_cascades_queue(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        db.upsert_file(conn, db.FileRow(source="a", path="v.mp4", status="pending"))
        db.enqueue(conn, "a", "v.mp4", "2026-05-14T00:00:00Z")
        db.delete_file(conn, "a", "v.mp4")
        assert db.queue_depth(conn, "pending") == 0
        assert db.get_file(conn, "a", "v.mp4") is None


def test_integrity_check(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        assert db.integrity_check(conn) == ["ok"]


def test_reset_db(tmp_path: Path):
    p = make_db(tmp_path)
    with db.open_db(p) as conn:
        db.upsert_file(conn, db.FileRow(source="a", path="x", status="ok"))
    db.reset_db(p)
    assert not p.exists()
    # Reopen + init: should be empty
    with db.open_db(p) as conn:
        db.init_schema(conn)
        assert list(db.iter_files(conn)) == []
