"""Security event recording. Details are sanitized and never contain secrets."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import SecurityEvent, SecurityEventType


def record_event(
    db: Session,
    *,
    account_id: str,
    event_type: SecurityEventType,
    detail: str = "",
    device_id: str | None = None,
    ip: str | None = None,
) -> SecurityEvent:
    event = SecurityEvent(
        account_id=account_id,
        device_id=device_id,
        event_type=event_type,
        detail=detail[:500],
        ip=ip,
    )
    db.add(event)
    return event
