"""Outbound WebSocket endpoint for PC agents.

Agents open a normal outbound TLS WebSocket (no inbound port required). The
connection is authenticated with the same signed device credential used for
REST calls. The server pushes signed envelopes; the agent verifies them
independently before acting.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import resolve_device
from app.models import AuthRequest, AuthRequestStatus, Device, DeviceStatus, utcnow
from app.services.requests import build_envelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/agent")
async def agent_socket(websocket: WebSocket) -> None:
    app = websocket.app
    settings = app.state.settings
    server_key = app.state.server_signing_key
    manager = app.state.connection_manager
    session_factory = app.state.session_factory

    header = websocket.headers.get("authorization", "")
    session = session_factory()
    device: Device | None = None
    try:
        try:
            device = resolve_device(session, header, settings, server_key)
        except Exception:  # noqa: BLE001 - reject unauthenticated sockets
            await websocket.close(code=4401)
            return

        await websocket.accept()
        device.last_seen_at = utcnow()
        session.commit()
        await manager.connect(device.id, websocket)

        if device.status == DeviceStatus.active:
            pending = session.query(AuthRequest).filter(
                AuthRequest.pc_id == device.id,
                AuthRequest.status.in_(
                    [AuthRequestStatus.pending, AuthRequestStatus.delivered]
                ),
            ).all()
            for req in pending:
                await websocket.send_json(
                    {"type": "auth_request", "envelope": build_envelope(server_key, req)}
                )

        await websocket.send_json({"type": "hello", "device_id": device.id, "status": "connected"})

        while True:
            message = await websocket.receive_text()
            if message == "ping":
                device.last_seen_at = utcnow()
                session.commit()
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        if device is not None:
            await manager.disconnect(device.id, websocket)
        session.close()
