"""Passkey (WebAuthn) credential enrollment and management."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.api.deps import client_ip, require_api_token
from app.core.rate_limit import rate_limit
from app.core.rp import allowed_origins_for, resolve_rp_id
from app.core.time import as_utc
from app.core.webauthn_service import (
    WebAuthnError,
    build_registration_options,
    verify_registration,
)
from app.database import get_db
from app.models import Challenge, ChallengePurpose, SecurityEventType, WebAuthnCredential, utcnow
from app.schemas import (
    CredentialOut,
    MessageResponse,
    RegistrationBeginResponse,
    RegistrationCompleteRequest,
)
from app.services.events import record_event
from app.services.ids import new_uuid
from app.services.requests import SINGLE_USER_ID

router = APIRouter(tags=["webauthn"])


@router.post(
    "/webauthn/register/begin",
    response_model=RegistrationBeginResponse,
    dependencies=[
        Depends(rate_limit("wa_register_begin", limit=30, window=60)),
        Depends(require_api_token),
    ],
)
def register_begin(
    request: Request,
    db: Session = Depends(get_db),
) -> RegistrationBeginResponse:
    settings = request.app.state.settings
    rp_id = resolve_rp_id(request, settings)
    challenge_bytes = secrets.token_bytes(32)
    options, _ = build_registration_options(
        rp_id=rp_id,
        rp_name=settings.rp_name,
        account_id=SINGLE_USER_ID,
        account_email=settings.rp_name,
        challenge=challenge_bytes,
    )
    expires_at = utcnow() + timedelta(seconds=settings.challenge_ttl_seconds)
    record = Challenge(
        id=new_uuid(),
        purpose=ChallengePurpose.registration,
        challenge=bytes_to_base64url(challenge_bytes),
        rp_id=rp_id,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return RegistrationBeginResponse(
        challenge_id=record.id,
        options=options,
        rp_id=rp_id,
        expires_at=expires_at,
    )


@router.post(
    "/webauthn/register/complete",
    response_model=CredentialOut,
    dependencies=[Depends(require_api_token)],
)
def register_complete(
    payload: RegistrationCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> CredentialOut:
    settings = request.app.state.settings
    challenge = db.get(Challenge, payload.challenge_id)
    if challenge is None or challenge.purpose != ChallengePurpose.registration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown registration challenge.")
    if challenge.used_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Challenge already used.")
    if as_utc(challenge.expires_at) <= utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Challenge expired.")

    try:
        result = verify_registration(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            rp_id=challenge.rp_id,
            allowed_origins=allowed_origins_for(settings, challenge.rp_id),
        )
    except WebAuthnError as exc:
        record_event(
            db,
            event_type=SecurityEventType.CHALLENGE_FAILED,
            detail="Passkey registration verification failed.",
            ip=client_ip(request),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == result.credential_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This passkey is already registered.")

    credential = WebAuthnCredential(
        id=new_uuid(),
        credential_id=result.credential_id,
        public_key=result.public_key,
        sign_count=result.sign_count,
        aaguid=result.aaguid,
        name=payload.name,
    )
    challenge.used_at = utcnow()
    db.add(credential)
    record_event(
        db,
        event_type=SecurityEventType.PASSKEY_REGISTERED,
        detail="Passkey registered.",
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(credential)
    return CredentialOut.model_validate(credential)


@router.get(
    "/webauthn/credentials",
    response_model=list[CredentialOut],
    dependencies=[Depends(require_api_token)],
)
def list_credentials(
    db: Session = Depends(get_db),
) -> list[CredentialOut]:
    credentials = db.execute(
        select(WebAuthnCredential).order_by(WebAuthnCredential.created_at.desc())
    ).scalars().all()
    return [CredentialOut.model_validate(c) for c in credentials]


@router.delete(
    "/webauthn/credentials/{credential_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_api_token)],
)
def delete_credential(
    credential_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> MessageResponse:
    credential = db.get(WebAuthnCredential, credential_id)
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found.")
    db.delete(credential)
    record_event(
        db,
        event_type=SecurityEventType.PASSKEY_REMOVED,
        detail="Passkey removed.",
        ip=client_ip(request),
    )
    db.commit()
    return MessageResponse(message="Passkey removed.")
