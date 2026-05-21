"""Centralized logging — file handler always, stderr only on --verbose."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path.home() / ".voice-realtime" / "logs"


def setup_logging(provider: str, verbose: bool = False) -> Path:
    """Configure root logger: always log debug to file, optionally to stderr.

    Returns the log file path.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"{ts}_{provider}.log"

    # Clean up any handlers from a previous session in the same process
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if verbose:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)

    return log_path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
