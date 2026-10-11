"""Verify the Alembic migration creates the expected schema on a fresh DB."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import get_settings

EXPECTED_TABLES = {
    "accounts",
    "session_tokens",
    "webauthn_credentials",
    "challenges",
    "devices",
    "pairing_codes",
    "auth_requests",
    "security_events",
    "alembic_version",
}


def test_migration_upgrade_creates_schema(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migrated.db"
    monkeypatch.setenv("BIO_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("BIO_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    server_root = Path(__file__).resolve().parents[1]
    config = Config(str(server_root / "alembic.ini"))
    config.set_main_option("script_location", str(server_root / "migrations"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables: {missing}"

    get_settings.cache_clear()


def test_migration_downgrade(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migrated_down.db"
    monkeypatch.setenv("BIO_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("BIO_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    server_root = Path(__file__).resolve().parents[1]
    config = Config(str(server_root / "alembic.ini"))
    config.set_main_option("script_location", str(server_root / "migrations"))
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "accounts" not in tables

    get_settings.cache_clear()
    os.environ.pop("BIO_DATABASE_URL", None)
