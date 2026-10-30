"""Tests for the ASGI request-body size limit."""

from __future__ import annotations

import asyncio

from app.core.request_limits import MAX_REQUEST_BODY_BYTES, RequestBodyLimitMiddleware


def test_http_request_with_oversized_content_length_is_rejected(client) -> None:
    response = client.post(
        "/api/v1/devices/enroll",
        content=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413


def test_chunked_request_body_is_bounded_without_content_length() -> None:
    messages = iter(
        [
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"5678", "more_body": False},
        ]
    )
    sent: list[dict] = []
    app_called = False

    async def receive() -> dict:
        return next(messages)

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(_scope, _receive, _send) -> None:
        nonlocal app_called
        app_called = True

    scope = {"type": "http", "headers": [], "method": "POST", "path": "/"}
    asyncio.run(RequestBodyLimitMiddleware(downstream, max_bytes=6)(scope, receive, send))

    assert app_called is False
    assert sent[0]["status"] == 413
