from fastapi.testclient import TestClient

from tests.conftest import auth_header, register_account


def test_register_and_me(client: TestClient) -> None:
    token = register_account(client)
    response = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


def test_register_duplicate_email(client: TestClient) -> None:
    register_account(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert response.status_code == 409


def test_register_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_register_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "password123"},
    )
    assert response.status_code == 422


def test_login_success_and_case_insensitive_email(client: TestClient) -> None:
    register_account(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "USER@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert response.json()["token"]


def test_login_wrong_password(client: TestClient) -> None:
    register_account(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    assert response.status_code == 401


def test_protected_endpoint_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_session(client: TestClient) -> None:
    token = register_account(client)
    assert client.post("/api/v1/auth/logout", headers=auth_header(token)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


def test_invalid_token_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me", headers=auth_header("garbage")).status_code == 401


def test_security_events_recorded(client: TestClient) -> None:
    token = register_account(client)
    events = client.get("/api/v1/security-events", headers=auth_header(token)).json()
    types = {e["event_type"] for e in events}
    assert "user_registered" in types
