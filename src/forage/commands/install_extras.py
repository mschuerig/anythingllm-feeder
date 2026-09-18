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
``python -m pip install docling[<ocr engine>] mlx-whisper``. That works
regardless of how the venv was built.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

# docling's OCR engine is auto-selected when the PDF pipeline is first built.
# With no engine extra installed it falls through to rapidocr-on-torch, which
# asks rapidocr for PP-OCRv6 weights that only ship for the onnxruntime
# backend -> "Unsupported configuration: torch.PP-OCRv6.det.small", and every
# PDF in the run fails. Install an engine that resolves: Apple Vision via
# ocrmac on macOS (native, no model downloads), rapidocr-on-onnxruntime
# elsewhere.
_DOCLING = "docling[ocrmac]" if sys.platform == "darwin" else "docling[rapidocr]"
# Module that has to be importable for the engine above to be usable. Checked
# alongside docling itself so an install predating the engine extra gets it
# pulled in on the next run instead of reporting "already installed".
_OCR_ENGINE_MODULE = "ocrmac" if sys.platform == "darwin" else "onnxruntime"

EXTRAS = (_DOCLING, "html2text", "mlx-whisper")

# transformers 5.9.0 regressed RT-DETR v2 (docling's layout model): it
# allocates float64 tensors on the model's device, which Apple's MPS backend
# rejects, so every PDF fails on Apple Silicon. Pin until upstream fixes 5.9.x.
EXTRA_CONSTRAINTS = ("transformers!=5.9.0",)


def _is_already_installed() -> tuple[bool, bool, bool]:
    """Return (has_docling, has_html2text, has_mlx_whisper) without importing
    the heavy code. "has_docling" means docling *and* a working OCR engine."""
    import importlib.util

    return (
        importlib.util.find_spec("docling") is not None
        and importlib.util.find_spec(_OCR_ENGINE_MODULE) is not None,
        importlib.util.find_spec("html2text") is not None,
        importlib.util.find_spec("mlx_whisper") is not None,
    )


def cmd_install_extras(args: argparse.Namespace) -> int:
    has_docling, has_html2text, has_whisper = _is_already_installed()

    if has_docling and has_html2text and has_whisper and not getattr(args, "force", False):
        print(f"extras already installed ({_DOCLING}, html2text, mlx-whisper)")
        return 0

    pkgs = list(EXTRAS) + list(EXTRA_CONSTRAINTS)
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

    has_docling, has_html2text, has_whisper = _is_already_installed()
    missing = []
    if not has_docling:
        missing.append(_DOCLING)
    if not has_html2text:
        missing.append("html2text")
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
