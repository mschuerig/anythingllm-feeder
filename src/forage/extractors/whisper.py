from __future__ import annotations

import re
import subprocess
from pathlib import Path

from forage.extractors.base import ExtractionResult, ExtractorError

# ---------------------------------------------------------------------------
# Heuristic constants — easy to tune.
# ---------------------------------------------------------------------------
BOILERPLATE_PHRASES: tuple[str, ...] = (
    "thanks for watching",
    "please subscribe",
    "subscribe to my channel",
    "see you next time",
    "danke fürs zuschauen",
    "bis zum nächsten mal",
)
SHORT_TRANSCRIPT_CHARS = 200
REPETITION_THRESHOLD = 4
DENSITY_MIN_DURATION_SECONDS = 300
DENSITY_WORDS_PER_SECOND = 0.3
LOGPROB_THRESHOLD = -1.0
TIMESTAMP_INTERVAL_SECONDS = 300  # one heading every 5 minutes

LANGUAGE_HINTS: dict[str, str] = {
    "de": "de", "deu": "de", "deutsch": "de", "german": "de",
    "en": "en", "eng": "en", "english": "en",
}
DEFAULT_LANGUAGE = "en"

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


class NoAudioStream(ExtractorError):
    """Raised when ffprobe finds no audio stream in the file."""


# ---------------------------------------------------------------------------
# ffprobe + language detection
# ---------------------------------------------------------------------------
def has_audio_stream(src: Path) -> bool:
    """Return True if ffprobe reports at least one audio stream."""
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0",
                str(src),
            ],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError as e:
        raise ExtractorError("ffprobe not found; install ffmpeg") from e
    if proc.returncode != 0:
        raise ExtractorError(f"ffprobe failed: {proc.stderr.strip()}")
    return bool(proc.stdout.strip())


def guess_language(src: Path) -> str:
    """Look for de/en hints in the filename or any parent directory name."""
    parts = list(src.parts) + [src.stem]
    for part in parts:
        for tok in re.split(r"[^a-zA-Z]+", part):
            tok = tok.lower()
            if tok in LANGUAGE_HINTS:
                return LANGUAGE_HINTS[tok]
    return DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------
def format_markdown(
    src: Path, segments: list[dict], language: str
) -> str:
    """Render segments to Markdown with timestamp section headings."""
    lines: list[str] = ["# Transcript", ""]
    lines.append(f"- Source: {src.name}")
    duration = segments[-1].get("end", 0) if segments else 0
    lines.append(f"- Duration: {_format_duration(duration)}")
    lines.append(f"- Language: {language}")
    lines.append("")
    if not segments:
        lines.append("(empty transcript)")
        return "\n".join(lines) + "\n"

    current_bucket: int | None = None
    body: list[str] = []
    for seg in segments:
        start = float(seg.get("start", 0) or 0)
        bucket = int(start // TIMESTAMP_INTERVAL_SECONDS) * TIMESTAMP_INTERVAL_SECONDS
        if bucket != current_bucket:
            if body:
                lines.append("")
            lines.append(f"## {_format_timestamp(bucket)}")
            lines.append("")
            current_bucket = bucket
            body = lines
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines).rstrip() + "\n"


def _format_timestamp(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# Hallucination heuristics
# ---------------------------------------------------------------------------
def run_heuristics(segments: list[dict]) -> list[str]:
    reasons: list[str] = []
    if _has_repetition(segments):
        reasons.append(
            f"repetition: same segment text ≥{REPETITION_THRESHOLD} times consecutively"
        )
    if _has_boilerplate(segments):
        reasons.append(
            "boilerplate: short transcript matches a known intro/outro phrase"
        )
    duration = float(segments[-1].get("end", 0) or 0) if segments else 0.0
    if duration > DENSITY_MIN_DURATION_SECONDS:
        text = " ".join((s.get("text") or "") for s in segments)
        word_count = len(text.split())
        density = word_count / duration if duration else 0
        if density < DENSITY_WORDS_PER_SECOND:
            reasons.append(
                f"low density: {word_count} words / {duration:.0f}s = {density:.3f}"
            )
    avg = _mean_logprob(segments)
    if avg is not None and avg < LOGPROB_THRESHOLD:
        reasons.append(f"low confidence: mean avg_logprob = {avg:.3f}")
    return reasons


def _has_repetition(segments: list[dict]) -> bool:
    streak = 0
    last: str | None = None
    for seg in segments:
        text = (seg.get("text") or "").strip().lower()
        if not text:
            continue
        if text == last:
            streak += 1
            if streak >= REPETITION_THRESHOLD:
                return True
        else:
            streak = 1
            last = text
    return False


def _has_boilerplate(segments: list[dict]) -> bool:
    text = " ".join((s.get("text") or "") for s in segments).lower()
    if len(text) > SHORT_TRANSCRIPT_CHARS:
        return False
    return any(p in text for p in BOILERPLATE_PHRASES)


def _mean_logprob(segments: list[dict]) -> float | None:
    vals = [
        float(s["avg_logprob"])
        for s in segments
        if s.get("avg_logprob") is not None
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------
class WhisperExtractor:
    name = "mlx-whisper"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def extract(self, src: Path) -> ExtractionResult:
        if not has_audio_stream(src):
            raise NoAudioStream(f"no audio stream: {src}")
        try:
            import mlx_whisper
        except ImportError as e:  # pragma: no cover - exercised manually
            raise ExtractorError(
                "mlx-whisper is not installed; install with the 'whisper' or 'all' extra"
            ) from e
        language = guess_language(src)
        try:
            result = mlx_whisper.transcribe(
                str(src),
                path_or_hf_repo=self.model,
                language=language,
                verbose=False,
            )
        except Exception as e:
            raise ExtractorError(f"mlx-whisper: {e}") from e
        segments = result.get("segments", []) or []
        markdown = format_markdown(src, segments, language)
        return ExtractionResult(
            markdown=markdown,
            extractor=self.name,
            suspicious_reasons=run_heuristics(segments),
        )
