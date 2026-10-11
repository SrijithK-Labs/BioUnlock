"""Security event listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SecurityEvent
from app.schemas import SecurityEventOut

router = APIRouter(tags=["events"])


@router.get("/security-events", response_model=list[SecurityEventOut])
def list_security_events(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[SecurityEventOut]:
    limit = max(1, min(limit, 200))
    events = db.execute(
        select(SecurityEvent)
        .order_by(SecurityEvent.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        SecurityEventOut(
            id=e.id,
            event_type=e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
            detail=e.detail,
            device_id=e.device_id,
            created_at=e.created_at,
        )
        for e in events
    ]
