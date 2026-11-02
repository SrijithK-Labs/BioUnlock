"""Tests for development database persistence and external server identity.

Development and tests may persist the signing key in ``server_config``. Deployed
environments must receive a stable key from an external secret store.
"""

from __future__ import annotations

import pytest

from app.core.security import SIGNING_KEY_ENV, ServerSigningKey, SigningKeyError
from app.core.server_identity import SERVER_CONFIG_ID, load_or_create_signing_key
from app.models import ServerConfig


def test_signing_key_is_generated_and_persisted(app):
    factory = app.state.session_factory
    first = load_or_create_signing_key(factory)
    second = load_or_create_signing_key(factory)

    assert first.fingerprint() == second.fingerprint()

    with factory() as session:
        row = session.get(ServerConfig, SERVER_CONFIG_ID)
        assert row is not None
        assert row.signing_key_pem
        assert ServerSigningKey.from_pem(row.signing_key_pem).fingerprint() == first.fingerprint()


def test_env_key_overrides_database(app, monkeypatch):
    source = ServerSigningKey.generate()
    monkeypatch.setenv(SIGNING_KEY_ENV, source.to_pem())

    key = load_or_create_signing_key(app.state.session_factory)

    assert key.fingerprint() == source.fingerprint()
    with app.state.session_factory() as session:
        assert session.get(ServerConfig, SERVER_CONFIG_ID) is None


def test_deployed_env_key_removes_legacy_database_key(app, monkeypatch):
    factory = app.state.session_factory
    old_key = ServerSigningKey.generate()
    with factory() as session:
        session.add(ServerConfig(id=SERVER_CONFIG_ID, signing_key_pem=old_key.to_pem()))
        session.commit()

    production_key = ServerSigningKey.generate()
    monkeypatch.setenv(SIGNING_KEY_ENV, production_key.to_pem())
    loaded = load_or_create_signing_key(factory, require_external=True)

    assert loaded.fingerprint() == production_key.fingerprint()
    with factory() as session:
        assert session.get(ServerConfig, SERVER_CONFIG_ID).signing_key_pem is None


def test_deployed_mode_requires_external_key(app, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)

    with pytest.raises(SigningKeyError, match="required in deployed environments"):
        load_or_create_signing_key(app.state.session_factory, require_external=True)
