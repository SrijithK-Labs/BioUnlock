import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import enroll_and_pair
from tests.support.helpers import device_auth_header, new_device_keypair

WS_PATH = "/api/v1/ws/agent"


def test_ws_rejects_unauthenticated(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS_PATH):
            pass


def test_ws_rejects_unpaired_device(client: TestClient) -> None:
    private_key, public_pem = new_device_keypair()
    enrolled = client.post(
        "/api/v1/devices/enroll",
        json={"name": "Pending PC", "platform": "windows", "public_key": public_pem},
    ).json()
    header = device_auth_header(
        private_key, enrolled["server_signing_key_fingerprint"], enrolled["device_id"]
    )
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS_PATH, headers=header):
            pass


def test_ws_accepts_paired_device(client: TestClient) -> None:
    device_id, private_key, fingerprint = enroll_and_pair(client)
    header = device_auth_header(private_key, fingerprint, device_id)
    with client.websocket_connect(WS_PATH, headers=header) as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["device_id"] == device_id
        websocket.send_text("ping")
        assert websocket.receive_json()["type"] == "pong"
