from __future__ import annotations

from dataclasses import dataclass, field


class ExtractorError(Exception):
    pass


@dataclass
class ExtractionResult:
    markdown: str
    extractor: str
    suspicious_reasons: list[str] = field(default_factory=list)
