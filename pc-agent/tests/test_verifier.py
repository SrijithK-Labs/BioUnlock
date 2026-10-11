"""Tests for independent envelope verification."""

from __future__ import annotations

import pytest
from support import build_envelope, memory_replay_store

from biounlock_agent.errors import EnvelopeVerificationError
from biounlock_agent.verifier import VerifiedEnvelope, verify_envelope

NOW = 1500


def _verify(envelope, server_pub_pem, server_fingerprint, **kwargs):
    return verify_envelope(
        envelope,
        pinned_public_key_pem=server_pub_pem,
        pinned_fingerprint=server_fingerprint,
        device_id="pc-1",
        now=NOW,
        **kwargs,
    )


def test_accepts_valid_envelope(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key)
    result = _verify(envelope, server_pub_pem, server_fingerprint)
    assert isinstance(result, VerifiedEnvelope)
    assert result.request_id == "req-1"
    assert result.pc_id == "pc-1"
    assert result.operation == "remote_unlock"


def test_accepts_remote_lock_operation(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key, operation="remote_lock")
    result = _verify(envelope, server_pub_pem, server_fingerprint)
    assert result.operation == "remote_lock"


def test_rejects_tampered_signature(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key, signature="AAAA")
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "bad_signature"


def test_rejects_unknown_key_fingerprint(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key, key_id="different-fingerprint")
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "key_mismatch"


def test_rejects_envelope_for_another_pc(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key, pc_id="other-pc")
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "pc_mismatch"


def test_rejects_expired_envelope(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key, expires_at=NOW - 100)
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "expired"


def test_rejects_future_envelope(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key, issued_at=NOW + 100, expires_at=NOW + 200)
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "not_yet_valid"


def test_rejects_unsupported_operation(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key, operation="format_disk")
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "unsupported_operation"


def test_rejects_replayed_envelope(server_key, server_pub_pem, server_fingerprint):
    store = memory_replay_store()
    envelope = build_envelope(server_key)
    _verify(envelope, server_pub_pem, server_fingerprint, replay_store=store)
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint, replay_store=store)
    assert exc.value.reason_code == "replayed"


def test_rejects_reused_nonce_under_new_request_id(server_key, server_pub_pem, server_fingerprint):
    store = memory_replay_store()
    first = build_envelope(server_key, request_id="req-1", nonce="shared")
    _verify(first, server_pub_pem, server_fingerprint, replay_store=store)
    second = build_envelope(server_key, request_id="req-2", nonce="shared")
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(second, server_pub_pem, server_fingerprint, replay_store=store)
    assert exc.value.reason_code == "replayed"


@pytest.mark.parametrize("bad", [None, "not-a-dict", 42, []])
def test_rejects_non_object_envelopes(bad, server_pub_pem, server_fingerprint):
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(bad, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "malformed"


def test_rejects_missing_field(server_key, server_pub_pem, server_fingerprint):
    envelope = build_envelope(server_key)
    del envelope["nonce"]
    with pytest.raises(EnvelopeVerificationError) as exc:
        _verify(envelope, server_pub_pem, server_fingerprint)
    assert exc.value.reason_code == "malformed"
