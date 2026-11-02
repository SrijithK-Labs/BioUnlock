"""Cryptographic primitives for the BioUnlock PC agent.

The agent owns a device Ed25519 keypair and pins the server's Ed25519 signing
key. Message formats match the backend exactly (see ``docs/protocol.md`` and
``server/app/core/security.py``) so that signatures verify on both sides.

Never invent algorithms; never log key material.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

DEVICE_AUTH_LABEL = "biounlock-device-auth-v1"
ENVELOPE_LABEL = "biounlock-envelope-v1"


def generate_identity() -> Ed25519PrivateKey:
    """Generate a fresh Ed25519 device private key."""
    return ed25519.Ed25519PrivateKey.generate()


def private_key_to_pem(private_key: Ed25519PrivateKey) -> bytes:
    """Serialize a private key as an unencrypted PKCS#8 PEM (protect at rest)."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def private_key_from_pem(data: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("device key is not Ed25519")
    return key


def public_key_pem(key: Ed25519PrivateKey | Ed25519PublicKey) -> str:
    """Return the SubjectPublicKeyInfo PEM for a private or public key."""
    public = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def load_public_key_pem(pem: str | bytes) -> Ed25519PublicKey:
    raw = pem.encode("utf-8") if isinstance(pem, str) else pem
    key = serialization.load_pem_public_key(raw)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("public key is not Ed25519")
    return key


def public_key_fingerprint(key: Ed25519PrivateKey | Ed25519PublicKey) -> str:
    """Hex SHA-256 of the raw public key bytes (matches the server)."""
    public = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def b64url_encode(data: bytes) -> str:
    """URL-safe base64 with padding, matching the server's signer."""
    return base64.urlsafe_b64encode(data).decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Decode URL-safe base64, tolerating missing padding."""
    return base64.urlsafe_b64decode(text.encode("ascii") + b"=" * (-len(text) % 4))


def sign_b64(private_key: Ed25519PrivateKey, message: bytes) -> str:
    return b64url_encode(private_key.sign(message))


def verify_b64(public_key: Ed25519PublicKey, message: bytes, signature_b64: str) -> bool:
    try:
        public_key.verify(b64url_decode(signature_b64), message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def device_auth_message(server_fingerprint: str, device_id: str, expiry: int) -> bytes:
    return f"{DEVICE_AUTH_LABEL}|{server_fingerprint}|{device_id}|{expiry}".encode()


def envelope_message(
    request_id: str,
    account_id: str,
    pc_id: str,
    operation: str,
    issued_at: int,
    expires_at: int,
    nonce: str,
) -> bytes:
    return (
        f"{ENVELOPE_LABEL}|{request_id}|{account_id}|{pc_id}|{operation}"
        f"|{issued_at}|{expires_at}|{nonce}"
    ).encode()


def make_device_auth_header(
    private_key: Ed25519PrivateKey,
    *,
    device_id: str,
    server_fingerprint: str,
    expiry: int,
) -> str:
    """Build ``Biounlock <device_id>.<expiry>.<base64url-signature>``."""
    message = device_auth_message(server_fingerprint, device_id, expiry)
    signature = sign_b64(private_key, message)
    return f"Biounlock {device_id}.{expiry}.{signature}"
