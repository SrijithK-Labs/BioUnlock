"""Outbound delivery of signed envelopes to connected PC agents.

The PC agent opens a single outbound WebSocket connection; the server pushes
envelopes. A REST inbox provides an equivalent long-poll fallback. The server
never dials the PC, so no inbound ports are required.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(device_id, set()).add(websocket)

    async def disconnect(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(device_id)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(device_id, None)

    def is_connected(self, device_id: str) -> bool:
        return bool(self._connections.get(device_id))

    def connected_device_ids(self) -> list[str]:
        return list(self._connections.keys())

    async def send_to_device(self, device_id: str, payload: dict[str, Any]) -> bool:
        async with self._lock:
            sockets = list(self._connections.get(device_id, set()))
        if not sockets:
            return False
        delivered = False
        for socket in sockets:
            try:
                await socket.send_json(payload)
                delivered = True
            except Exception:  # noqa: BLE001 - drop broken sockets
                await self.disconnect(device_id, socket)
        return delivered

    async def close_device(self, device_id: str, code: int = 1000) -> None:
        async with self._lock:
            sockets = list(self._connections.pop(device_id, set()))
        for socket in sockets:
            try:
                await socket.close(code=code)
            except Exception:  # noqa: BLE001
                pass
