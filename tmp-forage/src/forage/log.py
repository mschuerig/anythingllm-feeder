from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "forage"

_FILE_FMT = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s - %(message)s",
    "%Y-%m-%dT%H:%M:%S%z",
)
_CONSOLE_FMT = logging.Formatter("%(message)s")


def setup_logging(*, verbose: bool = False, quiet: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(_CONSOLE_FMT)
    logger.addHandler(console)
    logger.propagate = False
    return logger


def add_collection_log(log_path: Path) -> logging.Handler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path)
    handler.setLevel(logging.INFO)
    handler.setFormatter(_FILE_FMT)
    logging.getLogger(LOGGER_NAME).addHandler(handler)
    return handler


def remove_handler(handler: logging.Handler) -> None:
    logging.getLogger(LOGGER_NAME).removeHandler(handler)
    handler.close()


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
