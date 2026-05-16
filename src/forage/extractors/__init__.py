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


_REGISTRY: dict = {}


def get_extractor(name: str) -> Extractor:
    """Return a cached extractor instance by name.

    For docling use `get_docling(do_ocr=…)` instead, and for whisper use
    `get_whisper(model=…)` — both need configuration that doesn't fit a
    name-only lookup.
    """
    if name == "docling":
        # Default: OCR on. Callers wanting to honor per-collection config
        # should use `get_docling` instead.
        return get_docling(do_ocr=True)
    if name == "mlx-whisper":
        return get_whisper()
    raise ExtractorError(f"unknown extractor: {name}")


_EXTRAS_HINT = (
    "Run `forage install-extras` to add docling (PDF/Office) and "
    "mlx-whisper (audio/video) to this install."
)


def get_docling(*, do_ocr: bool) -> Extractor:
    """Return a docling extractor configured for the given OCR setting.

    Cached per `do_ocr` value, so toggling between collections won't reload
    docling's models on every switch (one cached instance per setting).
    """
    key = ("docling", bool(do_ocr))
    if key not in _REGISTRY:
        try:
            from forage.extractors.docling import DoclingExtractor
        except ImportError as exc:
            raise ExtractorError(
                f"docling is not installed in this Python ({exc.name}). "
                + _EXTRAS_HINT
            ) from exc
        _REGISTRY[key] = DoclingExtractor(do_ocr=do_ocr)
    return _REGISTRY[key]


def get_whisper(model: str | None = None) -> Extractor:
    """Return a cached WhisperExtractor.

    Pass ``model`` to use a specific HF model id; otherwise the extractor's
    built-in DEFAULT_MODEL is used.

    The "default" case (``model is None``) is cached under the plain string
    key ``"mlx-whisper"``, so test stubs that pre-populate ``_REGISTRY`` with
    that key (the convention before per-model caching existed) keep working.
    Explicit models are cached under ``("mlx-whisper", model)``.
    """
    if model is None:
        key: object = "mlx-whisper"
    else:
        key = ("mlx-whisper", model)
    if key not in _REGISTRY:
        try:
            from forage.extractors.whisper import WhisperExtractor
        except ImportError as exc:
            raise ExtractorError(
                f"mlx-whisper is not installed in this Python ({exc.name}). "
                + _EXTRAS_HINT
            ) from exc
        _REGISTRY[key] = (
            WhisperExtractor() if model is None else WhisperExtractor(model=model)
        )
    return _REGISTRY[key]


def clear_registry() -> None:
    """Drop cached extractor instances (used by tests)."""
    _REGISTRY.clear()
