"""Aggregates the versioned API routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    accounts,
    auth_requests,
    devices,
    pairing,
    server_info,
    webauthn,
    ws,
)

api_router = APIRouter()
api_router.include_router(accounts.router)
api_router.include_router(webauthn.router)
api_router.include_router(devices.router)
api_router.include_router(pairing.router)
api_router.include_router(auth_requests.router)
api_router.include_router(server_info.router)
api_router.include_router(ws.router)
