"""Lifespan background tasks.

The sweeper transitions stale pending items so the API never reports a
never-ending "pending" state. Failures here must not crash the server.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import as_utc
from app.models import (
    AuthRequest,
    AuthRequestStatus,
    Challenge,
    PairingCode,
    utcnow,
)

logger = logging.getLogger(__name__)


def sweep_once(session_factory) -> int:
    """Expire stale challenges, pairing codes and pending requests."""
    now = utcnow()
    changed = 0
    session: Session = session_factory()
    try:
        pending = session.execute(
            select(AuthRequest).where(
                AuthRequest.status.in_(
                    [AuthRequestStatus.pending, AuthRequestStatus.delivered]
                )
            )
        ).scalars().all()
        for request in pending:
            if as_utc(request.expires_at) <= now:
                request.status = AuthRequestStatus.expired
                changed += 1

        for pairing in session.execute(
            select(PairingCode).where(PairingCode.used_at.is_(None))
        ).scalars().all():
            if as_utc(pairing.expires_at) <= now:
                pairing.used_at = now
                changed += 1

        for challenge in session.execute(
            select(Challenge).where(Challenge.used_at.is_(None))
        ).scalars().all():
            if as_utc(challenge.expires_at) <= now:
                challenge.used_at = now
                changed += 1

        if changed:
            session.commit()
    finally:
        session.close()
    return changed


async def sweeper_loop(session_factory, interval_seconds: int = 30) -> None:
    while True:
        try:
            await asyncio.to_thread(sweep_once, session_factory)
        except Exception:  # noqa: BLE001 - never crash the loop
            logger.exception("sweeper iteration failed")
        await asyncio.sleep(interval_seconds)
