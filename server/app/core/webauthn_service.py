"""Thin wrapper around the maintained ``webauthn`` library.

The server is the Relying Party. Registration and authentication assertions
are verified here using the library — no custom cryptography is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, options_to_json_dict
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


class WebAuthnError(Exception):
    """A WebAuthn verification/enrollment failure with a safe message."""


@dataclass
class RegistrationResult:
    credential_id: str
    public_key: bytes
    sign_count: int
    aaguid: str | None


@dataclass
class AuthenticationResult:
    credential_id: str
    new_sign_count: int
    user_verified: bool


def build_registration_options(
    *, rp_id: str, rp_name: str, account_id: str, account_email: str, challenge: bytes
) -> tuple[dict, bytes]:
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=account_id.encode("utf-8"),
        user_name=account_email,
        user_display_name=account_email,
        challenge=challenge,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return options_to_json_dict(options), options.challenge


def verify_registration(
    *,
    credential: dict,
    expected_challenge: bytes,
    rp_id: str,
    allowed_origins: list[str],
) -> RegistrationResult:
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=allowed_origins,
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        raise WebAuthnError("Passkey registration could not be verified.") from exc
    return RegistrationResult(
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        aaguid=verified.aaguid,
    )


def build_authentication_options(
    *,
    rp_id: str,
    challenge: bytes,
    credential_ids: list[str],
) -> tuple[dict, bytes]:
    allow = [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes_safe(cid), type=PublicKeyCredentialType.PUBLIC_KEY
        )
        for cid in credential_ids
    ]
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        allow_credentials=allow or None,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options_to_json_dict(options), options.challenge


def verify_authentication(
    *,
    credential: dict,
    expected_challenge: bytes,
    rp_id: str,
    allowed_origins: list[str],
    credential_public_key: bytes,
    current_sign_count: int,
) -> AuthenticationResult:
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=allowed_origins,
            credential_public_key=credential_public_key,
            credential_current_sign_count=current_sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        raise WebAuthnError("Passkey authentication could not be verified.") from exc
    return AuthenticationResult(
        credential_id=bytes_to_base64url(verified.credential_id),
        new_sign_count=verified.new_sign_count,
        user_verified=verified.user_verified,
    )


def base64url_to_bytes_safe(value: str) -> bytes:
    from webauthn.helpers import base64url_to_bytes

    return base64url_to_bytes(value)
