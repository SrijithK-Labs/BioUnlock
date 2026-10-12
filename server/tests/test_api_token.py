from fastapi.testclient import TestClient

from app.config import Settings
from tests.conftest import enroll_and_pair, enroll_device, register_passkey

TOKEN = "test-api-token-1234"


def _auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_api_open_when_token_unset(client: TestClient) -> None:
    assert client.get("/api/v1/devices").status_code == 200
    assert client.get("/api/v1/webauthn/credentials").status_code == 200


def test_management_endpoints_require_token(client: TestClient, settings: Settings) -> None:
    settings.api_token = TOKEN
    for path in (
        "/api/v1/devices",
        "/api/v1/webauthn/credentials",
        "/api/v1/security-events",
        "/api/v1/requests",
    ):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=_auth("wrong")).status_code == 401
        assert client.get(path, headers=_auth()).status_code == 200


def test_registration_requires_token(client: TestClient, settings: Settings) -> None:
    settings.api_token = TOKEN
    assert client.post("/api/v1/webauthn/register/begin").status_code == 401
    with_token = client.post("/api/v1/webauthn/register/begin", headers=_auth())
    assert with_token.status_code == 200


def test_unlock_endpoints_require_token(client: TestClient, settings: Settings) -> None:
    device_id, _private_key, _fingerprint = enroll_and_pair(client)
    register_passkey(client)

    settings.api_token = TOKEN
    payload = {"pc_id": device_id}
    assert client.post("/api/v1/auth/challenges", json=payload).status_code == 401
    assert client.post("/api/v1/auth/challenges", json=payload, headers=_auth()).status_code == 200


def test_device_enrollment_is_not_gated(client: TestClient, settings: Settings) -> None:
    settings.api_token = TOKEN
    data = enroll_device(client)
    assert data["device_id"]


def test_production_fails_closed_without_token(client: TestClient, settings: Settings) -> None:
    settings.environment = "production"
    settings.api_token = None
    assert client.get("/api/v1/devices").status_code == 500
