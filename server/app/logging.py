"""Structured logging (JSON lines) that never includes secrets."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id") and record.request_id:
            payload["request_id"] = record.request_id
        return json.dumps(payload, default=str)


def sanitize_url(url: str | None) -> str:
    """Return a URL safe for logs, stripping any query string / fragment."""
    if not url:
        return ""
    return url.split("?")[0].split("#")[0]


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel("WARNING")
