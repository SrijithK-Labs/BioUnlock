from fastapi.testclient import TestClient

from tests.conftest import enroll_and_pair
from tests.support.helpers import device_auth_header, new_device_keypair


def test_list_devices_after_pairing(client: TestClient) -> None:
    device_id, _key, _fp = enroll_and_pair(client)
    devices = client.get("/api/v1/devices").json()
    assert len(devices) == 1
    assert devices[0]["id"] == device_id
    assert devices[0]["status"] == "active"
    assert devices[0]["is_online"] is False


def test_re_enroll_same_key_reuses_device(client: TestClient) -> None:
    _private_key, public_pem = new_device_keypair()
    payload = {"name": "Test PC", "platform": "windows", "public_key": public_pem}
    first = client.post("/api/v1/devices/enroll", json=payload)
    second = client.post("/api/v1/devices/enroll", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["device_id"] == second.json()["device_id"]


def test_re_enroll_keeps_existing_pairing(client: TestClient) -> None:
    private_key, public_pem = new_device_keypair()
    payload = {"name": "Test PC", "platform": "windows", "public_key": public_pem}
    first = client.post("/api/v1/devices/enroll", json=payload).json()
    client.post("/api/v1/pairing/confirm", json={"pairing_code": first["pairing_code"]})

    second = client.post("/api/v1/devices/enroll", json=payload).json()
    assert second["device_id"] == first["device_id"]

    device = client.get(f"/api/v1/devices/{first['device_id']}").json()
    assert device["status"] == "active"


def test_get_device_detail(client: TestClient) -> None:
    device_id, _key, _fp = enroll_and_pair(client)
    response = client.get(f"/api/v1/devices/{device_id}")
    assert response.status_code == 200
    assert response.json()["id"] == device_id


def test_get_device_detail_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/devices/does-not-exist").status_code == 404


def test_revoke_device(client: TestClient) -> None:
    device_id, _key, _fp = enroll_and_pair(client)
    response = client.post(f"/api/v1/devices/{device_id}/revoke")
    assert response.status_code == 200
    device = client.get(f"/api/v1/devices/{device_id}").json()
    assert device["status"] == "revoked"


def test_revoked_device_cannot_authenticate(client: TestClient, server_fingerprint: str) -> None:
    device_id, key, fp = enroll_and_pair(client)
    client.post(f"/api/v1/devices/{device_id}/revoke")
    header = device_auth_header(key, fp, device_id)
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_delete_revoked_device(client: TestClient) -> None:
    device_id, _key, _fp = enroll_and_pair(client)
    client.post(f"/api/v1/devices/{device_id}/revoke")
    response = client.delete(f"/api/v1/devices/{device_id}")
    assert response.status_code == 200
    assert client.get(f"/api/v1/devices/{device_id}").status_code == 404
    assert client.get("/api/v1/devices").json() == []


def test_delete_active_device_is_rejected(client: TestClient) -> None:
    device_id, _key, _fp = enroll_and_pair(client)
    response = client.delete(f"/api/v1/devices/{device_id}")
    assert response.status_code == 409
    assert client.get(f"/api/v1/devices/{device_id}").status_code == 200


def test_delete_unknown_device(client: TestClient) -> None:
    assert client.delete("/api/v1/devices/missing").status_code == 404


def test_delete_device_purges_related_rows(client: TestClient) -> None:
    device_id, _key, _fp = enroll_and_pair(client)
    client.post(f"/api/v1/devices/{device_id}/revoke")
    client.delete(f"/api/v1/devices/{device_id}")
    events = client.get("/api/v1/security-events").json()
    assert all(event["device_id"] != device_id for event in events)
    assert any(event["event_type"] == "device_deleted" for event in events)


def test_new_device_detail(client: TestClient, server_fingerprint: str) -> None:
    device_id, key, fp = enroll_and_pair(client)
    me = client.get("/api/v1/devices/me", headers=device_auth_header(key, fp, device_id))
    assert me.status_code == 200
    assert me.json()["id"] == device_id
    assert me.json()["status"] == "active"


def test_device_auth_invalid_signature(client: TestClient) -> None:
    device_id, key, fp = enroll_and_pair(client)
    header = device_auth_header(key, fp, device_id)
    header["Authorization"] = header["Authorization"][:-4] + "AAAA"
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_device_auth_expired(client: TestClient) -> None:
    device_id, key, fp = enroll_and_pair(client)
    header = device_auth_header(key, fp, device_id, expired=True, expiry_offset=600)
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_device_auth_wrong_key(client: TestClient) -> None:
    device_id, _key, fp = enroll_and_pair(client)
    other_key, _pem = new_device_keypair()
    header = device_auth_header(other_key, fp, device_id)
    assert client.get("/api/v1/devices/me", headers=header).status_code == 401


def test_device_auth_failures_are_indistinguishable(client: TestClient) -> None:
    device_id, key, fp = enroll_and_pair(client)

    unknown = device_auth_header(key, fp, "00000000-0000-0000-0000-000000000000")
    bad_sig = device_auth_header(key, fp, device_id)
    bad_sig["Authorization"] = bad_sig["Authorization"][:-4] + "AAAA"
    expired = device_auth_header(key, fp, device_id, expired=True, expiry_offset=600)

    messages = set()
    for header in (unknown, bad_sig, expired):
        response = client.get("/api/v1/devices/me", headers=header)
        assert response.status_code == 401
        messages.add(response.json()["error"]["message"])
    assert messages == {"Device authentication failed."}


def test_heartbeat(client: TestClient) -> None:
    device_id, key, fp = enroll_and_pair(client)
    response = client.post("/api/v1/devices/me/heartbeat", headers=device_auth_header(key, fp, device_id))
    assert response.status_code == 200
    body = response.json()
    assert body["paired"] is True
    assert "pending_requests" in body
