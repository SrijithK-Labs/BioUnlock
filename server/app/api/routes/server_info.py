"""Server identity information used by PC agents during pairing."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__
from app.core.rp import resolve_rp_id
from app.schemas import ServerInfoResponse

router = APIRouter(tags=["server"])


@router.get("/server/info", response_model=ServerInfoResponse)
def server_info(request: Request) -> ServerInfoResponse:
    settings = request.app.state.settings
    server_key = request.app.state.server_signing_key
    return ServerInfoResponse(
        name="BioUnlock",
        version=__version__,
        rp_id=resolve_rp_id(request, settings),
        server_signing_key_fingerprint=server_key.fingerprint(),
        environment=settings.environment,
    )
