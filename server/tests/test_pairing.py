from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Device, PairingCode, utcnow
from tests.conftest import auth_header, enroll_device, register_account


def test_enroll_returns_pairing_material(client: TestClient) -> None:
    data = enroll_device(client)
    assert data["device_id"]
    assert len(data["pairing_code"]) >= 16
    assert data["server_signing_key_fingerprint"]
    assert "BEGIN PUBLIC KEY" in data["server_signing_public_key"]


def test_confirm_pairing_success(client: TestClient) -> None:
    token = register_account(client)
    data = enroll_device(client)
    response = client.post(
        "/api/v1/pairing/confirm",
        json={"pairing_code": data["pairing_code"]},
        headers=auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["device"]["status"] == "active"


def test_pairing_code_single_use(client: TestClient) -> None:
    token = register_account(client)
    data = enroll_device(client)
    first = client.post("/api/v1/pairing/confirm", json={"pairing_code": data["pairing_code"]}, headers=auth_header(token))
    assert first.status_code == 200
    second = client.post("/api/v1/pairing/confirm", json={"pairing_code": data["pairing_code"]}, headers=auth_header(token))
    assert second.status_code == 400


def test_pairing_unknown_code(client: TestClient) -> None:
    token = register_account(client)
    response = client.post("/api/v1/pairing/confirm", json={"pairing_code": "AAAAAAAAAAAAAAAAAAAAAAAA"}, headers=auth_header(token))
    assert response.status_code == 400


def test_pairing_expired_code(client: TestClient, app) -> None:
    token = register_account(client)
    data = enroll_device(client)
    factory = app.state.session_factory
    session = factory()
    pairing = session.execute(select(PairingCode).where(PairingCode.device_id == data["device_id"])).scalars().first()
    pairing.expires_at = utcnow() - timedelta(seconds=5)
    session.commit()
    session.close()
    response = client.post("/api/v1/pairing/confirm", json={"pairing_code": data["pairing_code"]}, headers=auth_header(token))
    assert response.status_code == 400


def test_pairing_attempt_limit(client: TestClient) -> None:
    token = register_account(client)
    data = enroll_device(client)
    code = data["pairing_code"]
    # Same prefix, wrong final character to target the correct record.
    wrong = code[:-1] + ("B" if code[-1] != "B" else "C")
    for _ in range(5):
        client.post("/api/v1/pairing/confirm", json={"pairing_code": wrong}, headers=auth_header(token))
    response = client.post("/api/v1/pairing/confirm", json={"pairing_code": code}, headers=auth_header(token))
    assert response.status_code == 400


def test_pairing_conflicts_with_other_account(client: TestClient, app) -> None:
    register_account(client, email="a@example.com")
    token_b = register_account(client, email="b@example.com")
    data = enroll_device(client)
    factory = app.state.session_factory
    session = factory()
    device = session.get(Device, data["device_id"])
    from app.models import Account

    account_a = session.execute(select(Account).where(Account.email == "a@example.com")).scalar_one()
    device.account_id = account_a.id
    session.commit()
    session.close()
    # B holds the code but the device is claimed by A.
    response = client.post("/api/v1/pairing/confirm", json={"pairing_code": data["pairing_code"]}, headers=auth_header(token_b))
    assert response.status_code == 409
