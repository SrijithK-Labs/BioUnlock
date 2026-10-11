"""Vercel serverless entrypoint.

Vercel's Python runtime serves any ASGI ``app`` object it finds in an ``api/``
function. Re-export the FastAPI application so every route is handled here
(see ``vercel.json`` for the catch-all rewrite).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

__all__ = ["app"]
