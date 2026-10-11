"""ASGI entrypoint.

Run with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000

or use the factory directly::

    uvicorn app.factory:create_app --factory
"""

from __future__ import annotations

from app.factory import create_app

app = create_app()
