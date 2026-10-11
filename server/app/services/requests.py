"""Authorization request envelope building and helpers."""

from __future__ import annotations

from app.core.security import ServerSigningKey, envelope_message
from app.core.time import as_utc, to_epoch
from app.models import AuthRequest

__all__ = ["as_utc", "to_epoch", "build_envelope", "status_value"]


def build_envelope(server_key: ServerSigningKey, request: AuthRequest) -> dict:
    """Build a signed authorization envelope for a PC agent.

    The signature covers every field, so the agent can independently verify
    integrity and binding to account/PC/operation/expiry/nonce.
    """
    issued_at = to_epoch(request.created_at)
    expires_at = to_epoch(request.expires_at)
    message = envelope_message(
        request.id,
        request.account_id,
        request.pc_id,
        request.operation,
        issued_at,
        expires_at,
        request.nonce,
    )
    return {
        "request_id": request.id,
        "account_id": request.account_id,
        "pc_id": request.pc_id,
        "operation": request.operation,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": request.nonce,
        "signature": server_key.sign(message),
        "server_signing_key_id": server_key.fingerprint(),
    }


def status_value(request: AuthRequest) -> str:
    status = request.status
    return status.value if hasattr(status, "value") else str(status)
