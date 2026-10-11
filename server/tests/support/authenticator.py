"""A minimal software WebAuthn authenticator for tests.

It builds standards-compliant client data, authenticator data, COSE keys and
attestation objects, then signs assertions with a real Ed25519 key. This lets
the test suite exercise the server's real WebAuthn verification path without a
physical device.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04
FLAG_ATTESTED_CREDENTIAL_DATA = 0x40


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class SoftAuthenticator:
    def __init__(self, rp_id: str, origin: str) -> None:
        self.rp_id = rp_id
        self.origin = origin
        self.private_key = Ed25519PrivateKey.generate()
        self.credential_id = secrets.token_bytes(32)
        self.aaguid = b"\x00" * 16
        self.sign_count = 0

    def _rp_id_hash(self) -> bytes:
        return hashlib.sha256(self.rp_id.encode("utf-8")).digest()

    def _cose_public_key(self) -> bytes:
        raw = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        # COSE OKP key: {1:1 (kty), 3:-8 (EdDSA), -1:6 (Ed25519), -2: pubkey}
        return cbor2.dumps({1: 1, 3: -8, -1: 6, -2: raw})

    def _client_data(self, ctype: str, challenge: bytes) -> bytes:
        return json.dumps(
            {
                "type": ctype,
                "challenge": b64url(challenge),
                "origin": self.origin,
                "crossOrigin": False,
            }
        ).encode("utf-8")

    def make_credential(self, challenge: bytes) -> dict:
        client_data = self._client_data("webauthn.create", challenge)
        auth_data = (
            self._rp_id_hash()
            + bytes([FLAG_USER_PRESENT | FLAG_USER_VERIFIED | FLAG_ATTESTED_CREDENTIAL_DATA])
            + (0).to_bytes(4, "big")
            + self.aaguid
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self._cose_public_key()
        )
        attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation_object),
                "transports": ["internal"],
            },
        }

    def get_assertion(self, challenge: bytes, *, user_verified: bool = True) -> dict:
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", challenge)
        flags = FLAG_USER_PRESENT | (FLAG_USER_VERIFIED if user_verified else 0)
        auth_data = self._rp_id_hash() + bytes([flags]) + self.sign_count.to_bytes(4, "big")
        signature = self.private_key.sign(auth_data + hashlib.sha256(client_data).digest())
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": None,
            },
        }
