from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import PairingCode, utcnow
from tests.conftest import enroll_device


def test_enroll_returns_pairing_material(client: TestClient) -> None:
    data = enroll_device(client)
    assert data["device_id"]
    assert len(data["pairing_code"]) >= 16
    assert data["server_signing_key_fingerprint"]
    assert "BEGIN PUBLIC KEY" in data["server_signing_public_key"]


def test_confirm_pairing_success(client: TestClient) -> None:
    data = enroll_device(client)
    response = client.post(
        "/api/v1/pairing/confirm",
        json={"pairing_code": data["pairing_code"]},
    )
    assert response.status_code == 200
    assert response.json()["device"]["status"] == "active"


def test_pairing_code_single_use(client: TestClient) -> None:
    data = enroll_device(client)
    first = client.post("/api/v1/pairing/confirm", json={"pairing_code": data["pairing_code"]})
    assert first.status_code == 200
    second = client.post("/api/v1/pairing/confirm", json={"pairing_code": data["pairing_code"]})
    assert second.status_code == 400


def test_pairing_unknown_code(client: TestClient) -> None:
    response = client.post("/api/v1/pairing/confirm", json={"pairing_code": "AAAAAAAAAAAAAAAAAAAAAAAA"})
    assert response.status_code == 400


def test_pairing_expired_code(client: TestClient, app) -> None:
    data = enroll_device(client)
    factory = app.state.session_factory
    session = factory()
    pairing = session.execute(select(PairingCode).where(PairingCode.device_id == data["device_id"])).scalars().first()
    pairing.expires_at = utcnow() - timedelta(seconds=5)
    session.commit()
    session.close()
    response = client.post("/api/v1/pairing/confirm", json={"pairing_code": data["pairing_code"]})
    assert response.status_code == 400


def test_pairing_attempt_limit(client: TestClient) -> None:
    data = enroll_device(client)
    code = data["pairing_code"]
    # Same prefix, wrong final character to target the correct record.
    wrong = code[:-1] + ("B" if code[-1] != "B" else "C")
    for _ in range(5):
        client.post("/api/v1/pairing/confirm", json={"pairing_code": wrong})
    response = client.post("/api/v1/pairing/confirm", json={"pairing_code": code})
    assert response.status_code == 400
