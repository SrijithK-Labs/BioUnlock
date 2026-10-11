"""Version and health endpoints.

Health endpoints expose no configuration or secrets.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from app import __version__
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/health/ready", response_model=HealthResponse)
def readiness(request: Request, response: Response) -> HealthResponse:
    try:
        session = request.app.state.session_factory()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
    except Exception:  # noqa: BLE001
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unavailable", version=__version__)
    return HealthResponse(status="ready", version=__version__)
