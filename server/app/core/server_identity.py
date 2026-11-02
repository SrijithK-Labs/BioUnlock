"""Stable server signing identity for tests and development.

Deployed environments must load ``BIO_SIGNING_KEY`` from a secret store. Only
development and explicit test harnesses may persist a generated key in the DB.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import SIGNING_KEY_ENV, ServerSigningKey, SigningKeyError
from app.models import ServerConfig

logger = logging.getLogger(__name__)

SERVER_CONFIG_ID = 1


def load_or_create_signing_key(
    session_factory: sessionmaker[Session],
    *,
    require_external: bool = False,
) -> ServerSigningKey:
    """Return the server signing key, storing a new one in the DB if absent."""
    env_pem = os.environ.get(SIGNING_KEY_ENV)
    if env_pem:
        key = ServerSigningKey.from_pem(env_pem)
        if require_external:
            try:
                with session_factory() as session:
                    row = session.get(ServerConfig, SERVER_CONFIG_ID)
                    if row is not None and row.signing_key_pem is not None:
                        row.signing_key_pem = None
                        session.commit()
            except SQLAlchemyError as exc:
                raise SigningKeyError(
                    "Could not remove the legacy database signing key."
                ) from exc
        return key
    if require_external:
        raise SigningKeyError(f"{SIGNING_KEY_ENV} is required in deployed environments.")

    try:
        with session_factory() as session:
            row = session.get(ServerConfig, SERVER_CONFIG_ID)
            if row is not None and row.signing_key_pem:
                return ServerSigningKey.from_pem(row.signing_key_pem)

            key = ServerSigningKey.generate()
            if row is None:
                session.add(
                    ServerConfig(id=SERVER_CONFIG_ID, signing_key_pem=key.to_pem())
                )
            else:
                row.signing_key_pem = key.to_pem()
            try:
                session.commit()
            except SQLAlchemyError:
                # A concurrent cold start may have inserted the row first.
                session.rollback()
                row = session.get(ServerConfig, SERVER_CONFIG_ID)
                if row is not None and row.signing_key_pem:
                    return ServerSigningKey.from_pem(row.signing_key_pem)
                raise
            return key
    except SQLAlchemyError:
        logger.warning(
            "Could not persist the server signing key; using an ephemeral key "
            "for this process. Check the database connection and that "
            "migrations have run.",
            exc_info=True,
        )
        return ServerSigningKey.generate()
