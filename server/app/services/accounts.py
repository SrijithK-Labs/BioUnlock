"""Account/session helpers."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token, new_token
from app.models import Account, SessionToken, utcnow


def create_session(db: Session, account: Account, ttl_seconds: int) -> tuple[str, SessionToken]:
    token = new_token()
    record = SessionToken(
        account_id=account.id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(seconds=ttl_seconds),
    )
    db.add(record)
    return token, record


def revoke_session(db: Session, token: str) -> None:
    record = db.execute(
        select(SessionToken).where(SessionToken.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if record is not None and record.revoked_at is None:
        record.revoked_at = utcnow()


def new_uuid() -> str:
    return str(uuid.uuid4())
