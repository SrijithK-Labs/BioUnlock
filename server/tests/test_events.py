from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import SecurityEvent, utcnow
from tests.conftest import enroll_and_pair


def test_security_events_days_filter(client: TestClient, app) -> None:
    enroll_and_pair(client)

    session = app.state.session_factory()
    events = session.execute(select(SecurityEvent)).scalars().all()
    assert events
    for event in events:
        event.created_at = utcnow() - timedelta(days=40)
    session.commit()
    session.close()

    assert client.get("/api/v1/security-events?days=30").json() == []
    assert len(client.get("/api/v1/security-events?days=60").json()) == len(events)


def test_security_events_limit_is_capped(client: TestClient) -> None:
    enroll_and_pair(client)
    listing = client.get("/api/v1/security-events?limit=99999").json()
    assert isinstance(listing, list)
