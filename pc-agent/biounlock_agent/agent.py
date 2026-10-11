"""Agent orchestration: enrollment, pairing, delivery and verification.

The :class:`Agent` ties together the device identity, the pinned server key, the
API client, the verifier, and outbound delivery. It is intentionally
framework-free so it can be driven by the console entrypoint, the GUI, or a
Windows service.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from biounlock_agent import unlock
from biounlock_agent.api_client import ApiClient, Enrollment, Heartbeat
from biounlock_agent.config import (
    DEVICE_KEY_NAME,
    REPLAY_FILENAME,
    AgentConfig,
    ConfigStore,
    default_device_name,
    default_shared_home,
)
from biounlock_agent.crypto import (
    Ed25519PrivateKey,
    generate_identity,
    private_key_from_pem,
    private_key_to_pem,
)
from biounlock_agent.delivery import DeliveryManager
from biounlock_agent.errors import AgentError, ApiError, EnvelopeVerificationError, NotEnrolledError
from biounlock_agent.replay import ReplayStore
from biounlock_agent.storage import SecretStore, default_secret_store
from biounlock_agent.verifier import VerifiedEnvelope, verify_envelope

logger = logging.getLogger(__name__)

# Envelope failures that are authentically about this PC (signature + PC binding
# verified) and therefore safe to report back as a rejection.
ACKABLE_REJECTION_REASONS = frozenset(
    {"expired", "not_yet_valid", "unsupported_operation"}
)


@dataclass(frozen=True)
class ProcessedEnvelope:
    request_id: str
    outcome: str  # "verified" | "rejected" | "dropped"
    reason_code: str | None = None


@dataclass(frozen=True)
class AgentStatus:
    enrolled: bool
    paired: bool
    device_id: str | None
    device_name: str
    server_url: str | None
    account_email: str | None
    connected: bool
    processed_count: int
    credential_enrolled: bool
    last_error: str | None


class Agent:
    def __init__(
        self,
        *,
        home: Path | None = None,
        config_store: ConfigStore | None = None,
        secret_store: SecretStore | None = None,
        replay_store: ReplayStore | None = None,
        api_factory: Callable[..., ApiClient] | None = None,
        clock: Callable[[], float] = time.time,
        unlock_dir: Path | None = None,
    ) -> None:
        self.config_store = config_store or ConfigStore(home)
        ensure_home = getattr(self.config_store, "ensure_home", None)
        if callable(ensure_home):
            ensure_home()
        self.secret_store = secret_store or default_secret_store(self.config_store.home)
        self.replay_store = replay_store or ReplayStore(self.config_store.home / REPLAY_FILENAME)
        self.config = self.config_store.load()
        self.unlock_dir = Path(unlock_dir) if unlock_dir is not None else default_shared_home()
        self._clock = clock
        self._api_factory = api_factory or (lambda **kwargs: ApiClient(**kwargs))
        self._api: ApiClient | None = None
        self._identity: Ed25519PrivateKey | None = None
        self._stop = asyncio.Event()
        self._connected = False
        self.processed_count = 0
        self.last_error: str | None = None

    # --- identity ------------------------------------------------------

    def load_or_create_identity(self) -> Ed25519PrivateKey:
        raw = self.secret_store.get(DEVICE_KEY_NAME)
        if raw is not None:
            self._identity = private_key_from_pem(raw)
        else:
            self._identity = generate_identity()
            self.secret_store.set(DEVICE_KEY_NAME, private_key_to_pem(self._identity))
        return self._identity

    @property
    def identity(self) -> Ed25519PrivateKey | None:
        return self._identity

    # --- api -----------------------------------------------------------

    def _ensure_api(self) -> ApiClient:
        if not self.config.is_enrolled:
            raise NotEnrolledError("agent is not enrolled with a server")
        if self._api is None:
            identity = self.load_or_create_identity()
            self._api = self._api_factory(
                server_url=self.config.server_url,
                private_key=identity,
                device_id=self.config.device_id,
                server_fingerprint=self.config.server_signing_key_fingerprint,
            )
        return self._api

    def _reset_api(self) -> None:
        if self._api is not None:
            self._api.close()
            self._api = None

    # --- enrollment / pairing -----------------------------------------

    def enroll(self, server_url: str, *, device_name: str | None = None) -> Enrollment:
        """Enroll this PC and pin the server signing key (trust on first use)."""
        identity = self.load_or_create_identity()
        name = (device_name or self.config.device_name or default_device_name()).strip() or default_device_name()
        client = self._api_factory(server_url=server_url, private_key=identity)
        try:
            info = client.server_info()
            enrollment = client.enroll(name=name, platform=self.config.platform)
        finally:
            client.close()

        if info.server_signing_key_fingerprint != enrollment.server_signing_key_fingerprint:
            raise AgentError(
                "server information changed during enrollment; refusing to pin an inconsistent key"
            )

        self.config = AgentConfig(
            server_url=server_url.rstrip("/"),
            device_id=enrollment.device_id,
            device_name=enrollment.device_name,
            platform=self.config.platform or "windows",
            server_signing_public_key=enrollment.server_signing_public_key,
            server_signing_key_fingerprint=enrollment.server_signing_key_fingerprint,
            enrolled_at=datetime.now(UTC),
            paired=False,
        )
        self.config_store.save(self.config)
        self._reset_api()
        return enrollment

    def refresh_pairing(self) -> Heartbeat:
        """Heartbeat the server and persist pairing state."""
        api = self._ensure_api()
        heartbeat = api.heartbeat()
        changed = False
        if heartbeat.paired and not self.config.paired:
            self.config.paired = True
            self.config.paired_at = datetime.now(UTC)
            changed = True
        if heartbeat.account_email and heartbeat.account_email != self.config.account_email:
            self.config.account_email = heartbeat.account_email
            changed = True
        if changed:
            self.config_store.save(self.config)
        return heartbeat

    async def wait_for_pairing(self, *, timeout: float | None = None, interval: float = 3.0) -> bool:
        deadline = None if timeout is None else self._clock() + timeout
        while not self._stop.is_set():
            try:
                if self.refresh_pairing().paired:
                    return True
            except (ApiError, NotEnrolledError) as exc:
                self.last_error = str(exc)
            if deadline is not None and self._clock() >= deadline:
                return False
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                return self.config.paired
            except TimeoutError:
                pass
        return self.config.paired

    # --- envelope handling --------------------------------------------

    def handle_envelope(self, envelope: object) -> ProcessedEnvelope:
        """Verify and acknowledge a single delivered envelope."""
        request_id = ""
        if isinstance(envelope, dict):
            value = envelope.get("request_id")
            if isinstance(value, str):
                request_id = value

        if not self.config.is_paired:
            logger.info("Ignoring envelope: PC is not paired")
            return ProcessedEnvelope(request_id, "dropped", "not_paired")

        try:
            verified = verify_envelope(
                envelope,
                pinned_public_key_pem=self.config.server_signing_public_key or "",
                pinned_fingerprint=self.config.server_signing_key_fingerprint or "",
                device_id=self.config.device_id or "",
                now=int(self._clock()),
                replay_store=self.replay_store,
            )
        except EnvelopeVerificationError as exc:
            if exc.reason_code in ACKABLE_REJECTION_REASONS and request_id:
                self._ack(request_id, status="rejected", reason_code=exc.reason_code)
                return ProcessedEnvelope(request_id, "rejected", exc.reason_code)
            logger.warning("Dropped envelope (%s)", exc.reason_code)
            return ProcessedEnvelope(request_id, "dropped", exc.reason_code)

        self._ack(verified.request_id, status="verified")
        self.processed_count += 1
        self._issue_unlock_ticket(verified)
        logger.info(
            "Verified authorization request %s for account %s",
            verified.request_id,
            verified.account_id,
        )
        return ProcessedEnvelope(verified.request_id, "verified")

    def _issue_unlock_ticket(self, verified: VerifiedEnvelope) -> None:
        """Turn a verified remote-unlock into a short-lived ticket for the CP.

        This is best-effort: a missing credential only means the Credential
        Provider has nothing to submit, and is logged rather than raised so the
        request is still acknowledged as ``verified``.
        """
        if verified.operation != "remote_unlock":
            return
        home = self.config_store.home
        try:
            if not unlock.has_windows_credential(home):
                logger.warning(
                    "Verified unlock %s but no Windows credential is enrolled; "
                    "run 'biounlock_agent set-credential' to enable real unlocking.",
                    verified.request_id,
                )
                return
            credential = unlock.load_windows_credential(home)
            unlock.issue_unlock_ticket(
                self.unlock_dir, request_id=verified.request_id, credential=credential
            )
            logger.info("Issued Windows unlock ticket for request %s", verified.request_id)
        except unlock.UnlockError as exc:
            logger.warning("Could not issue unlock ticket for %s: %s", verified.request_id, exc)


    def _ack(self, request_id: str, *, status: str, reason_code: str | None = None) -> None:
        try:
            api = self._ensure_api()
            api.ack(
                request_id,
                status=status,
                reason_code=reason_code,
                observed_at=int(self._clock()),
            )
        except (ApiError, NotEnrolledError) as exc:
            self.last_error = str(exc)
            logger.warning("Failed to report %s for %s: %s", status, request_id, exc)

    # --- run loop ------------------------------------------------------

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or self._stop
        stop.clear()
        self.load_or_create_identity()
        api = self._ensure_api()

        delivery = DeliveryManager(
            server_url=self.config.server_url or "",
            auth_header_provider=api.authorization_header,
            on_envelope=self.handle_envelope,
            api=api,
            on_status_change=self._set_connected,
        )
        try:
            await asyncio.gather(self._heartbeat_loop(stop), delivery.run(stop))
        finally:
            self._connected = False

    def _set_connected(self, value: bool) -> None:
        self._connected = value

    async def _heartbeat_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            interval = 30.0
            try:
                heartbeat = await asyncio.to_thread(self.refresh_pairing)
                interval = float(max(5, heartbeat.heartbeat_interval_seconds))
                self.last_error = None
            except (ApiError, NotEnrolledError) as exc:
                self.last_error = str(exc)
                logger.warning("Heartbeat failed: %s", exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                pass

    # --- lifecycle / status -------------------------------------------

    def unenroll(self) -> None:
        """Forget the server identity and the device private key locally."""
        self.request_stop()
        self._reset_api()
        self.config_store.reset()
        self.secret_store.delete(DEVICE_KEY_NAME)
        self.config = AgentConfig()
        self._identity = None

    def status(self) -> AgentStatus:
        return AgentStatus(
            enrolled=self.config.is_enrolled,
            paired=self.config.is_paired,
            device_id=self.config.device_id,
            device_name=self.config.device_name,
            server_url=self.config.server_url,
            account_email=self.config.account_email,
            connected=self._connected,
            processed_count=self.processed_count,
            credential_enrolled=unlock.has_windows_credential(self.config_store.home),
            last_error=self.last_error,
        )

    def close(self) -> None:
        self._reset_api()
        self.replay_store.close()
