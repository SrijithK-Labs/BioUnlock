"""Pairing code generation and confirmation.

Pairing codes are high-entropy, single-use, TTL-limited and attempt-limited.
Only a hash of the code is stored.
"""

from __future__ import annotations

import base64
import json
import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_secret
from app.core.time import as_utc
from app.models import Device, DeviceStatus, PairingCode, SecurityEventType, utcnow
from app.services.events import record_event

CODE_PREFIX_LEN = 6


def generate_pairing_code() -> str:
    raw = secrets.token_bytes(16)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def create_pairing(
    db: Session,
    *,
    device: Device,
    ttl_seconds: int,
    server_fingerprint: str,
) -> tuple[PairingCode, str, str]:
    # Invalidate any previous unused codes for this device.
    existing = db.execute(
        select(PairingCode).where(
            PairingCode.device_id == device.id, PairingCode.used_at.is_(None)
        )
    ).scalars().all()
    for old in existing:
        old.used_at = utcnow()

    code = generate_pairing_code()
    expires_at = utcnow() + timedelta(seconds=ttl_seconds)
    qr_payload = json.dumps(
        {
            "v": 1,
            "type": "biounlock-pairing",
            "device_id": device.id,
            "device_name": device.name,
            "pairing_code": code,
            "server_fingerprint": server_fingerprint,
            "server_url": None,
        }
    )
    pairing = PairingCode(
        id=secrets.token_hex(16),
        device_id=device.id,
        code_hash=hash_secret(code),
        code_prefix=code[:CODE_PREFIX_LEN],
        qr_payload=qr_payload,
        expires_at=expires_at,
    )
    db.add(pairing)
    return pairing, code, qr_payload


def confirm_pairing(
    db: Session,
    *,
    code: str,
    ip: str | None,
    max_attempts: int,
) -> Device:
    code = code.strip()
    if len(code) < CODE_PREFIX_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pairing code."
        )
    prefix = code[:CODE_PREFIX_LEN]
    matched = db.execute(
        select(PairingCode).where(
            PairingCode.code_prefix == prefix,
            PairingCode.used_at.is_(None),
        )
    ).scalars().first()

    if matched is None:
        record_event(
            db,
            event_type=SecurityEventType.PAIRING_ATTEMPT_FAILED,
            detail="Unknown pairing code.",
            ip=ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired pairing code."
        )

    matched.attempts += 1
    now = utcnow()

    if as_utc(matched.expires_at) <= now or matched.attempts > max_attempts:
        matched.used_at = now
        record_event(
            db,
            event_type=SecurityEventType.PAIRING_ATTEMPT_FAILED,
            detail="Expired or exhausted pairing code.",
            device_id=matched.device_id,
            ip=ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired pairing code."
        )

    if matched.code_hash != hash_secret(code):
        record_event(
            db,
            event_type=SecurityEventType.PAIRING_ATTEMPT_FAILED,
            detail="Incorrect pairing code.",
            device_id=matched.device_id,
            ip=ip,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired pairing code."
        )

    device = db.get(Device, matched.device_id)
    if device is None or device.status == DeviceStatus.revoked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Device is not available for pairing."
        )

    device.status = DeviceStatus.active
    device.paired_at = now
    matched.used_at = now
    record_event(
        db,
        event_type=SecurityEventType.DEVICE_PAIRED,
        detail=f"Device '{device.name}' paired.",
        device_id=device.id,
        ip=ip,
    )
    db.commit()
    db.refresh(device)
    return device
