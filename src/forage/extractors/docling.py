from __future__ import annotations

from pathlib import Path

from forage.extractors.base import ExtractionResult, ExtractorError


class DoclingExtractor:
    """Wraps a single docling `DocumentConverter` for the duration of a run."""

    name = "docling"

    def __init__(self) -> None:
        self._converter = None

    def _get_converter(self):
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter
            except ImportError as e:  # pragma: no cover - exercised manually
                raise ExtractorError(
                    "docling is not installed; install with the 'docling' or 'all' extra"
                ) from e
            self._converter = DocumentConverter()
        return self._converter

    def extract(self, src: Path) -> ExtractionResult:
        converter = self._get_converter()
        try:
            result = converter.convert(str(src))
            md = result.document.export_to_markdown()
        except Exception as e:
            raise ExtractorError(f"docling: {e}") from e
        return ExtractionResult(markdown=md, extractor=self.name)
