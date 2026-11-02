"""Well-known endpoints.

Currently serves the Digital Asset Links file so an Android app can be
associated with this WebAuthn relying party domain. A bundled default is served
so this works on any host out of the box; override it with
``BIO_ASSET_LINKS_PATH``.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app import static_assets

router = APIRouter(tags=["well-known"])


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def asset_links(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    configured = settings.asset_links_path
    if configured:
        path = Path(configured)
        if path.is_file():
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise HTTPException(
                    status_code=500, detail="Asset links unavailable"
                ) from exc
            return JSONResponse(content=content)
    return JSONResponse(content=static_assets.asset_links_document())
