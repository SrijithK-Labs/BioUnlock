"""Tests for the secret store fallback."""

from __future__ import annotations

import pytest

from biounlock_agent.config import ENV_MACHINE_SECRETS
from biounlock_agent.storage import (
    DpapiSecretStore,
    FileSecretStore,
    default_secret_store,
    dpapi_available,
)


def test_file_secret_store_roundtrip(home):
    store = FileSecretStore(home)
    assert store.get("device_key") is None

    store.set("device_key", b"private-material")
    assert store.get("device_key") == b"private-material"

    store.delete("device_key")
    assert store.get("device_key") is None


def test_file_secret_store_overwrites(home):
    store = FileSecretStore(home)
    store.set("k", b"one")
    store.set("k", b"two")
    assert store.get("k") == b"two"


@pytest.mark.skipif(not dpapi_available(), reason="Windows DPAPI (pywin32) is not available")
def test_default_secret_store_honors_machine_flag(home):
    user_store = default_secret_store(home, machine=False)
    machine_store = default_secret_store(home, machine=True)
    assert isinstance(user_store, DpapiSecretStore)
    assert isinstance(machine_store, DpapiSecretStore)
    assert user_store._machine is False
    assert machine_store._machine is True


def test_default_secret_store_follows_service_mode(monkeypatch, home):
    monkeypatch.setenv(ENV_MACHINE_SECRETS, "1")
    store = default_secret_store(home)
    if isinstance(store, DpapiSecretStore):
        assert store._machine is True


@pytest.mark.skipif(not dpapi_available(), reason="Windows DPAPI (pywin32) is not available")
def test_machine_scope_store_roundtrip(home):
    store = default_secret_store(home, machine=True)
    store.set("device_key", b"machine-material")
    assert store.get("device_key") == b"machine-material"

