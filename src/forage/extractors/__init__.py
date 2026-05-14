from __future__ import annotations

from pathlib import Path
from typing import Protocol

from forage.extractors.base import ExtractionResult, ExtractorError

DOCLING_EXTS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".txt", ".md"}
)
WHISPER_EXTS: frozenset[str] = frozenset(
    {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
)
ALL_EXTS: frozenset[str] = DOCLING_EXTS | WHISPER_EXTS


def extractor_for(path: Path) -> str | None:
    """Return the extractor name for a path, or None if unsupported."""
    ext = path.suffix.lower()
    if ext in DOCLING_EXTS:
        return "docling"
    if ext in WHISPER_EXTS:
        return "mlx-whisper"
    return None


def is_video(path: Path) -> bool:
    return path.suffix.lower() in WHISPER_EXTS


class Extractor(Protocol):
    name: str
    def extract(self, src: Path) -> ExtractionResult: ...


_REGISTRY: dict[str, Extractor] = {}


def get_extractor(name: str) -> Extractor:
    """Return a cached extractor instance by name. Imports lazily."""
    if name not in _REGISTRY:
        if name == "docling":
            from forage.extractors.docling import DoclingExtractor
            _REGISTRY[name] = DoclingExtractor()
        elif name == "mlx-whisper":
            from forage.extractors.whisper import WhisperExtractor
            _REGISTRY[name] = WhisperExtractor()
        else:
            raise ExtractorError(f"unknown extractor: {name}")
    return _REGISTRY[name]


def clear_registry() -> None:
    """Drop cached extractor instances (used by tests)."""
    _REGISTRY.clear()
