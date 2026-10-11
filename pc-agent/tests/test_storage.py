"""Tests for the secret store fallback."""

from __future__ import annotations

from biounlock_agent.storage import FileSecretStore


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
