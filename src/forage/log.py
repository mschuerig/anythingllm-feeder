from __future__ import annotations

import logging
from pathlib import Path

from _shared import log as _shared_log

LOGGER_NAME = "forage"


def setup_logging(*, verbose: bool = False, quiet: bool = False) -> logging.Logger:
    return _shared_log.setup_logging(LOGGER_NAME, verbose=verbose, quiet=quiet)


def add_collection_log(log_path: Path) -> logging.Handler:
    return _shared_log.add_file_log(LOGGER_NAME, log_path)


def remove_handler(handler: logging.Handler) -> None:
    _shared_log.remove_handler(LOGGER_NAME, handler)


def get_logger() -> logging.Logger:
    return _shared_log.get_logger(LOGGER_NAME)
