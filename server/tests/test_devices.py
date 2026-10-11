from fastapi.testclient import TestClient

from tests.conftest import (
    auth_header,
    enroll_and_pair,
    register_account,
)
from tests.support.helpers import device_auth_header, new_device_keypair


def test_list_devices_after_pairing(client: TestClient) -> None:
    token = register_account(client)
    device_id, _key, _fp = enroll_and_pair(client, token)
    devices = client.get("/api/v1/devices", headers=auth_header(token)).json()
    assert len(devices) == 1
    assert devices[0]["id"] == device_id
    assert devices[0]["status"] == "active"
    assert devices[0]["is_online"] is False


def test_get_device_detail_ownership(client: TestClient) -> None:
    token_a = register_account(client, email="a@example.com")
    token_b = register_account(client, email="b@example.com")
    device_id, _key, _fp = enroll_and_pair(client, token_a)
    assert client.get(f"/api/v1/devices/{device_id}", headers=auth_header(token_b)).status_code == 404
    assert client.get(f"/api/v1/devices/{device_id}", headers=auth_header(token_a)).status_code == 200


def test_revoke_device(client: TestClient) -> None:
    token = register_account(client)
    device_id, _key, _fp = enroll_and_pair(client, token)
    response = client.post(f"/api/v1/devices/{device_id}/revoke", headers=auth_header(token))
    assert response.status_code == 200
    device = client.get(f"/api/v1/devices/{device_id}", headers=auth_header(token)).json()
    assert device["status"] == "revoked"


def test_revoked_device_cannot_authenticate(client: TestClient, server_fingerprint: str) -> None:
    token = register_account(client)
    device_id, key, fp = enroll_and_pair(client, token)
    client.post(f"/api/v1/devices/{device_id}/revoke", headers=auth_header(token))
    header = device_auth_header(key, fp, device_id)
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_new_device_detail(client: TestClient, server_fingerprint: str) -> None:
    token = register_account(client)
    device_id, key, fp = enroll_and_pair(client, token)
    me = client.get("/api/v1/devices/me", headers=device_auth_header(key, fp, device_id))
    assert me.status_code == 200
    assert me.json()["id"] == device_id
    assert me.json()["status"] == "active"


def test_device_auth_invalid_signature(client: TestClient) -> None:
    token = register_account(client)
    device_id, key, fp = enroll_and_pair(client, token)
    header = device_auth_header(key, fp, device_id)
    header["Authorization"] = header["Authorization"][:-4] + "AAAA"
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_device_auth_expired(client: TestClient) -> None:
    token = register_account(client)
    device_id, key, fp = enroll_and_pair(client, token)
    header = device_auth_header(key, fp, device_id, expired=True, expiry_offset=600)
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_device_auth_wrong_key(client: TestClient) -> None:
    token = register_account(client)
    device_id, _key, fp = enroll_and_pair(client, token)
    other_key, _pem = new_device_keypair()
    header = device_auth_header(other_key, fp, device_id)
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_heartbeat(client: TestClient) -> None:
    token = register_account(client)
    device_id, key, fp = enroll_and_pair(client, token)
    response = client.post("/api/v1/devices/me/heartbeat", headers=device_auth_header(key, fp, device_id))
    assert response.status_code == 200
    body = response.json()
    assert body["paired"] is True
    assert body["account_email"] == "user@example.com"
