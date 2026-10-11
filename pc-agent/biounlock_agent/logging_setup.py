"""Logging configuration for the BioUnlock agent.

Logs never contain secrets; callers must sanitize URLs and avoid key material.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO", log_file: str | Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format=DEFAULT_FORMAT,
        handlers=handlers,
        force=True,
    )
