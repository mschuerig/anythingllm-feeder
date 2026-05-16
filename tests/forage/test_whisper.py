from __future__ import annotations

from pathlib import Path

import pytest

from forage.extractors import whisper


def test_format_markdown_basic(tmp_path: Path):
    segments = [
        {"start": 0.0, "end": 4.0, "text": " Hello there."},
        {"start": 4.0, "end": 8.0, "text": " More text."},
        {"start": 305.0, "end": 310.0, "text": " After five minutes."},
    ]
    src = tmp_path / "video.mp4"
    md = whisper.format_markdown(src, segments, "en")
    assert md.startswith("# Transcript")
    assert "- Source: video.mp4" in md
    assert "- Language: en" in md
    assert "## 00:00" in md
    assert "## 05:00" in md
    assert "Hello there." in md
    assert "After five minutes." in md


def test_format_markdown_empty(tmp_path: Path):
    md = whisper.format_markdown(tmp_path / "silent.mp4", [], "en")
    assert "(empty transcript)" in md


def test_guess_language(tmp_path: Path):
    assert whisper.guess_language(Path("/a/b/clip_de.mp4")) == "de"
    assert whisper.guess_language(Path("/a/german/clip.mp4")) == "de"
    assert whisper.guess_language(Path("/a/english/clip.mp4")) == "en"
    assert whisper.guess_language(Path("/a/b/clip.mp4")) == "en"  # default


def test_heuristics_repetition():
    segs = [
        {"start": i, "end": i + 1, "text": "loop"} for i in range(10)
    ]
    reasons = whisper.run_heuristics(segs)
    assert any("repetition" in r for r in reasons)


def test_heuristics_boilerplate_short():
    segs = [
        {"start": 0, "end": 4, "text": "Thanks for watching! Please subscribe."}
    ]
    reasons = whisper.run_heuristics(segs)
    assert any("boilerplate" in r for r in reasons)


def test_heuristics_no_boilerplate_when_long():
    text = "Thanks for watching! " + "X" * 300
    segs = [{"start": 0, "end": 4, "text": text}]
    reasons = whisper.run_heuristics(segs)
    assert not any("boilerplate" in r for r in reasons)


def test_heuristics_low_density():
    # 600s video, only 10 words -> density 0.0167
    segs = [
        {"start": 0, "end": 600, "text": "one two three four five six seven eight nine ten"}
    ]
    reasons = whisper.run_heuristics(segs)
    assert any("density" in r for r in reasons)


def test_heuristics_low_confidence():
    segs = [
        {"start": 0, "end": 1, "text": "x", "avg_logprob": -1.5},
        {"start": 1, "end": 2, "text": "y", "avg_logprob": -1.2},
    ]
    reasons = whisper.run_heuristics(segs)
    assert any("confidence" in r for r in reasons)


def test_heuristics_clean():
    segs = [
        {"start": 0, "end": 30, "text": "well-paced normal speech " * 10,
         "avg_logprob": -0.3},
        {"start": 30, "end": 60, "text": "more normal content here " * 10,
         "avg_logprob": -0.3},
    ]
    assert whisper.run_heuristics(segs) == []


def test_parse_duration():
    from forage.commands.transcribe import parse_duration
    assert parse_duration("90s") == 90
    assert parse_duration("90") == 90
    assert parse_duration("5m") == 300
    assert parse_duration("2h") == 7200
    assert parse_duration(" 4H ") == 4 * 3600
    import pytest
    from forage.config import ConfigError
    with pytest.raises(ConfigError):
        parse_duration("bogus")
