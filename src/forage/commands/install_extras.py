"""Install the optional heavy dependencies into forage's own venv.

`anythingllm-feeder` ships a small core (httpx + send2trash + shtab) and
declares `docling` and `mlx-whisper` as optional extras. When installed
via Homebrew, the core gets installed up front and this command pulls in
the heavy extras as a separate step — the brew install path itself
can't carry them cleanly (their wheels conflict with brew's post-install
Mach-O relocator and brew's build sandbox blocks the source-build
workaround).

When installed via `uv sync --extra all` from source, this command is a
no-op — the extras are already there.

Implementation: locate the venv's Python via ``sys.executable`` and call
``python -m pip install docling mlx-whisper``. That works regardless of
how the venv was built.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

EXTRAS = ("docling", "mlx-whisper")


def _is_already_installed() -> tuple[bool, bool]:
    """Return (has_docling, has_mlx_whisper) without importing the heavy code."""
    import importlib.util

    return (
        importlib.util.find_spec("docling") is not None,
        importlib.util.find_spec("mlx_whisper") is not None,
    )


def cmd_install_extras(args: argparse.Namespace) -> int:
    has_docling, has_whisper = _is_already_installed()

    if has_docling and has_whisper and not getattr(args, "force", False):
        print("extras already installed (docling, mlx-whisper)")
        return 0

    pkgs = list(EXTRAS)
    print(f"installing extras into {sys.prefix}:")
    print(f"  pip target: {sys.executable}")
    print(f"  packages: {' '.join(pkgs)}")
    print("this can take a few minutes — docling pulls in PyTorch.")
    print()

    cmd = [sys.executable, "-m", "pip", "install"]
    if getattr(args, "upgrade", False):
        cmd.append("--upgrade")
    cmd.extend(pkgs)
    try:
        rc = subprocess.run(cmd, check=False).returncode
    except OSError as exc:
        print(f"error: could not run pip: {exc}", file=sys.stderr)
        return 2
    if rc != 0:
        print(f"error: pip install failed with exit code {rc}", file=sys.stderr)
        return rc

    has_docling, has_whisper = _is_already_installed()
    missing = []
    if not has_docling:
        missing.append("docling")
    if not has_whisper:
        missing.append("mlx-whisper")
    if missing:
        print(
            f"warning: pip reported success but {', '.join(missing)} is "
            "still not importable in this interpreter",
            file=sys.stderr,
        )
        return 1
    print("done. forage can now extract documents and transcribe audio/video.")
    return 0
