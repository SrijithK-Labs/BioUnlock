"""HTTP client for the BioUnlock backend (agent-facing endpoints).

All authenticated calls use the signed device credential
``Authorization: Biounlock <device_id>.<expiry>.<sig>``. TLS verification is
never disabled by this client.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from biounlock_agent.crypto import Ed25519PrivateKey, make_device_auth_header, public_key_pem
from biounlock_agent.errors import ApiError, NotEnrolledError

DEFAULT_TIMEOUT_SECONDS = 15.0
DEVICE_AUTH_TTL_SECONDS = 300
API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class ServerInfo:
    name: str
    version: str
    rp_id: str
    server_signing_key_fingerprint: str
    environment: str


@dataclass(frozen=True)
class Enrollment:
    device_id: str
    device_name: str
    pairing_code: str
    qr_payload: str
    expires_at: str
    server_signing_public_key: str
    server_signing_key_fingerprint: str


@dataclass(frozen=True)
class Heartbeat:
    server_time: str
    heartbeat_interval_seconds: int
    paired: bool
    pending_requests: int


class ApiClient:
    def __init__(
        self,
        server_url: str,
        *,
        private_key: Ed25519PrivateKey | None = None,
        device_id: str | None = None,
        server_fingerprint: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        verify: bool = True,
        clock=time.time,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self._private_key = private_key
        self._device_id = device_id
        self._server_fingerprint = server_fingerprint
        self._clock = clock
        self._client = httpx.Client(
            base_url=self.server_url + API_PREFIX,
            timeout=timeout,
            transport=transport,
            verify=verify,
            headers={"Accept": "application/json"},
        )

    # --- lifecycle -----------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def set_identity(
        self,
        *,
        private_key: Ed25519PrivateKey | None = None,
        device_id: str | None = None,
        server_fingerprint: str | None = None,
    ) -> None:
        if private_key is not None:
            self._private_key = private_key
        if device_id is not None:
            self._device_id = device_id
        if server_fingerprint is not None:
            self._server_fingerprint = server_fingerprint

    # --- internals -----------------------------------------------------

    def authorization_header(self) -> str:
        """Build a fresh signed device credential for the WebSocket handshake."""
        return self._device_auth_header()["Authorization"]

    def _device_auth_header(self) -> dict[str, str]:
        if not (self._private_key and self._device_id and self._server_fingerprint):
            raise NotEnrolledError("device is not enrolled")
        expiry = int(self._clock()) + DEVICE_AUTH_TTL_SECONDS
        header = make_device_auth_header(
            self._private_key,
            device_id=self._device_id,
            server_fingerprint=self._server_fingerprint,
            expiry=expiry,
        )
        return {"Authorization": header}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        code = "http_error"
        message = response.text or f"HTTP {response.status_code}"
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                code = str(error.get("code") or code)
                message = str(error.get("message") or message)
            elif isinstance(body, dict) and "detail" in body:
                message = str(body["detail"])
        except ValueError:
            pass
        raise ApiError(message, code=code, status_code=response.status_code)

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = False,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = self._device_auth_header() if auth else {}
        try:
            response = self._client.request(method, path, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise ApiError(f"network error: {exc}", code="network_error") from exc
        self._raise_for_status(response)
        return response

    # --- endpoints -----------------------------------------------------

    def server_info(self) -> ServerInfo:
        data = self._request("GET", "/server/info").json()
        return ServerInfo(
            name=data["name"],
            version=data["version"],
            rp_id=data["rp_id"],
            server_signing_key_fingerprint=data["server_signing_key_fingerprint"],
            environment=data["environment"],
        )

    def enroll(self, *, name: str, platform: str = "windows") -> Enrollment:
        if self._private_key is None:
            raise NotEnrolledError("no device identity to enroll")
        payload = {"name": name, "platform": platform, "public_key": public_key_pem(self._private_key)}
        data = self._request("POST", "/devices/enroll", json=payload).json()
        return Enrollment(
            device_id=data["device_id"],
            device_name=data["device_name"],
            pairing_code=data["pairing_code"],
            qr_payload=data["qr_payload"],
            expires_at=data["expires_at"],
            server_signing_public_key=data["server_signing_public_key"],
            server_signing_key_fingerprint=data["server_signing_key_fingerprint"],
        )

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/devices/me", auth=True).json()

    def heartbeat(self) -> Heartbeat:
        data = self._request("POST", "/devices/me/heartbeat", auth=True).json()
        return Heartbeat(
            server_time=data["server_time"],
            heartbeat_interval_seconds=int(data["heartbeat_interval_seconds"]),
            paired=bool(data["paired"]),
            pending_requests=int(data.get("pending_requests", 0)),
        )

    def inbox(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/devices/me/inbox", auth=True).json()
        requests = data.get("requests", []) if isinstance(data, dict) else []
        return list(requests)

    def ack(
        self,
        request_id: str,
        *,
        status: str,
        reason_code: str | None = None,
        observed_at: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": status}
        if reason_code is not None:
            payload["reason_code"] = reason_code
        if observed_at is not None:
            payload["observed_at"] = observed_at
        return self._request("POST", f"/requests/{request_id}/ack", auth=True, json=payload).json()
