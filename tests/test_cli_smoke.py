from __future__ import annotations

import json
from pathlib import Path

import pytest

from forage import cli, config, paths


def run(*argv: str) -> int:
    return cli.main(list(argv))


def test_create_list_info_multi_source(
    app_support: Path, source_tree: Path, capsys: pytest.CaptureFixture[str]
):
    rc = run("create", "demo", "--source", f"a={source_tree}", "--source", f"b={source_tree}")
    assert rc == 0

    coll_dir = paths.collection_dir("demo")
    assert coll_dir.is_dir()
    assert paths.collection_config_path("demo").is_file()
    assert paths.collection_db_path("demo").is_file()
    assert paths.source_output_dir("demo", "a").is_dir()
    assert paths.source_output_dir("demo", "b").is_dir()

    cfg = config.load_collection("demo")
    assert [s.name for s in cfg.sources] == ["a", "b"]
    assert all(Path(s.path) == source_tree.resolve() for s in cfg.sources)

    capsys.readouterr()  # discard create output
    assert run("list") == 0
    out = capsys.readouterr().out
    assert "demo" in out and "2 source(s)" in out

    assert run("--json", "list") == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed[0]["name"] == "demo"
    assert parsed[0]["source_count"] == 2

    assert run("info", "demo") == 0
    out = capsys.readouterr().out
    assert "collection: demo" in out
    assert "  - a:" in out and "  - b:" in out
    assert "pending queue: 0" in out

    assert run("--json", "info", "demo") == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["name"] == "demo"
    assert {s["name"] for s in parsed["sources"]} == {"a", "b"}
    assert parsed["pending_queue"] == 0


def test_create_rejects_duplicate(
    app_support: Path, source_tree: Path, capsys: pytest.CaptureFixture[str]
):
    rc = run("create", "demo", "--source", f"a={source_tree}")
    assert rc == 0
    rc = run("create", "demo", "--source", f"a={source_tree}")
    assert rc == 1
    err = capsys.readouterr().err
    assert "already exists" in err


def test_create_rejects_missing_source_path(
    app_support: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    rc = run("create", "demo", "--source", f"a={tmp_path / 'nope'}")
    assert rc == 1
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_create_rejects_duplicate_source_names(
    app_support: Path, source_tree: Path, capsys: pytest.CaptureFixture[str]
):
    rc = run("create", "demo", "--source", f"a={source_tree}", "--source", f"a={source_tree}")
    assert rc == 1
    err = capsys.readouterr().err
    assert "duplicate source name" in err


def test_create_rejects_bad_collection_name(
    app_support: Path, source_tree: Path, capsys: pytest.CaptureFixture[str]
):
    rc = run("create", "Bad-Name", "--source", f"a={source_tree}")
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid collection name" in err


def test_info_unknown_collection(
    app_support: Path, capsys: pytest.CaptureFixture[str]
):
    rc = run("info", "missing")
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err
