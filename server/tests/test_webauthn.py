from fastapi.testclient import TestClient

from tests.conftest import (
    TEST_ORIGIN,
    auth_header,
    create_auth_request,
    enroll_and_pair,
    register_account,
    register_passkey,
)
from tests.support.authenticator import SoftAuthenticator
from tests.support.helpers import b64url_decode


def test_register_passkey_and_list(client: TestClient) -> None:
    token = register_account(client)
    register_passkey(client, token)
    credentials = client.get("/api/v1/webauthn/credentials", headers=auth_header(token)).json()
    assert len(credentials) == 1
    assert credentials[0]["name"] == "Test passkey"


def test_delete_passkey(client: TestClient) -> None:
    token = register_account(client)
    register_passkey(client, token)
    credential_id = client.get("/api/v1/webauthn/credentials", headers=auth_header(token)).json()[0]["id"]
    assert client.delete(f"/api/v1/webauthn/credentials/{credential_id}", headers=auth_header(token)).status_code == 200
    assert client.get("/api/v1/webauthn/credentials", headers=auth_header(token)).json() == []


def test_register_passkey_unknown_challenge(client: TestClient) -> None:
    token = register_account(client)
    authenticator = SoftAuthenticator("localhost", TEST_ORIGIN)
    credential = authenticator.make_credential(b"0" * 32)
    response = client.post(
        "/api/v1/webauthn/register/complete",
        json={"challenge_id": "does-not-exist", "credential": credential},
        headers=auth_header(token),
    )
    assert response.status_code == 400


def test_register_passkey_rejects_foreign_origin(client: TestClient) -> None:
    token = register_account(client)
    begin = client.post("/api/v1/webauthn/register/begin", headers=auth_header(token)).json()
    authenticator = SoftAuthenticator("localhost", "https://evil.example.com")
    credential = authenticator.make_credential(b64url_decode(begin["options"]["challenge"]))
    response = client.post(
        "/api/v1/webauthn/register/complete",
        json={"challenge_id": begin["challenge_id"], "credential": credential},
        headers=auth_header(token),
    )
    assert response.status_code == 400


def test_challenge_requires_passkey(client: TestClient) -> None:
    token = register_account(client)
    device_id, _key, _fp = enroll_and_pair(client, token)
    response = client.post("/api/v1/auth/challenges", json={"pc_id": device_id}, headers=auth_header(token))
    assert response.status_code == 409


def test_end_to_end_authorization_request(client: TestClient) -> None:
    token = register_account(client)
    authenticator = register_passkey(client, token)
    device_id, _key, _fp = enroll_and_pair(client, token)
    response = create_auth_request(client, token, device_id, authenticator)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["operation"] == "remote_unlock"


def test_end_to_end_lock_request(client: TestClient) -> None:
    token = register_account(client)
    authenticator = register_passkey(client, token)
    device_id, _key, _fp = enroll_and_pair(client, token)
    response = create_auth_request(client, token, device_id, authenticator, operation="remote_lock")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["operation"] == "remote_lock"


def test_rejects_unknown_operation(client: TestClient) -> None:
    token = register_account(client)
    authenticator = register_passkey(client, token)
    device_id, _key, _fp = enroll_and_pair(client, token)
    response = create_auth_request(client, token, device_id, authenticator, operation="format_disk")
    assert response.status_code == 422


def test_authorization_tampered_signature(client: TestClient) -> None:
    token = register_account(client)
    authenticator = register_passkey(client, token)
    device_id, _key, _fp = enroll_and_pair(client, token)
    begin = client.post("/api/v1/auth/challenges", json={"pc_id": device_id}, headers=auth_header(token)).json()
    assertion = authenticator.get_assertion(b64url_decode(begin["options"]["challenge"]))
    # Corrupt the signature.
    sig = assertion["response"]["signature"]
    assertion["response"]["signature"] = ("A" if sig[0] != "A" else "B") + sig[1:]
    response = client.post(
        "/api/v1/auth/requests",
        json={"challenge_id": begin["challenge_id"], "pc_id": device_id, "assertion": assertion},
        headers=auth_header(token),
    )
    assert response.status_code == 400
