from __future__ import annotations

import errno
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path


class CollectionLocked(Exception):
    pass


@contextmanager
def collection_lock(lock_path: Path):
    """Acquire an exclusive non-blocking flock on `lock_path`.

    Raises `CollectionLocked` if another forage process holds the lock.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise CollectionLocked(
                    f"collection locked: {lock_path.parent.name}"
                ) from e
            raise
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)
