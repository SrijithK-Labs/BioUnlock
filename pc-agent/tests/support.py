"""Shared test helpers for the BioUnlock PC agent test suite."""

from __future__ import annotations

import sqlite3
from typing import Any

from biounlock_agent.crypto import envelope_message, public_key_fingerprint, sign_b64
from biounlock_agent.replay import ReplayStore


def build_envelope(
    server_key,
    *,
    request_id: str = "req-1",
    account_id: str = "acct-1",
    pc_id: str = "pc-1",
    operation: str = "remote_unlock",
    issued_at: int = 1000,
    expires_at: int = 2000,
    nonce: str = "nonce-1",
    key_id: str | None = None,
    signature: str | None = None,
) -> dict[str, Any]:
    message = envelope_message(request_id, account_id, pc_id, operation, issued_at, expires_at, nonce)
    return {
        "request_id": request_id,
        "account_id": account_id,
        "pc_id": pc_id,
        "operation": operation,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
        "signature": signature if signature is not None else sign_b64(server_key, message),
        "server_signing_key_id": key_id if key_id is not None else public_key_fingerprint(server_key),
    }


def memory_replay_store() -> ReplayStore:
    return ReplayStore(connection=sqlite3.connect(":memory:", check_same_thread=False))
