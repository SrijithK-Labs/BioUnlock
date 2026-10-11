"""SQLAlchemy models for the BioUnlock backend.

All identifiers use UUIDs (stored as 36-char strings for SQLite/PostgreSQL
portability). Secrets are never stored in plaintext: pairing codes are stored
as hashes.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class DeviceStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    revoked = "revoked"


class AuthRequestStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    verified = "verified"
    rejected = "rejected"
    expired = "expired"


class ChallengePurpose(str, enum.Enum):
    registration = "registration"
    authentication = "authentication"


class SecurityEventType(str, enum.Enum):
    PASSKEY_REGISTERED = "passkey_registered"
    PASSKEY_REMOVED = "passkey_removed"
    DEVICE_ENROLLED = "device_enrolled"
    DEVICE_PAIRED = "device_paired"
    DEVICE_REVOKED = "device_revoked"
    DEVICE_HEARTBEAT = "device_heartbeat"
    AUTH_REQUEST_CREATED = "auth_request_created"
    AUTH_REQUEST_DELIVERED = "auth_request_delivered"
    AUTH_REQUEST_VERIFIED = "auth_request_verified"
    AUTH_REQUEST_REJECTED = "auth_request_rejected"
    AUTH_REQUEST_EXPIRED = "auth_request_expired"
    PAIRING_ATTEMPT_FAILED = "pairing_attempt_failed"
    CHALLENGE_FAILED = "challenge_failed"
    RATE_LIMITED = "rate_limited"


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aaguid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Challenge(Base):
    """A WebAuthn challenge issued by the RP and validated once."""

    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    purpose: Mapped[ChallengePurpose] = mapped_column(
        Enum(ChallengePurpose, native_enum=False, length=32)
    )
    challenge: Mapped[str] = mapped_column(String(512))
    rp_id: Mapped[str] = mapped_column(String(255))
    # For authentication challenges: the target PC being authorized.
    pc_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(50), default="windows")
    public_key_pem: Mapped[str] = mapped_column(Text)
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, native_enum=False, length=16), default=DeviceStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    auth_requests: Mapped[list[AuthRequest]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    code_prefix: Mapped[str] = mapped_column(String(16), index=True)
    qr_payload: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthRequest(Base):
    __tablename__ = "auth_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pc_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    challenge_id: Mapped[str | None] = mapped_column(
        ForeignKey("challenges.id", ondelete="SET NULL"), nullable=True
    )
    operation: Mapped[str] = mapped_column(String(50), default="remote_unlock")
    nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[AuthRequestStatus] = mapped_column(
        Enum(AuthRequestStatus, native_enum=False, length=16), default=AuthRequestStatus.pending
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ack_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    device: Mapped[Device] = relationship(back_populates="auth_requests")


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[SecurityEventType] = mapped_column(
        Enum(SecurityEventType, native_enum=False, length=40), index=True
    )
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
