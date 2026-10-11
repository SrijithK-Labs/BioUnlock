"""Tests for the backend HTTP client using httpx's mock transport."""

from __future__ import annotations

import json

import httpx
import pytest

from biounlock_agent.api_client import ApiClient
from biounlock_agent.crypto import device_auth_message, verify_b64
from biounlock_agent.errors import ApiError, NotEnrolledError


def _client(handler, **kwargs) -> ApiClient:
    return ApiClient("http://testserver", transport=httpx.MockTransport(handler), **kwargs)


def test_server_info_parses_response():
    def handler(request):
        assert request.url.path == "/api/v1/server/info"
        return httpx.Response(
            200,
            json={
                "name": "BioUnlock",
                "version": "0.1.0",
                "rp_id": "example.com",
                "server_signing_key_fingerprint": "FP",
                "environment": "production",
            },
        )

    info = _client(handler).server_info()
    assert info.server_signing_key_fingerprint == "FP"
    assert info.rp_id == "example.com"


def test_enroll_sends_public_key(device_identity):
    captured: dict = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "device_id": "device-1",
                "device_name": "PC",
                "pairing_code": "ABCD-1234",
                "qr_payload": "{}",
                "expires_at": "2030-01-01T00:00:00Z",
                "server_signing_public_key": "PEM",
                "server_signing_key_fingerprint": "FP",
            },
        )

    client = _client(handler, private_key=device_identity)
    enrollment = client.enroll(name="PC")

    assert captured["path"] == "/api/v1/devices/enroll"
    assert "BEGIN PUBLIC KEY" in captured["body"]["public_key"]
    assert enrollment.pairing_code == "ABCD-1234"


def test_heartbeat_uses_signed_device_credential(device_identity):
    captured: dict = {}

    def handler(request):
        captured["auth"] = request.headers["authorization"]
        return httpx.Response(
            200,
            json={
                "server_time": "2026-01-01T00:00:00Z",
                "heartbeat_interval_seconds": 60,
                "paired": True,
                "pending_requests": 0,
            },
        )

    client = _client(handler, private_key=device_identity, device_id="device-1", server_fingerprint="FP")
    heartbeat = client.heartbeat()

    assert heartbeat.paired is True
    scheme, credential = captured["auth"].split(" ", 1)
    assert scheme == "Biounlock"
    device_id, expiry, signature = credential.split(".", 2)
    assert device_id == "device-1"
    assert verify_b64(
        device_identity.public_key(),
        device_auth_message("FP", "device-1", int(expiry)),
        signature,
    )


def test_inbox_returns_envelopes(device_identity):
    def handler(request):
        assert request.url.path == "/api/v1/devices/me/inbox"
        return httpx.Response(200, json={"requests": [{"request_id": "r1"}]})

    client = _client(handler, private_key=device_identity, device_id="device-1", server_fingerprint="FP")
    assert client.inbox() == [{"request_id": "r1"}]


def test_ack_posts_status_and_reason(device_identity):
    captured: dict = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"request_id": "r1", "status": "verified", "acknowledged_at": "t"})

    client = _client(handler, private_key=device_identity, device_id="device-1", server_fingerprint="FP")
    client.ack("r1", status="rejected", reason_code="expired", observed_at=123)

    assert captured["path"] == "/api/v1/requests/r1/ack"
    assert captured["body"] == {"status": "rejected", "reason_code": "expired", "observed_at": 123}


def test_api_error_is_parsed():
    def handler(request):
        return httpx.Response(400, json={"error": {"code": "bad_request", "message": "nope"}})

    with pytest.raises(ApiError) as exc:
        _client(handler).server_info()
    assert exc.value.code == "bad_request"
    assert exc.value.status_code == 400
    assert "nope" in str(exc.value)


def test_network_error_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ApiError) as exc:
        _client(handler).server_info()
    assert exc.value.code == "network_error"


def test_device_calls_require_enrollment():
    def handler(request):  # pragma: no cover - must not be reached
        raise AssertionError("no request should be sent")

    client = _client(handler)
    with pytest.raises(NotEnrolledError):
        client.heartbeat()
