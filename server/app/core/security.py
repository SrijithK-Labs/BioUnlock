"""Cryptographic primitives used by BioUnlock.

- Hashing: secrets are stored hashed (SHA-256).
- Server signing key: Ed25519 loaded from / generated into a protected file.
- Signatures are produced with the ``cryptography`` library.

Never invent algorithms. Never log key material.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ENVELOPE_LABEL = "biounlock-envelope-v1"
DEVICE_AUTH_LABEL = "biounlock-device-auth-v1"

# Env var holding the Ed25519 private key as PEM. Intended for hosts with an
# ephemeral filesystem (e.g. serverless) where the key file cannot persist; a
# stable key keeps agents trusting the same server identity across deploys.
SIGNING_KEY_ENV = "BIO_SIGNING_KEY"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)


class SigningKeyError(RuntimeError):
    pass


class ServerSigningKey:
    """Ed25519 server signing key with a stable public fingerprint.

    The key is stored as a PKCS#8 PEM file with POSIX-style 0600 permissions
    where the platform supports it. The file lives outside the DB so it can be
    moved to a secrets manager in production.
    """

    def __init__(
        self,
        signing_key_path: Path | None = None,
        load: bool = True,
        overwrite: bool = False,
        private_key: Ed25519PrivateKey | None = None,
    ) -> None:
        self._path = signing_key_path
        self._private_key = private_key
        if load and private_key is None:
            self._load_or_create(overwrite)

    @property
    def path(self) -> Path | None:
        return self._path

    @classmethod
    def generate(cls) -> ServerSigningKey:
        """Create a fresh in-memory key that is not persisted anywhere yet."""
        return cls(load=False, private_key=ed25519.Ed25519PrivateKey.generate())

    @classmethod
    def from_pem(cls, pem: str) -> ServerSigningKey:
        """Load a key from an Ed25519 PKCS#8 PEM string (no file access)."""
        return cls(load=False, private_key=cls._load_pem(pem))

    def to_pem(self) -> str:
        """Serialise the private key as an unencrypted PKCS#8 PEM string."""
        return self._require_key().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

    def _load_or_create(self, overwrite: bool) -> None:
        env_pem = os.environ.get(SIGNING_KEY_ENV)
        if env_pem and not overwrite:
            self._private_key = self._load_pem(env_pem)
            return
        if self._path is None:
            self._private_key = ed25519.Ed25519PrivateKey.generate()
            return
        if overwrite or not self._path.exists():
            self._create()
            return
        raw = self._path.read_bytes()
        self._private_key = serialization.load_pem_private_key(raw, password=None)

    @staticmethod
    def _load_pem(value: str) -> Ed25519PrivateKey:
        # Accept both real newlines and a single-line value where newlines are
        # written as literal ``\n`` (common for env vars in dashboards).
        candidates = [value]
        if "\\n" in value:
            candidates.append(value.replace("\\n", "\n"))
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                key = serialization.load_pem_private_key(
                    candidate.strip().encode("utf-8"), password=None
                )
            except (ValueError, TypeError) as exc:
                last_error = exc
                continue
            if not isinstance(key, Ed25519PrivateKey):
                raise SigningKeyError(f"{SIGNING_KEY_ENV} must be an Ed25519 private key")
            return key
        raise SigningKeyError(
            f"{SIGNING_KEY_ENV} is set but is not a valid PEM private key"
        ) from last_error

    def _create(self) -> None:
        self._private_key = ed25519.Ed25519PrivateKey.generate()
        pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(pem)
        try:
            self._path.chmod(0o600)
        except (NotImplementedError, OSError):
            pass  # Windows ignores chmod; ACLs should still restrict access.

    def _require_key(self) -> Ed25519PrivateKey:
        if self._private_key is None:
            self._create()
        assert self._private_key is not None
        return self._private_key

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._require_key().public_key()

    def public_key_pem(self) -> bytes:
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def fingerprint(self) -> str:
        pub = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(pub).hexdigest()

    def sign(self, message: bytes) -> str:
        import base64

        sig = self._require_key().sign(message)
        return base64.urlsafe_b64encode(sig).decode("ascii")


def load_public_key_from_pem(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode("utf-8"))
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("public key is not Ed25519")
    return key


def verify_message_signature(
    message: bytes, signature_b64: str, public_key_pem: str | bytes
) -> bool:
    """Verify an Ed25519 signature over ``message``."""
    import base64

    from cryptography.exceptions import InvalidSignature

    try:
        public_key = load_public_key_from_pem(public_key_pem.decode() if isinstance(public_key_pem, bytes) else public_key_pem)
        sig = base64.urlsafe_b64decode(signature_b64.encode("ascii") + b"=" * (-len(signature_b64) % 4))
        public_key.verify(sig, message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def generate_device_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def serialize_private_key_pem(private_key: Ed25519PrivateKey) -> str:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def serialize_public_key_pem(public_key: Ed25519PublicKey) -> str:
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def device_auth_message(server_fingerprint: str, device_id: str, expiry: int) -> bytes:
    return f"{DEVICE_AUTH_LABEL}|{server_fingerprint}|{device_id}|{expiry}".encode()


def envelope_message(request_id: str, account_id: str, pc_id: str, operation: str, issued_at: int, expires_at: int, nonce: str) -> bytes:
    return (
        f"{ENVELOPE_LABEL}|{request_id}|{account_id}|{pc_id}|{operation}"
        f"|{issued_at}|{expires_at}|{nonce}"
    ).encode()
