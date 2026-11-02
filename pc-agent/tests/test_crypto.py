"""Tests for the crypto wire formats shared with the backend."""

from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives import serialization

from biounlock_agent import crypto


def test_device_auth_message_matches_server_format():
    message = crypto.device_auth_message("FP", "dev", 123)
    assert message == b"biounlock-device-auth-v1|FP|dev|123"


def test_envelope_message_matches_server_format():
    message = crypto.envelope_message("r", "a", "p", "remote_unlock", 1, 2, "n")
    assert message == b"biounlock-envelope-v1|r|a|p|remote_unlock|1|2|n"


def test_make_device_auth_header_is_signed_and_parsable(device_identity):
    header = crypto.make_device_auth_header(
        device_identity, device_id="dev", server_fingerprint="FP", expiry=123
    )
    scheme, credential = header.split(" ", 1)
    assert scheme == "Biounlock"
    device_id, expiry, signature = credential.split(".", 2)
    assert (device_id, expiry) == ("dev", "123")
    assert crypto.verify_b64(
        device_identity.public_key(),
        crypto.device_auth_message("FP", "dev", 123),
        signature,
    )


def test_public_key_fingerprint_is_sha256_of_raw_key(server_key, server_fingerprint):
    raw = server_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    assert server_fingerprint == hashlib.sha256(raw).hexdigest()


def test_b64url_roundtrip_with_and_without_padding():
    data = bytes(range(64))
    encoded = crypto.b64url_encode(data)
    assert crypto.b64url_decode(encoded) == data
    assert crypto.b64url_decode(encoded.rstrip("=")) == data


def test_verify_b64_rejects_tampered_message(server_key):
    public = server_key.public_key()
    signature = crypto.sign_b64(server_key, b"hello")
    assert crypto.verify_b64(public, b"hello", signature)
    assert not crypto.verify_b64(public, b"hell0", signature)
