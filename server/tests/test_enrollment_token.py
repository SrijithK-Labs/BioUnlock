"""Tests for the second-secret gate on passkey enrollment."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.deps import require_enrollment_token
from app.config import Settings
from app.database import Base
from app.factory import create_app
from tests.conftest import TEST_ORIGIN
from tests.support.authenticator import SoftAuthenticator
from tests.support.helpers import b64url_decode

API_TOKEN = "api-secret"
ENROLLMENT_TOKEN = "enroll-secret"


@pytest.fixture()
def gated_client(settings: Settings):
    settings.api_token = API_TOKEN
    settings.enrollment_token = ENROLLMENT_TOKEN
    application = create_app(settings, allow_unauthenticated_api_for_tests=True)
    Base.metadata.create_all(application.state.engine)
    with TestClient(application) as client:
        yield client
    application.state.engine.dispose()


def _headers(enrollment_token: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    if enrollment_token is not None:
        headers["X-BioUnlock-Enrollment"] = enrollment_token
    return headers


def _register(client: TestClient, *, enrollment_token: str | None = None):
    headers = _headers(enrollment_token)
    begin = client.post("/api/v1/webauthn/register/begin", headers=headers)
    if begin.status_code != 200:
        return begin
    options = begin.json()
    authenticator = SoftAuthenticator(rp_id="localhost", origin=TEST_ORIGIN)
    credential = authenticator.make_credential(
        b64url_decode(options["options"]["challenge"])
    )
    return client.post(
        "/api/v1/webauthn/register/complete",
        headers=headers,
        json={
            "challenge_id": options["challenge_id"],
            "credential": credential,
            "name": "Passkey",
        },
    )


def test_first_passkey_bootstraps_without_an_enrollment_token(
    gated_client: TestClient,
) -> None:
    assert _register(gated_client).status_code == 200


def test_extra_passkey_requires_the_enrollment_token(
    gated_client: TestClient,
) -> None:
    assert _register(gated_client).status_code == 200

    assert _register(gated_client).status_code == 403
    assert _register(gated_client, enrollment_token="wrong").status_code == 403
    assert (
        _register(gated_client, enrollment_token=ENROLLMENT_TOKEN).status_code == 200
    )


def test_removing_a_passkey_requires_the_enrollment_token(
    gated_client: TestClient,
) -> None:
    assert _register(gated_client).status_code == 200
    credentials = gated_client.get(
        "/api/v1/webauthn/credentials", headers=_headers()
    ).json()
    credential_id = credentials[0]["id"]
    path = f"/api/v1/webauthn/credentials/{credential_id}"

    denied = gated_client.delete(path, headers=_headers())
    allowed = gated_client.delete(
        path, headers=_headers(ENROLLMENT_TOKEN)
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200


class _CountResult:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class _FakeSession:
    def __init__(self, count: int) -> None:
        self._count = count

    def execute(self, *_args, **_kwargs) -> _CountResult:
        return _CountResult(self._count)


def _request(settings: Settings) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                allow_unauthenticated_api_for_tests=False,
            )
        ),
        headers={},
    )


def test_enrollment_fails_closed_without_a_configured_token() -> None:
    settings = Settings(_env_file=None, environment="production")
    with pytest.raises(HTTPException) as excinfo:
        require_enrollment_token(_request(settings), db=_FakeSession(1))
    assert excinfo.value.status_code == 500


def test_enrollment_token_is_required_when_configured() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        enrollment_token=ENROLLMENT_TOKEN,
    )
    with pytest.raises(HTTPException) as excinfo:
        require_enrollment_token(_request(settings), db=_FakeSession(1))
    assert excinfo.value.status_code == 403


def test_bootstrap_is_allowed_even_without_a_configured_token() -> None:
    settings = Settings(_env_file=None, environment="production")
    require_enrollment_token(_request(settings), db=_FakeSession(0))
