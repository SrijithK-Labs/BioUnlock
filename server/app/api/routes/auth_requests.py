"""Remote authentication challenges, requests, status and acknowledgements."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.api.deps import (
    client_ip,
    require_active_device,
    require_api_token,
)
from app.core.rate_limit import rate_limit
from app.core.rp import allowed_origins_for, resolve_rp_id
from app.core.webauthn_service import (
    WebAuthnError,
    build_authentication_options,
    verify_authentication,
)
from app.database import get_db
from app.models import (
    AuthRequest,
    AuthRequestStatus,
    Challenge,
    ChallengePurpose,
    Device,
    DeviceStatus,
    SecurityEventType,
    WebAuthnCredential,
    utcnow,
)
from app.schemas import (
    AckRequest,
    AckResponse,
    AuthenticationBeginRequest,
    AuthenticationBeginResponse,
    AuthenticationCompleteRequest,
    AuthRequestOut,
)
from app.services.challenges import consume_challenge
from app.services.events import record_event
from app.services.ids import new_uuid
from app.services.requests import as_utc, build_envelope, status_value

router = APIRouter(tags=["auth-requests"])


def _require_active_device_for_request(db: Session, pc_id: str) -> Device:
    device = db.get(Device, pc_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PC not found.")
    if device.status != DeviceStatus.active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PC is not paired and active.")
    return device


def _request_out(db: Session, request: AuthRequest) -> AuthRequestOut:
    device = db.get(Device, request.pc_id)
    return AuthRequestOut(
        id=request.id,
        pc_id=request.pc_id,
        pc_name=device.name if device else None,
        operation=request.operation,
        status=status_value(request),
        created_at=request.created_at,
        expires_at=request.expires_at,
        delivered_at=request.delivered_at,
        ack_at=request.ack_at,
        ack_reason=request.ack_reason,
    )


@router.post(
    "/auth/challenges",
    response_model=AuthenticationBeginResponse,
    dependencies=[
        Depends(rate_limit("challenge", limit=30, window=60)),
        Depends(require_api_token),
    ],
)
def create_challenge(
    payload: AuthenticationBeginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthenticationBeginResponse:
    settings = request.app.state.settings
    device = _require_active_device_for_request(db, payload.pc_id)

    credentials = db.execute(select(WebAuthnCredential)).scalars().all()
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Register a passkey before authorizing a PC.",
        )

    challenge_bytes = secrets.token_bytes(32)
    rp_id = resolve_rp_id(request, settings)
    options, _ = build_authentication_options(
        rp_id=rp_id,
        challenge=challenge_bytes,
        credential_ids=[c.credential_id for c in credentials],
    )
    expires_at = utcnow() + timedelta(seconds=settings.challenge_ttl_seconds)
    record = Challenge(
        id=new_uuid(),
        purpose=ChallengePurpose.authentication,
        challenge=bytes_to_base64url(challenge_bytes),
        rp_id=rp_id,
        pc_id=device.id,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return AuthenticationBeginResponse(
        challenge_id=record.id,
        options=options,
        rp_id=rp_id,
        expires_at=expires_at,
        pc_id=device.id,
        pc_name=device.name,
    )


@router.post(
    "/auth/requests",
    response_model=AuthRequestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit("auth_request", limit=30, window=60)),
        Depends(require_api_token),
    ],
)
async def create_auth_request(
    payload: AuthenticationCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthRequestOut:
    settings = request.app.state.settings
    server_key = request.app.state.server_signing_key

    challenge = db.get(Challenge, payload.challenge_id)
    if (
        challenge is None
        or challenge.purpose != ChallengePurpose.authentication
        or challenge.pc_id != payload.pc_id
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown authorization challenge.")
    if challenge.used_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Challenge already used.")
    if as_utc(challenge.expires_at) <= utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Challenge expired.")

    device = _require_active_device_for_request(db, payload.pc_id)
    if not consume_challenge(db, challenge.id):
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Challenge already used or expired.")
    db.commit()

    assertion = payload.assertion
    assertion_id = assertion.get("id")
    if not isinstance(assertion_id, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed assertion.")
    credential = db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == assertion_id)
    ).scalar_one_or_none()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown passkey.")

    try:
        result = verify_authentication(
            credential=assertion,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            rp_id=challenge.rp_id,
            allowed_origins=allowed_origins_for(settings, challenge.rp_id),
            credential_public_key=credential.public_key,
            current_sign_count=credential.sign_count,
        )
    except WebAuthnError as exc:
        record_event(
            db,
            event_type=SecurityEventType.CHALLENGE_FAILED,
            detail="Authorization assertion verification failed.",
            device_id=device.id,
            ip=client_ip(request),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    credential.sign_count = result.new_sign_count
    credential.last_used_at = utcnow()
    auth_request = AuthRequest(
        id=new_uuid(),
        pc_id=device.id,
        challenge_id=challenge.id,
        operation=payload.operation,
        nonce=secrets.token_hex(16),
        status=AuthRequestStatus.pending,
        expires_at=utcnow() + timedelta(seconds=settings.auth_request_ttl_seconds),
    )
    db.add(auth_request)
    record_event(
        db,
        event_type=SecurityEventType.AUTH_REQUEST_CREATED,
        detail=f"Authorization request for '{device.name}'.",
        device_id=device.id,
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(auth_request)

    # Attempt real-time delivery over the agent's outbound WebSocket.
    manager = request.app.state.connection_manager
    envelope = build_envelope(server_key, auth_request)
    delivered = await manager.send_to_device(device.id, {"type": "auth_request", "envelope": envelope})
    if delivered:
        auth_request.status = AuthRequestStatus.delivered
        auth_request.delivered_at = utcnow()
        record_event(
            db,
            event_type=SecurityEventType.AUTH_REQUEST_DELIVERED,
            detail="Delivered to PC.",
            device_id=device.id,
        )
        db.commit()
        db.refresh(auth_request)

    return _request_out(db, auth_request)


@router.get("/requests", response_model=list[AuthRequestOut], dependencies=[Depends(require_api_token)])
def list_requests(
    limit: int = 50,
    days: int = 30,
    db: Session = Depends(get_db),
) -> list[AuthRequestOut]:
    limit = max(1, min(limit, 200))
    days = max(1, min(days, 365))
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(AuthRequest)
        .where(AuthRequest.created_at >= since)
        .order_by(AuthRequest.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_request_out(db, r) for r in rows]


@router.get(
    "/requests/{request_id}",
    response_model=AuthRequestOut,
    dependencies=[Depends(require_api_token)],
)
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
) -> AuthRequestOut:
    auth_request = db.get(AuthRequest, request_id)
    if auth_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    # Lazily expire a stale pending request so the client sees the truth.
    if (
        auth_request.status in (AuthRequestStatus.pending, AuthRequestStatus.delivered)
        and as_utc(auth_request.expires_at) <= utcnow()
    ):
        auth_request.status = AuthRequestStatus.expired
        record_event(
            db,
            event_type=SecurityEventType.AUTH_REQUEST_EXPIRED,
            detail="Authorization request expired.",
            device_id=auth_request.pc_id,
        )
        db.commit()
        db.refresh(auth_request)
    return _request_out(db, auth_request)


@router.post("/requests/{request_id}/ack", response_model=AckResponse)
def acknowledge_request(
    request_id: str,
    payload: AckRequest,
    device: Device = Depends(require_active_device),
    db: Session = Depends(get_db),
) -> AckResponse:
    auth_request = db.get(AuthRequest, request_id)
    if auth_request is None or auth_request.pc_id != device.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    current = auth_request.status
    new_status = AuthRequestStatus(payload.status)

    if as_utc(auth_request.expires_at) <= utcnow() and current in (
        AuthRequestStatus.pending,
        AuthRequestStatus.delivered,
    ):
        auth_request.status = AuthRequestStatus.expired
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request expired.")

    if current in (AuthRequestStatus.verified, AuthRequestStatus.rejected):
        if current == new_status:
            return AckResponse(
                request_id=auth_request.id,
                status=status_value(auth_request),
                acknowledged_at=auth_request.ack_at or utcnow(),
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request already finalized with a different status.")

    if current == AuthRequestStatus.expired:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request expired.")

    auth_request.status = new_status
    auth_request.ack_at = utcnow()
    auth_request.ack_reason = payload.reason_code
    event_type = (
        SecurityEventType.AUTH_REQUEST_VERIFIED
        if new_status == AuthRequestStatus.verified
        else SecurityEventType.AUTH_REQUEST_REJECTED
    )
    record_event(
        db,
        event_type=event_type,
        detail=payload.reason_code or "",
        device_id=device.id,
    )
    db.commit()
    db.refresh(auth_request)
    return AckResponse(
        request_id=auth_request.id,
        status=status_value(auth_request),
        acknowledged_at=auth_request.ack_at,
    )
