from __future__ import annotations

import platform
import sys
from pathlib import Path

from forage.extractors.base import ExtractionResult, ExtractorError


class DoclingExtractor:
    """Wraps a single docling `DocumentConverter` for the duration of a run.

    `do_ocr` controls whether docling's OCR pass runs on image-bearing PDF
    regions. The native (embedded) text extraction path is unaffected.
    """

    name = "docling"

    def __init__(self, do_ocr: bool = True) -> None:
        self.do_ocr = bool(do_ocr)
        self._converter = None

    def _get_converter(self):
        if self._converter is None:
            try:
                from docling.datamodel.accelerator_options import (
                    AcceleratorDevice,
                    AcceleratorOptions,
                )
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions
                from docling.document_converter import (
                    DocumentConverter,
                    PdfFormatOption,
                )
            except ImportError as e:  # pragma: no cover - exercised manually
                raise ExtractorError(
                    "docling is not installed; install with the 'docling' or 'all' extra"
                ) from e
            pdf_opts = PdfPipelineOptions()
            pdf_opts.do_ocr = self.do_ocr
            # Route docling's layout/table/OCR models through the GPU on Apple
            # Silicon; docling's AUTO has historically picked CPU here, so be
            # explicit. DOCLING_DEVICE / DOCLING_NUM_THREADS env vars still
            # win because AcceleratorOptions reads them on construction.
            is_apple_silicon = (
                sys.platform == "darwin" and platform.machine() == "arm64"
            )
            pdf_opts.accelerator_options = AcceleratorOptions(
                device=(
                    AcceleratorDevice.MPS
                    if is_apple_silicon
                    else AcceleratorDevice.AUTO
                ),
                num_threads=8,
            )
            # Table-structure stays at docling's default (on).
            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts),
                }
            )
        return self._converter

    def extract(self, src: Path) -> ExtractionResult:
        converter = self._get_converter()
        try:
            result = converter.convert(str(src))
            md = result.document.export_to_markdown()
        except Exception as e:
            raise ExtractorError(f"docling: {e}") from e
        if md.strip():
            return ExtractionResult(markdown=md, extractor=self.name)
        if src.suffix.lower() in _HTML_EXTS:
            fallback = _html2text_extract(src)
            if fallback is not None and fallback.strip():
                return ExtractionResult(markdown=fallback, extractor="html2text")
        raise ExtractorError("docling produced empty output")


_HTML_EXTS = frozenset({".html", ".htm"})


def _html2text_extract(src: Path) -> str | None:
    """Best-effort HTML→Markdown conversion as a fallback when docling
    yields empty output. Returns None if html2text isn't importable or the
    file can't be read.
    """
    try:
        import html2text
    except ImportError:
        return None
    try:
        html = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_images = True
    return h.handle(html)
