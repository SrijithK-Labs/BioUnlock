"""PC enrollment, listing, details, revocation, heartbeat and inbox."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_account, get_current_device, require_active_device
from app.core.rate_limit import rate_limit
from app.core.security import load_public_key_from_pem
from app.core.time import as_utc
from app.database import get_db
from app.models import AuthRequest, AuthRequestStatus, Device, DeviceStatus, SecurityEventType, utcnow
from app.schemas import (
    DeviceEnrollRequest,
    DeviceEnrollResponse,
    DeviceOut,
    HeartbeatResponse,
    MessageResponse,
)
from app.services.accounts import new_uuid
from app.services.events import record_event
from app.services.pairing import create_pairing
from app.services.requests import build_envelope

router = APIRouter(tags=["devices"])

ONLINE_WINDOW_SECONDS = 180


def device_online(device: Device, manager) -> bool:
    if device.status != DeviceStatus.active:
        return False
    if manager is not None and manager.is_connected(device.id):
        return True
    if device.last_seen_at is None:
        return False
    delta = (utcnow() - as_utc(device.last_seen_at)).total_seconds()
    return delta <= ONLINE_WINDOW_SECONDS


def device_to_out(device: Device, manager) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        platform=device.platform,
        status=device.status.value if hasattr(device.status, "value") else str(device.status),
        created_at=device.created_at,
        paired_at=device.paired_at,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
        is_online=device_online(device, manager),
        account_id=device.account_id,
    )


@router.post(
    "/devices/enroll",
    response_model=DeviceEnrollResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("enroll", limit=30, window=60))],
)
def enroll_device(
    payload: DeviceEnrollRequest, request: Request, db: Session = Depends(get_db)
) -> DeviceEnrollResponse:
    try:
        load_public_key_from_pem(payload.public_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="public_key must be an Ed25519 public key in PEM format.",
        ) from exc

    settings = request.app.state.settings
    server_key = request.app.state.server_signing_key
    device = Device(
        id=new_uuid(),
        name=payload.name,
        platform=payload.platform,
        public_key_pem=payload.public_key,
        status=DeviceStatus.pending,
    )
    db.add(device)
    db.flush()
    pairing, code, qr_payload = create_pairing(
        db,
        device=device,
        ttl_seconds=settings.pairing_ttl_seconds,
        server_fingerprint=server_key.fingerprint(),
    )
    db.commit()
    return DeviceEnrollResponse(
        device_id=device.id,
        device_name=device.name,
        pairing_code=code,
        qr_payload=qr_payload,
        expires_at=pairing.expires_at,
        server_signing_public_key=server_key.public_key_pem().decode("utf-8"),
        server_signing_key_fingerprint=server_key.fingerprint(),
    )


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(
    request: Request,
    account=Depends(get_current_account),
    db: Session = Depends(get_db),
) -> list[DeviceOut]:
    devices = db.execute(
        select(Device).where(Device.account_id == account.id).order_by(Device.created_at.desc())
    ).scalars().all()
    manager = request.app.state.connection_manager
    return [device_to_out(d, manager) for d in devices]


@router.get("/devices/me", response_model=DeviceOut)
def device_me(request: Request, device: Device = Depends(get_current_device)) -> DeviceOut:
    return device_to_out(device, request.app.state.connection_manager)


@router.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: str,
    request: Request,
    account=Depends(get_current_account),
    db: Session = Depends(get_db),
) -> DeviceOut:
    device = db.get(Device, device_id)
    if device is None or device.account_id != account.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return device_to_out(device, request.app.state.connection_manager)


@router.post("/devices/{device_id}/revoke", response_model=MessageResponse)
async def revoke_device(
    device_id: str,
    request: Request,
    account=Depends(get_current_account),
    db: Session = Depends(get_db),
) -> MessageResponse:
    device = db.get(Device, device_id)
    if device is None or device.account_id != account.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    device.status = DeviceStatus.revoked
    device.revoked_at = utcnow()
    record_event(
        db,
        account_id=account.id,
        event_type=SecurityEventType.DEVICE_REVOKED,
        detail=f"Device '{device.name}' revoked by owner.",
        device_id=device.id,
        ip=client_ip(request),
    )
    db.commit()
    await request.app.state.connection_manager.close_device(device.id, code=4001)
    return MessageResponse(message="Device revoked.")


@router.post("/devices/me/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    request: Request,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    settings = request.app.state.settings
    device.last_seen_at = utcnow()
    account_email = None
    paired = device.status == DeviceStatus.active and device.account_id is not None
    pending = 0
    if device.account_id is not None:
        from app.models import Account

        account = db.get(Account, device.account_id)
        account_email = account.email if account else None
        pending = len(
            db.execute(
                select(AuthRequest).where(
                    AuthRequest.pc_id == device.id,
                    AuthRequest.status.in_([AuthRequestStatus.pending, AuthRequestStatus.delivered]),
                )
            ).scalars().all()
        )
    db.commit()
    return HeartbeatResponse(
        server_time=utcnow(),
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        paired=paired,
        account_email=account_email,
        pending_requests=pending,
    )


@router.get("/devices/me/inbox")
def inbox(
    request: Request,
    device: Device = Depends(require_active_device),
    db: Session = Depends(get_db),
) -> dict:
    """Long-poll fallback delivery: return pending envelopes for this PC."""
    server_key = request.app.state.server_signing_key
    pending = db.execute(
        select(AuthRequest).where(
            AuthRequest.pc_id == device.id,
            AuthRequest.status.in_([AuthRequestStatus.pending, AuthRequestStatus.delivered]),
        )
    ).scalars().all()
    envelopes = []
    for req in pending:
        if as_utc(req.expires_at) <= utcnow():
            continue
        envelopes.append(build_envelope(server_key, req))
    return {"requests": envelopes}
