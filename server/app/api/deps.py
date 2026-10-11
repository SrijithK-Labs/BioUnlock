"""FastAPI dependencies: database session, current account, current device."""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import device_auth_message, hash_token, verify_message_signature
from app.core.time import as_utc
from app.database import get_db
from app.models import Account, Device, DeviceStatus, SessionToken, utcnow


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def get_current_account(
    request: Request, db: Session = Depends(get_db)
) -> Account:
    token = _bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    record = db.execute(
        select(SessionToken).where(SessionToken.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if record is None or record.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.")
    if as_utc(record.expires_at) <= utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")
    account = db.get(Account, record.account_id)
    if account is None or not account.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable.")
    return account


def _parse_device_auth(header: str) -> tuple[str, int, str] | None:
    if not header.lower().startswith("biounlock "):
        return None
    credential = header[len("biounlock "):].strip()
    parts = credential.split(".", 2)
    if len(parts) != 3:
        return None
    device_id, expiry_raw, signature = parts
    try:
        expiry = int(expiry_raw)
    except ValueError:
        return None
    return device_id, expiry, signature


def get_current_device(request: Request, db: Session = Depends(get_db)) -> Device:
    header = request.headers.get("authorization", "")
    return resolve_device(
        db, header, request.app.state.settings, request.app.state.server_signing_key
    )


def resolve_device(db: Session, header: str, settings, server_key) -> Device:
    parsed = _parse_device_auth(header)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device authentication required.",
            headers={"WWW-Authenticate": "Biounlock"},
        )
    device_id, expiry, signature = parsed
    device = db.get(Device, device_id)
    if device is None or device.status == DeviceStatus.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown device.")

    now = int(time.time())
    if expiry < now - settings.clock_skew_seconds or expiry > now + settings.session_ttl_seconds * 4:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device signature expired.")

    message = device_auth_message(server_key.fingerprint(), device_id, expiry)
    if not verify_message_signature(message, signature, device.public_key_pem):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device signature.")
    return device


def require_active_device(device: Device = Depends(get_current_device)) -> Device:
    if device.status != DeviceStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device is not paired and active.",
        )
    return device
