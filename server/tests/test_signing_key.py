"""Tests for loading the server signing key from a file or an env var.

Keeping this key stable is what lets PC agents trust the same server identity
across restarts and deploys (important on hosts with an ephemeral filesystem).
"""

from __future__ import annotations

import pytest

from app.core.security import SIGNING_KEY_ENV, ServerSigningKey, SigningKeyError


def test_loads_signing_key_from_env(tmp_path, monkeypatch):
    source = tmp_path / "key.pem"
    original = ServerSigningKey(source, overwrite=True)

    monkeypatch.setenv(SIGNING_KEY_ENV, source.read_text(encoding="utf-8"))

    missing = tmp_path / "does-not-exist.pem"
    loaded = ServerSigningKey(missing)

    assert loaded.fingerprint() == original.fingerprint()
    assert not missing.exists()


def test_env_value_accepts_escaped_newlines(tmp_path, monkeypatch):
    source = tmp_path / "key.pem"
    original = ServerSigningKey(source, overwrite=True)

    monkeypatch.setenv(
        SIGNING_KEY_ENV, source.read_text(encoding="utf-8").replace("\n", "\\n")
    )

    loaded = ServerSigningKey(tmp_path / "missing.pem")

    assert loaded.fingerprint() == original.fingerprint()


def test_invalid_env_value_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(SIGNING_KEY_ENV, "not a pem key")

    with pytest.raises(SigningKeyError):
        ServerSigningKey(tmp_path / "missing.pem")
