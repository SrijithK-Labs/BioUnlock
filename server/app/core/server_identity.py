"""Server identity persistence.

The server's Ed25519 signing key is the root of trust PC agents pin during
pairing, so it must stay stable across restarts and deploys. Rather than rely
on an env var or a file (which does not survive on serverless hosts), the key
is stored in the database (``server_config``), generated once on first use.

``BIO_SIGNING_KEY`` still takes precedence when set, which is handy for local
development or for injecting a key from a secret manager.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import SIGNING_KEY_ENV, ServerSigningKey
from app.models import ServerConfig

logger = logging.getLogger(__name__)

SERVER_CONFIG_ID = 1


def load_or_create_signing_key(
    session_factory: sessionmaker[Session],
) -> ServerSigningKey:
    """Return the server signing key, storing a new one in the DB if absent."""
    env_pem = os.environ.get(SIGNING_KEY_ENV)
    if env_pem:
        return ServerSigningKey.from_pem(env_pem)

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
