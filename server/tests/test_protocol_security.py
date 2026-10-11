from fastapi.testclient import TestClient

from app.core.security import envelope_message, verify_message_signature
from tests.conftest import (
    create_auth_request,
    enroll_and_pair,
    register_passkey,
)
from tests.support.helpers import device_auth_header


def test_envelope_signature_is_verifiable(client: TestClient, app) -> None:
    authenticator = register_passkey(client)
    device_id, _key, fp = enroll_and_pair(client)
    request_id = create_auth_request(client, device_id, authenticator).json()["id"]

    server_key = app.state.server_signing_key
    session = app.state.session_factory()
    from app.models import AuthRequest

    req = session.get(AuthRequest, request_id)
    from app.services.requests import build_envelope

    envelope = build_envelope(server_key, req)
    session.close()

    assert envelope["server_signing_key_id"] == fp
    message = envelope_message(
        envelope["request_id"],
        envelope["account_id"],
        envelope["pc_id"],
        envelope["operation"],
        envelope["issued_at"],
        envelope["expires_at"],
        envelope["nonce"],
    )
    assert verify_message_signature(message, envelope["signature"], server_key.public_key_pem())

    # Tampering with any field invalidates the signature.
    tampered = dict(envelope)
    tampered["operation"] = "something_else"
    bad_message = envelope_message(
        tampered["request_id"],
        tampered["account_id"],
        tampered["pc_id"],
        tampered["operation"],
        tampered["issued_at"],
        tampered["expires_at"],
        tampered["nonce"],
    )
    assert not verify_message_signature(bad_message, tampered["signature"], server_key.public_key_pem())


def test_inbox_delivers_envelope(client: TestClient) -> None:
    authenticator = register_passkey(client)
    device_id, key, fp = enroll_and_pair(client)
    request_id = create_auth_request(client, device_id, authenticator).json()["id"]

    inbox = client.get("/api/v1/devices/me/inbox", headers=device_auth_header(key, fp, device_id))
    assert inbox.status_code == 200
    envelopes = inbox.json()["requests"]
    assert len(envelopes) == 1
    assert envelopes[0]["request_id"] == request_id


def test_inbox_requires_active_device(client: TestClient) -> None:
    assert client.get("/api/v1/devices/me/inbox").status_code == 401
