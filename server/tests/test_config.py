"""Tests for database URL resolution.

On Vercel the Postgres integration injects connection strings under generic
names (``DATABASE_URL``, ``POSTGRES_URL``, or a store-prefixed
``<store>_DATABASE_URL``). These are picked up when ``BIO_DATABASE_URL`` is not
set, and normalised to the psycopg driver.
"""

from __future__ import annotations

import os

import pytest

from app.config import DEFAULT_DATABASE_URL, Settings


@pytest.fixture(autouse=True)
def _clear_db_env(monkeypatch):
    for name in list(os.environ):
        if name.upper().endswith("DATABASE_URL"):
            monkeypatch.delenv(name, raising=False)


def test_defaults_to_sqlite():
    assert Settings(_env_file=None).database_url == DEFAULT_DATABASE_URL


def test_bio_database_url_is_used_and_normalized(monkeypatch):
    monkeypatch.setenv("BIO_DATABASE_URL", "postgresql://user:pw@host/db")
    assert Settings(_env_file=None).database_url == "postgresql+psycopg://user:pw@host/db"


def test_database_url_fallback_is_adopted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@host/db")
    assert Settings(_env_file=None).database_url == "postgresql+psycopg://user:pw@host/db"


def test_postgres_url_fallback_is_adopted(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://user:pw@pooler/db?sslmode=require")
    assert (
        Settings(_env_file=None).database_url
        == "postgresql+psycopg://user:pw@pooler/db?sslmode=require"
    )


def test_store_prefixed_url_is_adopted(monkeypatch):
    monkeypatch.setenv(
        "biounlockdb_DATABASE_URL", "postgresql://user:pw@host/db?sslmode=require"
    )
    assert (
        Settings(_env_file=None).database_url
        == "postgresql+psycopg://user:pw@host/db?sslmode=require"
    )


def test_pooled_url_is_preferred_over_unpooled(monkeypatch):
    monkeypatch.setenv("myproj_DATABASE_URL", "postgresql://user:pw@pooler/db")
    monkeypatch.setenv("myproj_DATABASE_URL_UNPOOLED", "postgresql://user:pw@direct/db")
    assert Settings(_env_file=None).database_url == "postgresql+psycopg://user:pw@pooler/db"


def test_explicit_sqlite_is_left_untouched(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@host/db")
    settings = Settings(_env_file=None, database_url="sqlite:///./custom.db")
    assert settings.database_url == "sqlite:///./custom.db"
