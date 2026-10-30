"""Atomic single-use WebAuthn challenge consumption."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Challenge, utcnow


def consume_challenge(db: Session, challenge_id: str) -> bool:
    """Claim an unexpired challenge exactly once, including under concurrency."""
    now = utcnow()
    result = db.execute(
        update(Challenge)
        .where(
            Challenge.id == challenge_id,
            Challenge.used_at.is_(None),
            Challenge.expires_at > now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1
