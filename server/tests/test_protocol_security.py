from fastapi.testclient import TestClient

from app.core.security import envelope_message, verify_message_signature
from tests.conftest import (
    auth_header,
    create_auth_request,
    enroll_and_pair,
    register_account,
    register_passkey,
)
from tests.support.helpers import device_auth_header


def test_challenge_cross_user_device_rejected(client: TestClient) -> None:
    token_a = register_account(client, email="a@example.com")
    register_passkey(client, token_a)
    token_b = register_account(client, email="b@example.com")
    register_passkey(client, token_b)
    device_id_a, _key, _fp = enroll_and_pair(client, token_a)
    # B tries to create a challenge for A's device.
    response = client.post("/api/v1/auth/challenges", json={"pc_id": device_id_a}, headers=auth_header(token_b))
    assert response.status_code == 404


def test_authorization_request_cannot_target_foreign_device(client: TestClient) -> None:
    token_a = register_account(client, email="a@example.com")
    authenticator_a = register_passkey(client, token_a)
    token_b = register_account(client, email="b@example.com")
    register_passkey(client, token_b)
    device_id_a, _key, _fp = enroll_and_pair(client, token_a)

    begin = client.post("/api/v1/auth/challenges", json={"pc_id": device_id_a}, headers=auth_header(token_a)).json()
    from tests.support.helpers import b64url_decode

    assertion = authenticator_a.get_assertion(b64url_decode(begin["options"]["challenge"]))
    # B tries to complete A's challenge.
    response = client.post(
        "/api/v1/auth/requests",
        json={"challenge_id": begin["challenge_id"], "pc_id": device_id_a, "assertion": assertion},
        headers=auth_header(token_b),
    )
    assert response.status_code == 400


def test_envelope_signature_is_verifiable(client: TestClient, app) -> None:
    token = register_account(client)
    authenticator = register_passkey(client, token)
    device_id, _key, fp = enroll_and_pair(client, token)
    request_id = create_auth_request(client, token, device_id, authenticator).json()["id"]

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
    token = register_account(client)
    authenticator = register_passkey(client, token)
    device_id, key, fp = enroll_and_pair(client, token)
    request_id = create_auth_request(client, token, device_id, authenticator).json()["id"]

    inbox = client.get("/api/v1/devices/me/inbox", headers=device_auth_header(key, fp, device_id))
    assert inbox.status_code == 200
    envelopes = inbox.json()["requests"]
    assert len(envelopes) == 1
    assert envelopes[0]["request_id"] == request_id


def test_inbox_requires_active_device(client: TestClient) -> None:
    assert client.get("/api/v1/devices/me/inbox").status_code == 401
