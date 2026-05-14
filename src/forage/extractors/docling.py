from __future__ import annotations

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
        return ExtractionResult(markdown=md, extractor=self.name)
