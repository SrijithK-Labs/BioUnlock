"""FastAPI dependencies: database session and current device."""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import device_auth_message, verify_message_signature
from app.database import get_db
from app.models import Device, DeviceStatus


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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
