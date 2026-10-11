"""Tests for database-persisted server identity.

The server signing key must survive restarts/deploys, so it is generated once
and stored in the ``server_config`` row instead of relying on a file or env var.
"""

from __future__ import annotations

from app.core.security import SIGNING_KEY_ENV, ServerSigningKey
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
