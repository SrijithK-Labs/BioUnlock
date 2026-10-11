"""Outbound delivery of signed envelopes.

The agent opens a single outbound WebSocket; the server pushes envelopes. If the
socket is unavailable the agent falls back to polling the REST inbox, so a
blocked WebSocket never stops authentication. No inbound port is required.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

from biounlock_agent.api_client import ApiClient
from biounlock_agent.errors import ApiError

logger = logging.getLogger(__name__)

DEFAULT_KEEPALIVE_SECONDS = 30.0
DEFAULT_REST_INTERVAL_SECONDS = 15.0


def ws_url_for(server_url: str) -> str:
    """Derive the agent WebSocket URL from the configured HTTP(S) server URL."""
    parts = urlsplit(server_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return f"{scheme}://{parts.netloc}/api/v1/ws/agent"


async def _open_socket(uri: str, headers: dict[str, str]):
    """Open a WebSocket across websockets library versions."""
    try:
        from websockets.asyncio.client import connect as connect_new
    except Exception:  # noqa: BLE001 - fall back to the legacy client
        connect_new = None
    if connect_new is not None:
        return await connect_new(uri, additional_headers=headers, open_timeout=15, ping_interval=None)
    import websockets  # type: ignore[import-not-found]

    return await websockets.connect(uri, extra_headers=headers, open_timeout=15, ping_interval=None)


class DeliveryManager:
    """WebSocket push with a REST long-poll fallback."""

    def __init__(
        self,
        *,
        server_url: str,
        auth_header_provider: Callable[[], str],
        on_envelope: Callable[[dict[str, Any]], Any],
        api: ApiClient,
        keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS,
        rest_interval_seconds: float = DEFAULT_REST_INTERVAL_SECONDS,
        on_status_change: Callable[[bool], None] | None = None,
    ) -> None:
        self.server_url = server_url
        self._auth_header_provider = auth_header_provider
        self._on_envelope = on_envelope
        self._api = api
        self._keepalive = keepalive_seconds
        self._rest_interval = rest_interval_seconds
        self._on_status_change = on_status_change
        self.connected = False

    def _set_connected(self, value: bool) -> None:
        if self.connected == value:
            return
        self.connected = value
        if self._on_status_change is not None:
            with suppress(Exception):
                self._on_status_change(value)

    async def run(self, stop: asyncio.Event) -> None:
        await asyncio.gather(self._run_websocket(stop), self._run_rest_fallback(stop))

    async def _run_websocket(self, stop: asyncio.Event) -> None:
        backoff = 1.0
        while not stop.is_set():
            try:
                await self._websocket_session(stop)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on any failure
                logger.warning("WebSocket delivery error: %s", exc)
            finally:
                self._set_connected(False)
            if stop.is_set():
                break
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            backoff = min(backoff * 2, 30.0)

    async def _websocket_session(self, stop: asyncio.Event) -> None:
        headers = {"Authorization": self._auth_header_provider()}
        socket = await _open_socket(ws_url_for(self.server_url), headers)
        self._set_connected(True)
        keepalive = asyncio.create_task(self._keepalive_loop(socket, stop))
        try:
            while not stop.is_set():
                recv_task = asyncio.create_task(socket.recv())
                stop_task = asyncio.create_task(stop.wait())
                done, pending = await asyncio.wait(
                    {recv_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await asyncio.gather(*pending)
                if stop_task in done:
                    break
                if recv_task in done:
                    try:
                        raw = recv_task.result()
                    except Exception:  # noqa: BLE001 - closed/errored socket
                        break
                    if raw is None:
                        break
                    await self._dispatch(raw)
        finally:
            keepalive.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await keepalive
            with suppress(Exception):
                await socket.close()

    async def _keepalive_loop(self, socket: Any, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._keepalive)
                return
            except TimeoutError:
                pass
            try:
                await socket.send("ping")
            except Exception:  # noqa: BLE001 - socket is gone
                return

    async def _dispatch(self, raw: Any) -> None:
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = bytes(raw).decode("utf-8")
            except UnicodeDecodeError:
                return
        try:
            message = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(message, dict):
            return
        if message.get("type") == "auth_request":
            envelope = message.get("envelope")
            if isinstance(envelope, dict):
                await asyncio.to_thread(self._on_envelope, envelope)

    async def _run_rest_fallback(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._rest_interval)
                return
            except TimeoutError:
                pass
            if self.connected:
                continue
            try:
                envelopes = await asyncio.to_thread(self._api.inbox)
            except ApiError as exc:
                logger.warning("Inbox poll failed: %s", exc)
                continue
            for envelope in envelopes:
                await asyncio.to_thread(self._on_envelope, envelope)
