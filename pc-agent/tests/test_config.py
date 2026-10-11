"""Tests for configuration persistence and paths."""

from __future__ import annotations

from biounlock_agent.config import ENV_HOME, AgentConfig, ConfigStore, default_home


def test_config_roundtrip(home):
    store = ConfigStore(home)
    assert store.load().is_enrolled is False

    config = AgentConfig(
        server_url="https://unlock.example.com",
        device_id="device-1",
        device_name="Workstation",
        server_signing_public_key="-----BEGIN PUBLIC KEY-----",
        server_signing_key_fingerprint="abc123",
        paired=True,
        account_email="user@example.com",
    )
    store.save(config)

    loaded = store.load()
    assert loaded.is_enrolled is True
    assert loaded.is_paired is True
    assert loaded.server_url == "https://unlock.example.com"
    assert loaded.account_email == "user@example.com"


def test_reset_removes_config(home):
    store = ConfigStore(home)
    store.save(AgentConfig(server_url="https://x"))
    assert store.exists() is True
    store.reset()
    assert store.exists() is False
    assert store.load().server_url is None


def test_is_paired_requires_enrollment(home):
    config = AgentConfig(paired=True, account_email="a@b")
    assert config.is_paired is False


def test_default_home_honors_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom-home"
    monkeypatch.setenv(ENV_HOME, str(target))
    assert default_home() == target
