"""Database engine/session management.

All access goes through a session factory owned by the FastAPI app. In tests
the session factory is swapped to a temporary SQLite file.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _make_engine(url: str) -> Engine:
    connect_args: dict[str, Any]
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

        def _fk_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        engine = create_engine(url, connect_args=connect_args)
        event.listen(engine, "connect", _fk_pragma)
        return engine
    return create_engine(url, pool_pre_ping=True)


def create_engine_for_url(url: str) -> Engine:
    return _make_engine(url)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request):
    """FastAPI dependency yielding a database session."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()
