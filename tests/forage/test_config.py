from __future__ import annotations

from pathlib import Path

import pytest

from forage import config


def test_validate_name_accepts_slugs():
    config.validate_name("news")
    config.validate_name("news-archive")
    config.validate_name("news_v2")
    config.validate_name("a1")


@pytest.mark.parametrize("bad", ["", "News", "-news", "_x", "has space", "ä"])
def test_validate_name_rejects(bad):
    with pytest.raises(config.ConfigError):
        config.validate_name(bad)


def test_parse_source_arg(tmp_path: Path):
    target = tmp_path / "tree"
    target.mkdir()
    name, path = config.parse_source_arg(f"archive={target}")
    assert name == "archive"
    assert path == target.resolve()


@pytest.mark.parametrize("bad", ["archive", "=path", "name=", "Bad=/tmp"])
def test_parse_source_arg_rejects(bad):
    with pytest.raises(config.ConfigError):
        config.parse_source_arg(bad)


def test_collection_config_roundtrip():
    cfg = config.CollectionConfig(
        name="news",
        sources=[
            config.Source(name="a", path="/tmp/a", created_at="2026-05-14T00:00:00Z"),
            config.Source(name="b", path="/tmp/b", created_at="2026-05-14T00:00:01Z"),
        ],
        created_at="2026-05-14T00:00:00Z",
    )
    again = config.CollectionConfig.from_json(cfg.to_json())
    assert again == cfg
    assert again.source("a").path == "/tmp/a"
    assert again.source("missing") is None


def test_collection_config_do_ocr_default_true():
    cfg = config.CollectionConfig(name="x")
    assert cfg.do_ocr is True
    again = config.CollectionConfig.from_json(cfg.to_json())
    assert again.do_ocr is True


def test_collection_config_do_ocr_roundtrip():
    cfg = config.CollectionConfig(name="x", do_ocr=False)
    again = config.CollectionConfig.from_json(cfg.to_json())
    assert again.do_ocr is False


def test_collection_config_do_ocr_legacy_default():
    # Configs written before do_ocr existed should default to True.
    payload = '{"version": 1, "name": "legacy", "created_at": "", "sources": []}'
    cfg = config.CollectionConfig.from_json(payload)
    assert cfg.do_ocr is True
