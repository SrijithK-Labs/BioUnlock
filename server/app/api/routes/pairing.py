"""Phone-side pairing confirmation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_api_token
from app.api.routes.devices import device_to_out
from app.core.rate_limit import rate_limit
from app.database import get_db
from app.schemas import PairingConfirmRequest, PairingConfirmResponse
from app.services.pairing import confirm_pairing

router = APIRouter(tags=["pairing"])


@router.post(
    "/pairing/confirm",
    response_model=PairingConfirmResponse,
    dependencies=[
        Depends(rate_limit("pairing_confirm", limit=10, window=60)),
        Depends(require_api_token),
    ],
)
def pairing_confirm(
    payload: PairingConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PairingConfirmResponse:
    settings = request.app.state.settings
    device = confirm_pairing(
        db,
        code=payload.pairing_code,
        ip=client_ip(request),
        max_attempts=settings.pairing_max_attempts,
    )
    return PairingConfirmResponse(
        device=device_to_out(device, request.app.state.connection_manager),
        paired_at=device.paired_at,
    )
