"""Shared test helpers for building device credentials and requests."""

from __future__ import annotations

import base64
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.security import device_auth_message, serialize_public_key_pem


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def new_device_keypair() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    return private_key, serialize_public_key_pem(private_key.public_key())


def sign_device_auth(private_key: Ed25519PrivateKey, fingerprint: str, device_id: str, expiry: int) -> str:
    message = device_auth_message(fingerprint, device_id, expiry)
    signature = private_key.sign(message)
    return base64.urlsafe_b64encode(signature).decode("ascii")


def device_auth_header(
    private_key: Ed25519PrivateKey,
    fingerprint: str,
    device_id: str,
    *,
    expiry_offset: int = 300,
    expired: bool = False,
) -> dict[str, str]:
    expiry = int(time.time()) + (-expiry_offset if expired else expiry_offset)
    signature = sign_device_auth(private_key, fingerprint, device_id, expiry)
    return {"Authorization": f"Biounlock {device_id}.{expiry}.{signature}"}
