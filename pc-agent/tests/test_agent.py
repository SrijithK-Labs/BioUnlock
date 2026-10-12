"""Tests for the agent's enrollment, pairing and envelope handling."""

from __future__ import annotations

import asyncio

import pytest
from support import build_envelope

import biounlock_agent.agent as agent_module
from biounlock_agent import unlock
from biounlock_agent.agent import Agent
from biounlock_agent.api_client import Enrollment, Heartbeat, ServerInfo
from biounlock_agent.config import (
    API_TOKEN_NAME,
    DEVICE_KEY_NAME,
    ENV_API_TOKEN,
    AgentConfig,
    ConfigStore,
)
from biounlock_agent.errors import AgentError, ApiError

NOW = 1500


def _enrollment(fingerprint: str) -> Enrollment:
    return Enrollment(
        device_id="pc-1",
        device_name="PC",
        pairing_code="CODE-1234",
        qr_payload="{}",
        expires_at="2030-01-01T00:00:00+00:00",
        server_signing_public_key=f"PEM-{fingerprint}",
        server_signing_key_fingerprint=fingerprint,
    )


def _make_agent(home, api_factory, replay_store, **kwargs) -> Agent:
    return Agent(
        home=home, api_factory=api_factory, replay_store=replay_store, unlock_dir=home, **kwargs
    )


def _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint) -> Agent:
    agent = _make_agent(home, api_factory, replay_store, clock=lambda: NOW)
    agent.config = AgentConfig(
        server_url="http://server",
        device_id="pc-1",
        device_name="PC",
        server_signing_public_key=server_pub_pem,
        server_signing_key_fingerprint=server_fingerprint,
        paired=True,
    )
    return agent


def test_enroll_pins_server_key_and_persists_identity(home, fake_api, api_factory, replay_store):
    fake_api.server_info_value = ServerInfo("BioUnlock", "0.1.0", "example.com", "FP", "production")
    fake_api.enroll_value = _enrollment("FP")

    agent = _make_agent(home, api_factory, replay_store)
    result = agent.enroll("http://server/", device_name="Workstation")

    assert result.device_id == "pc-1"
    assert agent.config.server_url == "http://server"
    assert agent.config.server_signing_key_fingerprint == "FP"
    assert agent.config.is_enrolled is True
    assert fake_api.enroll_name == "Workstation"
    assert agent.secret_store.get(DEVICE_KEY_NAME) is not None
    assert ConfigStore(home).load().device_id == "pc-1"


def test_enroll_rejects_inconsistent_server_key(home, fake_api, api_factory, replay_store):
    fake_api.server_info_value = ServerInfo("BioUnlock", "0.1.0", "example.com", "FP-A", "production")
    fake_api.enroll_value = _enrollment("FP-B")

    agent = _make_agent(home, api_factory, replay_store)
    with pytest.raises(AgentError):
        agent.enroll("http://server")


def test_enroll_sends_and_stores_api_token(home, fake_api, api_factory, replay_store):
    fake_api.server_info_value = ServerInfo("BioUnlock", "0.1.0", "example.com", "FP", "production")
    fake_api.enroll_value = _enrollment("FP")

    agent = _make_agent(home, api_factory, replay_store)
    agent.enroll("http://server/", api_token="secret-token")

    assert fake_api.kwargs["api_token"] == "secret-token"
    assert agent.secret_store.get(API_TOKEN_NAME) == b"secret-token"


def test_enroll_uses_env_token(home, fake_api, api_factory, replay_store, monkeypatch):
    monkeypatch.setenv(ENV_API_TOKEN, "env-token")
    fake_api.server_info_value = ServerInfo("BioUnlock", "0.1.0", "example.com", "FP", "production")
    fake_api.enroll_value = _enrollment("FP")

    agent = _make_agent(home, api_factory, replay_store)
    agent.enroll("http://server/")

    assert fake_api.kwargs["api_token"] == "env-token"


def test_enroll_uses_stored_token(home, fake_api, api_factory, replay_store):
    fake_api.server_info_value = ServerInfo("BioUnlock", "0.1.0", "example.com", "FP", "production")
    fake_api.enroll_value = _enrollment("FP")

    agent = _make_agent(home, api_factory, replay_store)
    agent.secret_store.set(API_TOKEN_NAME, b"stored-token")
    agent.enroll("http://server/")

    assert fake_api.kwargs["api_token"] == "stored-token"


def test_enroll_reports_missing_token_hint(home, api_factory, replay_store):
    class RejectingApi:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def server_info(self) -> ServerInfo:
            return ServerInfo("BioUnlock", "0.1.0", "example.com", "FP", "production")

        def enroll(self, *, name: str, platform: str = "windows") -> Enrollment:
            raise ApiError("A valid API token is required.", code="unauthorized", status_code=401)

        def close(self) -> None:
            pass

    agent = _make_agent(home, lambda **kwargs: RejectingApi(**kwargs), replay_store)
    with pytest.raises(AgentError, match="API token"):
        agent.enroll("http://server/")


def test_enroll_preserves_pairing_when_relinking_same_server(home, fake_api, api_factory, replay_store):
    fake_api.server_info_value = ServerInfo("BioUnlock", "0.1.0", "example.com", "FP", "production")
    fake_api.enroll_value = _enrollment("FP")

    agent = _make_agent(home, api_factory, replay_store)
    agent.config = AgentConfig(
        server_url="http://server",
        device_id="pc-1",
        device_name="PC",
        server_signing_public_key="PEM-FP",
        server_signing_key_fingerprint="FP",
        paired=True,
    )

    agent.enroll("http://server/")

    assert agent.config.device_id == "pc-1"
    assert agent.config.paired is True
    assert ConfigStore(home).load().paired is True


def test_enroll_resets_pairing_when_device_changes(home, fake_api, api_factory, replay_store):
    fake_api.server_info_value = ServerInfo("BioUnlock", "0.1.0", "example.com", "FP", "production")
    fake_api.enroll_value = _enrollment("FP")

    agent = _make_agent(home, api_factory, replay_store)
    agent.config = AgentConfig(
        server_url="http://server",
        device_id="old-device",
        server_signing_public_key="PEM-FP",
        server_signing_key_fingerprint="FP",
        paired=True,
    )

    agent.enroll("http://server")

    assert agent.config.device_id == "pc-1"
    assert agent.config.paired is False


def test_refresh_pairing_persists_state(home, fake_api, api_factory, replay_store, server_pub_pem, server_fingerprint):
    agent = _make_agent(home, api_factory, replay_store)
    agent.config = AgentConfig(
        server_url="http://server",
        device_id="pc-1",
        device_name="PC",
        server_signing_public_key=server_pub_pem,
        server_signing_key_fingerprint=server_fingerprint,
        paired=False,
    )
    fake_api.heartbeat_value = Heartbeat("t", 60, paired=True, pending_requests=2)

    heartbeat = agent.refresh_pairing()

    assert heartbeat.paired is True
    assert agent.config.paired is True
    assert ConfigStore(home).load().paired is True


def test_handle_envelope_verifies_and_acks(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    envelope = build_envelope(server_key, pc_id="pc-1")

    outcome = agent.handle_envelope(envelope)

    assert outcome.outcome == "verified"
    assert agent.processed_count == 1
    assert fake_api.acks[-1]["status"] == "verified"
    assert fake_api.acks[-1]["request_id"] == "req-1"


def test_handle_envelope_rejects_expired(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    envelope = build_envelope(server_key, pc_id="pc-1", expires_at=NOW - 100)

    outcome = agent.handle_envelope(envelope)

    assert outcome.outcome == "rejected"
    assert outcome.reason_code == "expired"
    assert fake_api.acks[-1]["status"] == "rejected"
    assert fake_api.acks[-1]["reason_code"] == "expired"


def test_handle_envelope_drops_bad_signature(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    envelope = build_envelope(server_key, pc_id="pc-1", signature="AAAA")

    outcome = agent.handle_envelope(envelope)

    assert outcome.outcome == "dropped"
    assert fake_api.acks == []


def test_handle_envelope_drops_when_not_paired(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    agent.config.paired = False
    envelope = build_envelope(server_key, pc_id="pc-1")

    outcome = agent.handle_envelope(envelope)

    assert outcome.outcome == "dropped"
    assert outcome.reason_code == "not_paired"
    assert fake_api.acks == []


def test_handle_envelope_rejects_replay(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    envelope = build_envelope(server_key, pc_id="pc-1")

    first = agent.handle_envelope(envelope)
    second = agent.handle_envelope(envelope)

    assert first.outcome == "verified"
    assert second.outcome == "dropped"
    assert second.reason_code == "replayed"
    assert len(fake_api.acks) == 1


def test_status_reports_unenrolled(home, api_factory, replay_store):
    agent = _make_agent(home, api_factory, replay_store)
    status = agent.status()
    assert status.enrolled is False
    assert status.paired is False
    assert status.processed_count == 0
    assert status.credential_enrolled is False


@pytest.mark.skipif(not unlock.dpapi_available(), reason="Windows DPAPI is not available")
def test_verified_unlock_issues_ticket(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint, monkeypatch):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    unlock.save_windows_credential(
        home, unlock.WindowsCredential(username="user", password="secret", domain="PC")
    )
    monkeypatch.setattr(unlock, "is_workstation_locked", lambda: True)
    envelope = build_envelope(server_key, pc_id="pc-1")

    outcome = agent.handle_envelope(envelope)

    assert outcome.outcome == "verified"
    ticket = unlock.read_unlock_ticket(home)
    assert ticket is not None
    assert ticket["request_id"] == "req-1"
    assert ticket["username"] == "user"
    assert ticket["password"] == "secret"


@pytest.mark.skipif(not unlock.dpapi_available(), reason="Windows DPAPI is not available")
def test_verified_unlock_when_already_unlocked_skips_ticket(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint, monkeypatch):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    credential = unlock.WindowsCredential(username="user", password="secret", domain="PC")
    unlock.save_windows_credential(home, credential)
    unlock.issue_unlock_ticket(home, request_id="stale", credential=credential)
    monkeypatch.setattr(unlock, "is_workstation_locked", lambda: False)

    outcome = agent.handle_envelope(build_envelope(server_key, pc_id="pc-1"))

    assert outcome.outcome == "verified"
    assert outcome.reason_code == "already_unlocked"
    assert unlock.read_unlock_ticket(home) is None


def test_verified_lock_locks_workstation(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint, monkeypatch):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    monkeypatch.setattr(unlock, "is_workstation_locked", lambda: False)
    calls = []
    monkeypatch.setattr(unlock, "lock_workstation", lambda: calls.append(True))

    outcome = agent.handle_envelope(build_envelope(server_key, pc_id="pc-1", operation="remote_lock"))

    assert outcome.outcome == "verified"
    assert outcome.reason_code is None
    assert calls == [True]
    assert fake_api.acks[-1]["status"] == "verified"
    assert fake_api.acks[-1]["reason_code"] is None


def test_verified_lock_when_already_locked_reports_reason(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint, monkeypatch):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    monkeypatch.setattr(unlock, "is_workstation_locked", lambda: True)
    calls = []
    monkeypatch.setattr(unlock, "lock_workstation", lambda: calls.append(True))

    outcome = agent.handle_envelope(build_envelope(server_key, pc_id="pc-1", operation="remote_lock"))

    assert outcome.outcome == "verified"
    assert outcome.reason_code == "already_locked"
    assert calls == []
    assert fake_api.acks[-1]["reason_code"] == "already_locked"


def test_verified_lock_failure_is_rejected(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint, monkeypatch):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    monkeypatch.setattr(unlock, "is_workstation_locked", lambda: False)

    def boom() -> None:
        raise unlock.UnlockError("nope")

    monkeypatch.setattr(unlock, "lock_workstation", boom)

    outcome = agent.handle_envelope(build_envelope(server_key, pc_id="pc-1", operation="remote_lock"))

    assert outcome.outcome == "rejected"
    assert outcome.reason_code == "lock_failed"
    assert fake_api.acks[-1]["status"] == "rejected"
    assert fake_api.acks[-1]["reason_code"] == "lock_failed"


@pytest.mark.skipif(not unlock.dpapi_available(), reason="Windows DPAPI is not available")
def test_verified_unlock_without_credential_still_succeeds(home, fake_api, api_factory, replay_store, server_key, server_pub_pem, server_fingerprint):
    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)

    outcome = agent.handle_envelope(build_envelope(server_key, pc_id="pc-1"))

    assert outcome.outcome == "verified"
    assert unlock.read_unlock_ticket(home) is None


def test_unenroll_clears_local_state(home, api_factory, replay_store):
    agent = _make_agent(home, api_factory, replay_store)
    agent.load_or_create_identity()
    agent.config = AgentConfig(
        server_url="http://server",
        device_id="pc-1",
        server_signing_public_key="PEM",
        server_signing_key_fingerprint="FP",
        paired=True,
    )
    agent.config_store.save(agent.config)

    agent.unenroll()

    assert agent.config.is_enrolled is False
    assert agent.secret_store.get(DEVICE_KEY_NAME) is None
    assert ConfigStore(home).exists() is False


def _heartbeat() -> Heartbeat:
    return Heartbeat(
        server_time="2026-01-01T00:00:00+00:00",
        heartbeat_interval_seconds=30,
        paired=True,
        pending_requests=0,
    )


def _run_briefly(agent: Agent) -> None:
    async def main() -> None:
        task = asyncio.ensure_future(agent.run())
        await asyncio.sleep(0.05)
        agent.request_stop()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(main())


def test_run_can_stop_and_start_again(
    monkeypatch, home, fake_api, api_factory, replay_store, server_pub_pem, server_fingerprint
):
    """Stopping and re-running the agent must not reuse a loop-bound stop event.

    ``asyncio.Event`` binds to the loop that first awaits it, so reusing one
    across runs raised "bound to a different event loop"; ``AgentRunner``
    swallowed that, leaving the PC showing as paired but doing nothing until a
    restart. ``run()`` now creates a fresh event each time.
    """
    fake_api.heartbeat_value = _heartbeat()

    class FakeDelivery:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def run(self, stop) -> None:
            await stop.wait()

    monkeypatch.setattr(agent_module, "DeliveryManager", FakeDelivery)

    agent = _paired_agent(home, api_factory, replay_store, server_pub_pem, server_fingerprint)
    _run_briefly(agent)
    _run_briefly(agent)
