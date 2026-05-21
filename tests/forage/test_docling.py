from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from forage.extractors.base import ExtractorError
from forage.extractors.docling import DoclingExtractor


class _StubConverter:
    def __init__(self, markdown: str) -> None:
        self._md = markdown

    def convert(self, _src: str):
        doc = SimpleNamespace(export_to_markdown=lambda: self._md)
        return SimpleNamespace(document=doc)


def test_empty_markdown_raises_for_non_html(tmp_path: Path):
    src = tmp_path / "fake.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    ext = DoclingExtractor(do_ocr=False)
    ext._converter = _StubConverter("")
    with pytest.raises(ExtractorError, match="empty output"):
        ext.extract(src)


def test_whitespace_only_markdown_raises_for_non_html(tmp_path: Path):
    src = tmp_path / "fake.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    ext = DoclingExtractor(do_ocr=False)
    ext._converter = _StubConverter("   \n\n  \t\n")
    with pytest.raises(ExtractorError, match="empty output"):
        ext.extract(src)


def test_non_empty_markdown_returns_result(tmp_path: Path):
    src = tmp_path / "fake.html"
    src.write_text("<html><body>hello</body></html>")
    ext = DoclingExtractor(do_ocr=False)
    ext._converter = _StubConverter("# Title\n\nbody\n")
    res = ext.extract(src)
    assert res.markdown == "# Title\n\nbody\n"
    assert res.extractor == "docling"


def test_empty_docling_html_falls_back_to_html2text(tmp_path: Path):
    """When docling yields empty for an HTML file, html2text rescues it."""
    pytest.importorskip("html2text")
    src = tmp_path / "page.html"
    src.write_text(
        "<html><body><h1>Pluralism</h1>"
        "<p>Gould on Dennett.</p></body></html>"
    )
    ext = DoclingExtractor(do_ocr=False)
    ext._converter = _StubConverter("")
    res = ext.extract(src)
    assert res.extractor == "html2text"
    assert "Pluralism" in res.markdown
    assert "Gould on Dennett" in res.markdown


def test_empty_docling_htm_extension_also_falls_back(tmp_path: Path):
    pytest.importorskip("html2text")
    src = tmp_path / "page.HTM"  # extension match is case-insensitive
    src.write_text("<html><body><p>visible</p></body></html>")
    ext = DoclingExtractor(do_ocr=False)
    ext._converter = _StubConverter("")
    res = ext.extract(src)
    assert res.extractor == "html2text"
    assert "visible" in res.markdown


def test_html_fallback_still_empty_raises(tmp_path: Path):
    """If even html2text produces nothing useful, surface as failed."""
    pytest.importorskip("html2text")
    src = tmp_path / "blank.html"
    src.write_text("<html><body>   </body></html>")
    ext = DoclingExtractor(do_ocr=False)
    ext._converter = _StubConverter("")
    with pytest.raises(ExtractorError, match="empty output"):
        ext.extract(src)


def test_html_fallback_skipped_when_html2text_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """If html2text isn't importable, the fallback is silent — we raise the
    same empty-output error as if it had never been tried."""
    src = tmp_path / "page.html"
    src.write_text("<html><body><p>x</p></body></html>")
    ext = DoclingExtractor(do_ocr=False)
    ext._converter = _StubConverter("")

    import builtins
    real_import = builtins.__import__

    def _no_html2text(name, *a, **kw):
        if name == "html2text":
            raise ImportError("No module named 'html2text'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_html2text)
    with pytest.raises(ExtractorError, match="empty output"):
        ext.extract(src)
