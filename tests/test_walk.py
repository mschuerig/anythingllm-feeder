from __future__ import annotations

import os
import time
from pathlib import Path

from forage import config, db, walk


def _stat_for(p: Path) -> tuple[float, int]:
    s = p.stat()
    return s.st_mtime, s.st_size


def test_iter_source_filters_and_skips_dotfiles(tmp_path: Path):
    root = tmp_path / "src"
    (root / "a").mkdir(parents=True)
    (root / "a" / "doc.pdf").write_bytes(b"x")
    (root / "a" / "note.md").write_text("hi")
    (root / "a" / "image.jpg").write_bytes(b"jpg")  # unsupported -> skipped
    (root / ".hidden").write_text("nope")           # dotfile -> skipped
    (root / ".cache").mkdir()
    (root / ".cache" / "stale.pdf").write_bytes(b"x")  # under dotdir -> skipped

    rels = sorted(rel for rel, _, _ in walk.iter_source(root))
    assert rels == ["a/doc.pdf", "a/note.md"]


def test_iter_source_explicit_ext_filter(tmp_path: Path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.pdf").write_bytes(b"x")
    (root / "b.md").write_text("y")
    rels = sorted(rel for rel, _, _ in walk.iter_source(root, exts={".pdf"}))
    assert rels == ["a.pdf"]


def test_parse_ext_filter():
    assert walk.parse_ext_filter(None) is None
    assert walk.parse_ext_filter("") is None
    assert walk.parse_ext_filter("pdf,mp4") == frozenset({".pdf", ".mp4"})
    assert walk.parse_ext_filter(" .PDF, mp4 ") == frozenset({".pdf", ".mp4"})


def _src_cfg(name: str, root: Path) -> config.Source:
    return config.Source(name=name, path=str(root), created_at="t")


def test_classify_new(tmp_path: Path):
    cls, sha = walk.classify(None, 1.0, 1, tmp_path)
    assert cls is walk.Classification.NEW
    assert sha is None


def test_classify_unchanged(tmp_path: Path):
    f = tmp_path / "a"
    f.write_text("hi")
    mtime, size = _stat_for(f)
    prior = db.FileRow(source="s", path="a", sha256="abc", mtime=mtime, size=size)
    cls, sha = walk.classify(prior, mtime, size, f)
    assert cls is walk.Classification.UNCHANGED
    assert sha is None


def test_classify_touched(tmp_path: Path):
    f = tmp_path / "a"
    f.write_text("hello")
    import hashlib
    real_sha = hashlib.sha256(b"hello").hexdigest()
    mtime, size = _stat_for(f)
    prior = db.FileRow(
        source="s", path="a", sha256=real_sha, mtime=mtime - 100, size=size
    )
    cls, sha = walk.classify(prior, mtime, size, f)
    assert cls is walk.Classification.TOUCHED
    assert sha == real_sha


def test_classify_changed(tmp_path: Path):
    f = tmp_path / "a"
    f.write_text("hello")
    import hashlib
    new_sha = hashlib.sha256(b"hello").hexdigest()
    mtime, size = _stat_for(f)
    prior = db.FileRow(
        source="s", path="a", sha256="oldsha", mtime=mtime - 100, size=size + 1
    )
    cls, sha = walk.classify(prior, mtime, size, f)
    assert cls is walk.Classification.CHANGED
    assert sha == new_sha


def test_walk_source_against_db(tmp_path: Path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "new.md").write_text("new")
    (root / "same.md").write_text("same content")
    (root / "touched.md").write_text("touched")
    (root / "changed.md").write_text("original")
    db_path = tmp_path / "state.db"
    with db.open_db(db_path) as conn:
        db.init_schema(conn)
        same_mtime, same_size = _stat_for(root / "same.md")
        touched_mtime, touched_size = _stat_for(root / "touched.md")
        changed_mtime, changed_size = _stat_for(root / "changed.md")

        import hashlib
        same_sha = hashlib.sha256(b"same content").hexdigest()
        touched_sha = hashlib.sha256(b"touched").hexdigest()
        db.upsert_file(
            conn,
            db.FileRow(
                source="s", path="same.md", sha256=same_sha,
                mtime=same_mtime, size=same_size, status="ok",
            ),
        )
        db.upsert_file(
            conn,
            db.FileRow(
                source="s", path="touched.md", sha256=touched_sha,
                mtime=touched_mtime - 100, size=touched_size, status="ok",
            ),
        )
        db.upsert_file(
            conn,
            db.FileRow(
                source="s", path="changed.md", sha256="stale-different-sha",
                mtime=changed_mtime - 100, size=changed_size + 5, status="ok",
            ),
        )

        items = {it.rel: it for it in walk.walk_source(conn, _src_cfg("s", root))}

    assert items["new.md"].classification is walk.Classification.NEW
    assert items["same.md"].classification is walk.Classification.UNCHANGED
    assert items["touched.md"].classification is walk.Classification.TOUCHED
    assert items["touched.md"].sha256 == touched_sha
    assert items["changed.md"].classification is walk.Classification.CHANGED
    assert items["changed.md"].sha256 is not None
    assert items["changed.md"].sha256 != "stale-different-sha"


def test_find_orphans(tmp_path: Path):
    root_a = tmp_path / "a"
    root_a.mkdir()
    (root_a / "live.md").write_text("live")

    db_path = tmp_path / "state.db"
    with db.open_db(db_path) as conn:
        db.init_schema(conn)
        db.upsert_file(conn, db.FileRow(source="a", path="live.md", status="ok"))
        db.upsert_file(conn, db.FileRow(source="a", path="gone.md", status="ok"))
        db.upsert_file(conn, db.FileRow(source="removed", path="x.md", status="ok"))

        sources = [_src_cfg("a", root_a)]
        orphans = walk.find_orphans(conn, sources)
        paths_seen = {(o.source, o.path) for o in orphans}
        assert paths_seen == {("a", "gone.md"), ("removed", "x.md")}

        orphans_a = walk.find_orphans(conn, sources, source_filter="a")
        assert {(o.source, o.path) for o in orphans_a} == {("a", "gone.md")}
