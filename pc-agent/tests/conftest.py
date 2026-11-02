"""Pytest fixtures for the BioUnlock PC agent."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from support import memory_replay_store

from biounlock_agent.api_client import Enrollment, Heartbeat, ServerInfo
from biounlock_agent.crypto import generate_identity, public_key_fingerprint, public_key_pem
from biounlock_agent.storage import FileSecretStore


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture()
def device_identity():
    return generate_identity()


@pytest.fixture()
def secret_store(home: Path) -> FileSecretStore:
    return FileSecretStore(home)


@pytest.fixture()
def replay_store():
    store = memory_replay_store()
    yield store
    store.close()


@pytest.fixture()
def server_key():
    return ed25519.Ed25519PrivateKey.generate()


@pytest.fixture()
def server_pub_pem(server_key) -> str:
    return public_key_pem(server_key)


@pytest.fixture()
def server_fingerprint(server_key) -> str:
    return public_key_fingerprint(server_key)


class FakeApi:
    """Stand-in for :class:`~biounlock_agent.api_client.ApiClient`."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.server_info_value: ServerInfo | None = None
        self.enroll_value: Enrollment | None = None
        self.heartbeat_value: Heartbeat | None = None
        self.inbox_value: list[dict] = []
        self.acks: list[dict] = []
        self.closed = False
        self.enroll_name: str | None = None

    def server_info(self) -> ServerInfo:
        assert self.server_info_value is not None
        return self.server_info_value

    def enroll(self, *, name: str, platform: str = "windows") -> Enrollment:
        self.enroll_name = name
        assert self.enroll_value is not None
        return self.enroll_value

    def heartbeat(self) -> Heartbeat:
        assert self.heartbeat_value is not None
        return self.heartbeat_value

    def inbox(self) -> list[dict]:
        return list(self.inbox_value)

    def ack(self, request_id: str, *, status: str, reason_code=None, observed_at=None) -> dict:
        self.acks.append(
            {
                "request_id": request_id,
                "status": status,
                "reason_code": reason_code,
                "observed_at": observed_at,
            }
        )
        return {"request_id": request_id, "status": status}

    def authorization_header(self) -> str:
        return "Biounlock fake.deadbeef"

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def fake_api() -> FakeApi:
    return FakeApi()


@pytest.fixture()
def api_factory(fake_api: FakeApi):
    def factory(**kwargs) -> FakeApi:
        fake_api.kwargs = kwargs
        return fake_api

    return factory
