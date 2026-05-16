"""Regenerate man pages for forage and ingest into ``man/``.

Run with ``uv run python scripts/build_manpages.py``. Requires the ``dev``
extra (argparse-manpage). The generated files (``man/forage.1`` and
``man/ingest.1``) are committed so the Homebrew formula can install them
without pulling argparse-manpage into the install-time closure.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAN_DIR = REPO_ROOT / "man"

PAGES = [
    {
        "module": "forage.cli",
        "function": "build_parser",
        "prog": "forage",
        "output": "forage.1",
        "description": (
            "Extract documents and videos to Markdown, organized as "
            "named collections of sources."
        ),
    },
    {
        "module": "ingest.cli",
        "function": "build_parser",
        "prog": "ingest",
        "output": "ingest.1",
        "description": (
            "Upload forage's extracted Markdown into a local AnythingLLM "
            "instance, one workspace per collection."
        ),
    },
]


def _project_metadata() -> tuple[str, str, str, str]:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    project = pyproject["project"]
    version = project["version"]
    project_name = project["name"]
    author = project["authors"][0]["name"]
    homepage = "https://github.com/mschuerig/anythingllm-feeder"
    return version, project_name, author, homepage


def main() -> int:
    MAN_DIR.mkdir(exist_ok=True)
    version, project_name, author, homepage = _project_metadata()

    for page in PAGES:
        out_path = MAN_DIR / page["output"]
        cmd = [
            "argparse-manpage",
            "--module", page["module"],
            "--function", page["function"],
            "--prog", page["prog"],
            "--project-name", project_name,
            "--version", version,
            "--author", author,
            "--url", homepage,
            "--description", page["description"],
            "--format", "single-commands-section",
            "--output", str(out_path),
        ]
        print(f"writing {out_path}")
        subprocess.run(cmd, check=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
