"""Independent verification of server-signed authorization envelopes.

The agent never trusts an envelope merely because it arrived from the backend.
It re-checks the signature against the pinned server key and validates every
binding (PC, operation, freshness, replay) before acknowledging anything.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from biounlock_agent.crypto import (
    envelope_message,
    load_public_key_pem,
    public_key_fingerprint,
    verify_b64,
)
from biounlock_agent.errors import EnvelopeVerificationError
from biounlock_agent.replay import ReplayStore

ALLOWED_OPERATIONS = frozenset({"remote_unlock", "remote_lock"})
DEFAULT_CLOCK_SKEW_SECONDS = 30


@dataclass(frozen=True)
class VerifiedEnvelope:
    request_id: str
    account_id: str
    pc_id: str
    operation: str
    issued_at: int
    expires_at: int
    nonce: str


def _require_str(envelope: dict, key: str) -> str:
    value = envelope.get(key)
    if not isinstance(value, str) or not value:
        raise EnvelopeVerificationError("malformed", f"field '{key}' is missing or invalid")
    return value


def _require_int(envelope: dict, key: str) -> int:
    value = envelope.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EnvelopeVerificationError("malformed", f"field '{key}' is missing or invalid")
    return value


def verify_envelope(
    envelope: object,
    *,
    pinned_public_key_pem: str,
    pinned_fingerprint: str,
    device_id: str,
    now: int | None = None,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    replay_store: ReplayStore | None = None,
    allowed_operations: frozenset[str] = ALLOWED_OPERATIONS,
) -> VerifiedEnvelope:
    """Verify an envelope and return its validated fields.

    Raises :class:`EnvelopeVerificationError` with a short ``reason_code`` on any
    failure. A ``replay_store``, when given, atomically records the request so a
    duplicate is rejected with reason ``replayed``.
    """
    if not isinstance(envelope, dict):
        raise EnvelopeVerificationError("malformed", "envelope is not a JSON object")

    request_id = _require_str(envelope, "request_id")
    account_id = _require_str(envelope, "account_id")
    pc_id = _require_str(envelope, "pc_id")
    operation = _require_str(envelope, "operation")
    nonce = _require_str(envelope, "nonce")
    issued_at = _require_int(envelope, "issued_at")
    expires_at = _require_int(envelope, "expires_at")
    signature = _require_str(envelope, "signature")
    key_id = envelope.get("server_signing_key_id")
    if not isinstance(key_id, str) or not key_id:
        raise EnvelopeVerificationError("malformed", "field 'server_signing_key_id' is missing")

    # 1. The envelope must claim the exact pinned server identity.
    if key_id != pinned_fingerprint:
        raise EnvelopeVerificationError("key_mismatch", "envelope signed by an unknown key")

    try:
        public_key = load_public_key_pem(pinned_public_key_pem)
    except Exception as exc:  # noqa: BLE001
        raise EnvelopeVerificationError("key_mismatch", "pinned server key is unusable") from exc
    if public_key_fingerprint(public_key) != pinned_fingerprint:
        raise EnvelopeVerificationError("key_mismatch", "pinned key does not match its fingerprint")

    # 2. Signature over the exact message.
    message = envelope_message(
        request_id, account_id, pc_id, operation, issued_at, expires_at, nonce
    )
    if not verify_b64(public_key, message, signature):
        raise EnvelopeVerificationError("bad_signature", "signature verification failed")

    # 3. The envelope must target this PC (checked before operation/time/replay
    #    so a rejection we report is always authentically about this PC).
    if pc_id != device_id:
        raise EnvelopeVerificationError("pc_mismatch", "envelope targets another PC")

    # 4. Only the single registered operation is accepted.
    if operation not in allowed_operations:
        raise EnvelopeVerificationError("unsupported_operation", f"operation '{operation}' is not allowed")

    # 5. Freshness.
    current = int(now if now is not None else time.time())
    if expires_at <= current - clock_skew_seconds:
        raise EnvelopeVerificationError("expired", "envelope has expired")
    if issued_at > current + clock_skew_seconds:
        raise EnvelopeVerificationError("not_yet_valid", "envelope was issued in the future")

    # 6. Replay protection.
    if replay_store is not None and not replay_store.check_and_record(request_id, nonce, now=current):
        raise EnvelopeVerificationError("replayed", "envelope was already processed")

    return VerifiedEnvelope(
        request_id=request_id,
        account_id=account_id,
        pc_id=pc_id,
        operation=operation,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
