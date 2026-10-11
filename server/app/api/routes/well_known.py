"""Well-known endpoints.

Currently serves the Digital Asset Links file so an Android app can be
associated with this WebAuthn relying party domain. The file content is
supplied out-of-band via ``BIO_ASSET_LINKS_PATH`` and never embedded in code.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["well-known"])


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def asset_links(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    configured = settings.asset_links_path
    if not configured:
        raise HTTPException(status_code=404, detail="Not found")
    path = Path(configured)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Asset links unavailable") from exc
    return JSONResponse(content=content)
