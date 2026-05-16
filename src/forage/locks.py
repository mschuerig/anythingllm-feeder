from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path


class CollectionLocked(Exception):
    pass


if sys.platform.startswith("win"):  # pragma: no cover - exercised on Windows
    import msvcrt

    @contextmanager
    def collection_lock(lock_path: Path):
        """Acquire an exclusive non-blocking lock on `lock_path`.

        Raises `CollectionLocked` if another forage process holds the lock.
        Uses ``msvcrt.locking`` on Windows.
        """
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(lock_path, "ab+")
        try:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                raise CollectionLocked(
                    f"collection locked: {lock_path.parent.name}"
                ) from e
            try:
                yield
            finally:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        finally:
            f.close()
else:
    import errno
    import fcntl

    @contextmanager
    def collection_lock(lock_path: Path):
        """Acquire an exclusive non-blocking flock on `lock_path`.

        Raises `CollectionLocked` if another forage process holds the lock.
        Uses ``fcntl.flock`` on Unix-like systems (macOS, Linux, *BSD).
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
