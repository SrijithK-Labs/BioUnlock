from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuthRequest, utcnow
from tests.conftest import (
    auth_header,
    create_auth_request,
    enroll_and_pair,
    register_account,
    register_passkey,
)
from tests.support.helpers import b64url_decode, device_auth_header


def _setup(client: TestClient):
    token = register_account(client)
    authenticator = register_passkey(client, token)
    device_id, key, fp = enroll_and_pair(client, token)
    return token, authenticator, device_id, key, fp


def test_full_flow_pending_then_verified(client: TestClient) -> None:
    token, authenticator, device_id, key, fp = _setup(client)

    created = create_auth_request(client, token, device_id, authenticator)
    assert created.status_code == 201
    request_id = created.json()["id"]

    status = client.get(f"/api/v1/requests/{request_id}", headers=auth_header(token)).json()
    assert status["status"] == "pending"

    ack = client.post(
        f"/api/v1/requests/{request_id}/ack",
        json={"status": "verified"},
        headers=device_auth_header(key, fp, device_id),
    )
    assert ack.status_code == 200, ack.text

    status = client.get(f"/api/v1/requests/{request_id}", headers=auth_header(token)).json()
    assert status["status"] == "verified"


def test_rejected_flow(client: TestClient) -> None:
    token, authenticator, device_id, key, fp = _setup(client)
    request_id = create_auth_request(client, token, device_id, authenticator).json()["id"]
    ack = client.post(
        f"/api/v1/requests/{request_id}/ack",
        json={"status": "rejected", "reason_code": "user_declined_on_pc"},
        headers=device_auth_header(key, fp, device_id),
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "rejected"


def test_ack_idempotent_same_status(client: TestClient) -> None:
    token, authenticator, device_id, key, fp = _setup(client)
    request_id = create_auth_request(client, token, device_id, authenticator).json()["id"]
    header = device_auth_header(key, fp, device_id)
    first = client.post(f"/api/v1/requests/{request_id}/ack", json={"status": "verified"}, headers=header)
    second = client.post(f"/api/v1/requests/{request_id}/ack", json={"status": "verified"}, headers=header)
    assert first.status_code == 200
    assert second.status_code == 200


def test_ack_conflicting_status(client: TestClient) -> None:
    token, authenticator, device_id, key, fp = _setup(client)
    request_id = create_auth_request(client, token, device_id, authenticator).json()["id"]
    header = device_auth_header(key, fp, device_id)
    client.post(f"/api/v1/requests/{request_id}/ack", json={"status": "verified"}, headers=header)
    conflict = client.post(f"/api/v1/requests/{request_id}/ack", json={"status": "rejected"}, headers=header)
    assert conflict.status_code == 409


def test_ack_from_wrong_device(client: TestClient) -> None:
    token, authenticator, device_id, _key, _fp = _setup(client)
    request_id = create_auth_request(client, token, device_id, authenticator).json()["id"]
    other_id, other_key, other_fp = enroll_and_pair(client, token, name="Other PC")
    response = client.post(
        f"/api/v1/requests/{request_id}/ack",
        json={"status": "verified"},
        headers=device_auth_header(other_key, other_fp, other_id),
    )
    assert response.status_code == 404


def test_request_lazily_expires(client: TestClient, app) -> None:
    token, authenticator, device_id, key, fp = _setup(client)
    request_id = create_auth_request(client, token, device_id, authenticator).json()["id"]
    session = app.state.session_factory()
    req = session.execute(select(AuthRequest).where(AuthRequest.id == request_id)).scalar_one()
    req.expires_at = utcnow() - timedelta(seconds=1)
    session.commit()
    session.close()

    status = client.get(f"/api/v1/requests/{request_id}", headers=auth_header(token)).json()
    assert status["status"] == "expired"

    ack = client.post(
        f"/api/v1/requests/{request_id}/ack",
        json={"status": "verified"},
        headers=device_auth_header(key, fp, device_id),
    )
    assert ack.status_code == 409


def test_replayed_challenge_rejected(client: TestClient) -> None:
    token, authenticator, device_id, _key, _fp = _setup(client)
    begin = client.post("/api/v1/auth/challenges", json={"pc_id": device_id}, headers=auth_header(token)).json()
    challenge = b64url_decode(begin["options"]["challenge"])
    assertion = authenticator.get_assertion(challenge)
    payload = {"challenge_id": begin["challenge_id"], "pc_id": device_id, "assertion": assertion}
    first = client.post("/api/v1/auth/requests", json=payload, headers=auth_header(token))
    assert first.status_code == 201
    second = client.post("/api/v1/auth/requests", json=payload, headers=auth_header(token))
    assert second.status_code == 409


def test_cross_user_request_access(client: TestClient) -> None:
    token_a, authenticator, device_id, _key, _fp = _setup(client)
    token_b = register_account(client, email="b@example.com")
    request_id = create_auth_request(client, token_a, device_id, authenticator).json()["id"]
    assert client.get(f"/api/v1/requests/{request_id}", headers=auth_header(token_b)).status_code == 404


def test_list_requests(client: TestClient) -> None:
    token, authenticator, device_id, _key, _fp = _setup(client)
    create_auth_request(client, token, device_id, authenticator)
    listing = client.get("/api/v1/requests", headers=auth_header(token)).json()
    assert len(listing) == 1
    assert listing[0]["pc_name"] == "Test PC"
