from __future__ import annotations

import sys

import pytest

from forage import extractors
from forage.cli import main
from forage.extractors.base import ExtractorError


def test_install_extras_skips_when_both_present(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If both extras report as already importable, the command no-ops."""
    monkeypatch.setattr(
        "forage.commands.install_extras._is_already_installed",
        lambda: (True, True),
    )

    rc = main(["install-extras"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "already installed" in out


def test_install_extras_invokes_pip(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing-extras path calls subprocess.run with the venv's python -m pip install."""
    monkeypatch.setattr(
        "forage.commands.install_extras._is_already_installed",
        lambda: (False, False),
    )

    captured: dict = {}

    class _Result:
        returncode = 0

    def _fake_run(cmd, check=False):
        captured["cmd"] = cmd
        # After "install", the next call to _is_already_installed should
        # report success.
        monkeypatch.setattr(
            "forage.commands.install_extras._is_already_installed",
            lambda: (True, True),
        )
        return _Result()

    monkeypatch.setattr("subprocess.run", _fake_run)

    rc = main(["install-extras"])

    assert rc == 0
    cmd = captured["cmd"]
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-m", "pip", "install"]
    assert "docling" in cmd
    assert "mlx-whisper" in cmd
    assert "done" in capsys.readouterr().out.lower()


def test_get_docling_raises_friendly_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without docling installed, get_docling should suggest install-extras."""
    extractors.clear_registry()

    def _import_docling(*a, **kw):
        raise ImportError("No module named 'docling'", name="docling")

    monkeypatch.setattr(
        "builtins.__import__",
        lambda name, *a, **kw: (
            _import_docling()
            if name == "forage.extractors.docling"
            else __import__(name, *a, **kw)
        ),
    )

    with pytest.raises(ExtractorError) as exc:
        extractors.get_docling(do_ocr=True)
    assert "forage install-extras" in str(exc.value)
