from __future__ import annotations

import os
import tempfile
from pathlib import Path, PurePosixPath


def output_relpath(source_name: str, source_relpath: str) -> str:
    """Path relative to a collection's output/ for the given source file.

    `source_relpath` is the source file's path relative to its source root,
    using forward slashes. The result has its extension replaced with `.md`
    and is prefixed with the source name.
    """
    p = PurePosixPath(source_relpath)
    return str(PurePosixPath(source_name) / p.with_suffix(".md"))


def write_atomic(target: Path, text: str) -> None:
    """Write `text` to `target` atomically via a sibling tempfile + rename."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
