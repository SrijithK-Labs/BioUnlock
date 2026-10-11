"""Persistent replay protection for processed authorization envelopes.

Every accepted or rejected envelope's ``request_id`` and ``nonce`` are recorded
so a replayed envelope can never be processed twice, even across restarts.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed (
    request_id TEXT PRIMARY KEY,
    nonce TEXT NOT NULL,
    processed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processed_nonce ON processed(nonce);
CREATE INDEX IF NOT EXISTS idx_processed_at ON processed(processed_at);
"""

DEFAULT_RETENTION_SECONDS = 7 * 24 * 3600


class ReplayStore:
    """SQLite-backed dedupe of processed request ids and nonces."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._lock = threading.Lock()
        if connection is not None:
            self._conn = connection
        elif path is not None:
            self._conn = sqlite3.connect(str(path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
        else:
            raise ValueError("ReplayStore requires a path or an existing connection")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def seen(self, request_id: str, nonce: str) -> bool:
        """Return True if this request id or nonce was already processed."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM processed WHERE request_id = ? OR nonce = ? LIMIT 1",
                (request_id, nonce),
            ).fetchone()
            return row is not None

    def record(self, request_id: str, nonce: str, *, now: int | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO processed(request_id, nonce, processed_at) VALUES (?, ?, ?)",
                (request_id, nonce, int(now if now is not None else time.time())),
            )
            self._conn.commit()

    def check_and_record(self, request_id: str, nonce: str, *, now: int | None = None) -> bool:
        """Atomically test-and-set. Returns True if newly recorded, False if seen."""
        timestamp = int(now if now is not None else time.time())
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM processed WHERE request_id = ? OR nonce = ? LIMIT 1",
                (request_id, nonce),
            ).fetchone()
            if row is not None:
                return False
            self._conn.execute(
                "INSERT OR IGNORE INTO processed(request_id, nonce, processed_at) VALUES (?, ?, ?)",
                (request_id, nonce, timestamp),
            )
            self._conn.commit()
            return True

    def prune(self, *, older_than_seconds: int = DEFAULT_RETENTION_SECONDS, now: int | None = None) -> int:
        cutoff = int(now if now is not None else time.time()) - older_than_seconds
        with self._lock:
            cursor = self._conn.execute("DELETE FROM processed WHERE processed_at < ?", (cutoff,))
            self._conn.commit()
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
