"""Pytest fixtures: isolated app, client, and end-to-end flow helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Base
from app.factory import create_app
from tests.support.authenticator import SoftAuthenticator
from tests.support.helpers import b64url_decode as _decode
from tests.support.helpers import new_device_keypair

TEST_ORIGIN = "http://localhost:8000"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        data_dir=str(tmp_path / "data"),
        rp_id="localhost",
        rp_name="BioUnlock Test",
        allowed_origins=[TEST_ORIGIN],
        cors_origins=[TEST_ORIGIN],
        rate_limit_enabled=False,
        session_ttl_seconds=3600,
        challenge_ttl_seconds=120,
        pairing_ttl_seconds=300,
        auth_request_ttl_seconds=120,
    )


@pytest.fixture()
def app(settings: Settings):
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def server_fingerprint(app) -> str:
    return app.state.server_signing_key.fingerprint()


def enroll_device(client: TestClient, *, name: str = "Test PC") -> dict:
    _private_key, public_pem = new_device_keypair()
    response = client.post(
        "/api/v1/devices/enroll",
        json={"name": name, "platform": "windows", "public_key": public_pem},
    )
    assert response.status_code == 201, response.text
    return response.json()


def enroll_and_pair(client: TestClient, *, name: str = "Test PC"):
    """Returns (device_id, private_key, fingerprint)."""
    private_key, public_pem = new_device_keypair()
    enroll = client.post(
        "/api/v1/devices/enroll",
        json={"name": name, "platform": "windows", "public_key": public_pem},
    )
    assert enroll.status_code == 201, enroll.text
    data = enroll.json()
    confirm = client.post(
        "/api/v1/pairing/confirm",
        json={"pairing_code": data["pairing_code"]},
    )
    assert confirm.status_code == 200, confirm.text
    return data["device_id"], private_key, data["server_signing_key_fingerprint"]


def register_passkey(client: TestClient, authenticator: SoftAuthenticator | None = None):
    authenticator = authenticator or SoftAuthenticator(rp_id="localhost", origin=TEST_ORIGIN)
    begin = client.post("/api/v1/webauthn/register/begin")
    assert begin.status_code == 200, begin.text
    options = begin.json()
    challenge = _decode(options["options"]["challenge"])
    credential = authenticator.make_credential(challenge)
    complete = client.post(
        "/api/v1/webauthn/register/complete",
        json={"challenge_id": options["challenge_id"], "credential": credential, "name": "Test passkey"},
    )
    assert complete.status_code == 200, complete.text
    return authenticator


def create_auth_request(
    client: TestClient,
    device_id: str,
    authenticator: SoftAuthenticator,
    *,
    operation: str = "remote_unlock",
):
    begin = client.post(
        "/api/v1/auth/challenges",
        json={"pc_id": device_id},
    )
    assert begin.status_code == 200, begin.text
    data = begin.json()
    challenge = _decode(data["options"]["challenge"])
    assertion = authenticator.get_assertion(challenge)
    created = client.post(
        "/api/v1/auth/requests",
        json={
            "challenge_id": data["challenge_id"],
            "pc_id": device_id,
            "operation": operation,
            "assertion": assertion,
        },
    )
    return created
