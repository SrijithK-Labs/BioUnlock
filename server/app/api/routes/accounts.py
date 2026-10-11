"""Account registration, login, sessions and security events."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_account
from app.core.rate_limit import rate_limit
from app.core.security import hash_password, verify_password
from app.database import get_db
from app.models import Account, SecurityEvent, SecurityEventType, SessionToken
from app.schemas import (
    AccountOut,
    LoginRequest,
    RegisterRequest,
    SecurityEventOut,
    TokenResponse,
)
from app.services.accounts import create_session, new_uuid, revoke_session
from app.services.events import record_event

router = APIRouter(tags=["accounts"])


def _token_response(token: str, record: SessionToken, account: Account) -> TokenResponse:
    return TokenResponse(
        token=token,
        expires_at=record.expires_at,
        account=AccountOut.model_validate(account),
    )


@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", limit=10, window=60))],
)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    existing = db.execute(select(Account).where(Account.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    account = Account(id=new_uuid(), email=email, password_hash=hash_password(payload.password))
    db.add(account)
    db.flush()
    token, record = create_session(db, account, request.app.state.settings.session_ttl_seconds)
    record_event(
        db,
        account_id=account.id,
        event_type=SecurityEventType.USER_REGISTERED,
        detail="Account created.",
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(account)
    db.refresh(record)
    return _token_response(token, record, account)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", limit=20, window=60))],
)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    account = db.execute(select(Account).where(Account.email == email)).scalar_one_or_none()
    if account is None or not account.is_active or not verify_password(payload.password, account.password_hash):
        # Same error for unknown user and bad password.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    token, record = create_session(db, account, request.app.state.settings.session_ttl_seconds)
    record_event(
        db,
        account_id=account.id,
        event_type=SecurityEventType.USER_LOGIN,
        detail="Login succeeded.",
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(record)
    return _token_response(token, record, account)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        revoke_session(db, header[7:].strip())
    record_event(
        db,
        account_id=account.id,
        event_type=SecurityEventType.USER_LOGOUT,
        detail="Logout.",
        ip=client_ip(request),
    )
    db.commit()


@router.get("/auth/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)) -> AccountOut:
    return AccountOut.model_validate(account)


@router.get("/security-events", response_model=list[SecurityEventOut])
def security_events(
    request: Request,
    limit: int = 50,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> list[SecurityEventOut]:
    limit = max(1, min(limit, 200))
    events = db.execute(
        select(SecurityEvent)
        .where(SecurityEvent.account_id == account.id)
        .order_by(SecurityEvent.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        SecurityEventOut(
            id=e.id,
            event_type=e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
            detail=e.detail,
            device_id=e.device_id,
            created_at=e.created_at,
        )
        for e in events
    ]
