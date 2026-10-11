"""Time helpers.

Stored timestamps may come back naive (SQLite) or aware (PostgreSQL). Always
normalize to aware UTC before comparing.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_epoch(dt: datetime) -> int:
    return int(as_utc(dt).timestamp())
