"""Pydantic request/response models for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class MessageResponse(BaseModel):
    message: str


# --- Accounts / sessions ---


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime
    account: AccountOut


# --- WebAuthn ---


class RegistrationBeginResponse(BaseModel):
    challenge_id: str
    options: dict[str, Any]
    rp_id: str
    expires_at: datetime


class RegistrationCompleteRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=200)


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str | None
    created_at: datetime
    last_used_at: datetime | None


class AuthenticationBeginRequest(BaseModel):
    pc_id: str


class AuthenticationBeginResponse(BaseModel):
    challenge_id: str
    options: dict[str, Any]
    rp_id: str
    expires_at: datetime
    pc_id: str
    pc_name: str


class AuthenticationCompleteRequest(BaseModel):
    challenge_id: str
    pc_id: str
    assertion: dict[str, Any]


# --- Devices / pairing ---


class DeviceEnrollRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    platform: str = Field(default="windows", max_length=50)
    public_key: str = Field(min_length=16)

    @field_validator("name", "platform")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class DeviceEnrollResponse(BaseModel):
    device_id: str
    device_name: str
    pairing_code: str
    qr_payload: str
    expires_at: datetime
    server_signing_public_key: str
    server_signing_key_fingerprint: str


class PairingConfirmRequest(BaseModel):
    pairing_code: str = Field(min_length=4, max_length=64)


class DeviceOut(BaseModel):
    id: str
    name: str
    platform: str
    status: str
    created_at: datetime
    paired_at: datetime | None
    last_seen_at: datetime | None
    revoked_at: datetime | None
    is_online: bool = False
    account_id: str | None = None


class PairingConfirmResponse(BaseModel):
    device: DeviceOut
    paired_at: datetime


class HeartbeatResponse(BaseModel):
    server_time: datetime
    heartbeat_interval_seconds: int
    paired: bool
    account_email: str | None = None
    pending_requests: int = 0


# --- Authorization requests ---


class AuthRequestOut(BaseModel):
    id: str
    pc_id: str
    pc_name: str | None = None
    operation: str
    status: str
    created_at: datetime
    expires_at: datetime
    delivered_at: datetime | None
    ack_at: datetime | None
    ack_reason: str | None


class EnvelopeOut(BaseModel):
    request_id: str
    account_id: str
    pc_id: str
    operation: str
    issued_at: int
    expires_at: int
    nonce: str
    signature: str
    server_signing_key_id: str


class AckRequest(BaseModel):
    status: Literal["verified", "rejected"]
    reason_code: str | None = Field(default=None, max_length=100)
    observed_at: int | None = None


class AckResponse(BaseModel):
    request_id: str
    status: str
    acknowledged_at: datetime


# --- Security events ---


class SecurityEventOut(BaseModel):
    id: int
    event_type: str
    detail: str
    device_id: str | None
    created_at: datetime


# --- Server info / health ---


class ServerInfoResponse(BaseModel):
    name: str
    version: str
    rp_id: str
    server_signing_key_fingerprint: str
    environment: str


class HealthResponse(BaseModel):
    status: str
    version: str
