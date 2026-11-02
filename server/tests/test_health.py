from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_versioned_health(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").status_code == 200


def test_server_info_has_no_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/server/info")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "BioUnlock"
    assert "server_signing_key_fingerprint" in body
    serialized = response.text.lower()
    for needle in ["private", "password", "secret", "token"]:
        assert needle not in serialized
