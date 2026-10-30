"""Tests for the delivery channel's keepalive and stale-socket handling.

A WebSocket that has gone half-open (sleep/resume, Wi-Fi change, NAT timeout)
still reports itself connected. The agent used to trust that flag and skip the
REST inbox, so phone requests were silently lost until the app was restarted.
"""

from __future__ import annotations

import asyncio

import pytest

from biounlock_agent import delivery


class _CountingApi:
    def __init__(self) -> None:
        self.calls = 0

    def inbox(self) -> list[dict]:
        self.calls += 1
        return []


def _manager(api: _CountingApi | None = None) -> delivery.DeliveryManager:
    return delivery.DeliveryManager(
        server_url="https://example.test",
        auth_header_provider=lambda: "test",
        on_envelope=lambda envelope: None,
        api=api or _CountingApi(),  # type: ignore[arg-type]
    )


def test_websocket_url_rejects_public_http():
    with pytest.raises(ValueError, match="HTTP"):
        delivery.ws_url_for("http://example.com")


def test_socket_is_healthy_only_while_traffic_is_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1000.0
    monkeypatch.setattr(delivery.time, "monotonic", lambda: now)
    manager = _manager()

    manager.connected = True
    manager._last_activity = now - delivery.DEFAULT_STALE_AFTER_SECONDS + 1
    assert manager._socket_healthy() is True

    manager._last_activity = now - delivery.DEFAULT_STALE_AFTER_SECONDS
    assert manager._socket_healthy() is False

    manager.connected = False
    manager._last_activity = now
    assert manager._socket_healthy() is False


def test_websocket_is_opened_with_keepalive_pings(monkeypatch: pytest.MonkeyPatch) -> None:
    ws_client = pytest.importorskip("websockets.asyncio.client")
    captured: dict = {}

    async def fake_connect(uri, **kwargs):
        captured["uri"] = uri
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ws_client, "connect", fake_connect)

    asyncio.run(delivery._open_socket("wss://example.test/api/v1/ws/agent", {"Authorization": "x"}))

    assert captured["ping_interval"] == delivery.PING_INTERVAL_SECONDS
    assert captured["ping_timeout"] == delivery.PING_TIMEOUT_SECONDS


def test_rest_fallback_polls_when_the_socket_goes_silent() -> None:
    api = _CountingApi()
    manager = _manager(api)
    manager._rest_interval = 0.01
    manager.connected = True
    manager._last_activity = 0.0  # long ago: the socket reports connected but is silent

    async def run() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(manager._run_rest_fallback(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await task

    asyncio.run(run())

    assert api.calls >= 2


def test_rest_fallback_stays_quiet_while_the_socket_is_healthy() -> None:
    api = _CountingApi()
    manager = _manager(api)
    manager._rest_interval = 0.01
    manager.connected = True
    manager._last_activity = delivery.time.monotonic()

    async def run() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(manager._run_rest_fallback(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await task

    asyncio.run(run())

    assert api.calls == 0
