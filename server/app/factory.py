"""Application factory for the BioUnlock backend."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.api.routes import health, well_known
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.rate_limit import RateLimiter
from app.core.request_limits import RequestBodyLimitMiddleware
from app.core.security import SIGNING_KEY_ENV, SigningKeyError
from app.core.server_identity import load_or_create_signing_key
from app.database import create_engine_for_url, make_session_factory
from app.logging import configure_logging
from app.services.delivery import ConnectionManager
from app.services.sweeper import sweeper_loop

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    allow_unauthenticated_api_for_tests: bool = False,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    test_harness = (
        settings.environment.lower() == "test"
        and allow_unauthenticated_api_for_tests
    )
    if not settings.rate_limit_enabled and not test_harness:
        raise ValueError("Rate limiting cannot be disabled outside the explicit test harness.")
    require_external_signing_key = not settings.is_development and not test_harness
    if require_external_signing_key and not os.environ.get(SIGNING_KEY_ENV):
        raise SigningKeyError(f"{SIGNING_KEY_ENV} is required outside development and tests.")

    engine = create_engine_for_url(settings.database_url)
    session_factory = make_session_factory(engine)
    server_key = load_or_create_signing_key(
        session_factory, require_external=require_external_signing_key
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(sweeper_loop(session_factory))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            engine.dispose()

    docs_enabled = settings.is_development
    app = FastAPI(
        title="BioUnlock API",
        version=__version__,
        description="Experimental single-owner remote authentication backend for BioUnlock.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.state.settings = settings
    app.state.allow_unauthenticated_api_for_tests = test_harness
    app.state.session_factory = session_factory
    app.state.engine = engine
    app.state.server_signing_key = server_key
    app.state.rate_limiter = RateLimiter(settings.rate_limit_enabled)
    app.state.connection_manager = ConnectionManager()

    register_error_handlers(app)
    app.add_middleware(
        RequestBodyLimitMiddleware,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health is available both at the root (for infra probes) and versioned.
    app.include_router(health.router)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(well_known.router)
    app.include_router(api_router, prefix="/api/v1")

    return app
