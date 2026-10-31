"""Runtime resolution of the WebAuthn relying-party ID and allowed origins.

Development may leave ``BIO_RP_ID`` at ``auto`` so the RP ID follows the request
host (localhost, a tunnel, a Vercel preview). Deployed environments must pin it
to their real WebAuthn domain. Allowed origins are the configured ones plus the
current host and the Android app origin(s) taken from the Digital Asset Links
data; the cleartext development origin is only added while developing.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi import Request

from app import static_assets
from app.config import AUTO_RP_ID, DEFAULT_RP_ID, Settings


def request_host(request: Request) -> str:
    """Return the bare host (no scheme/port) the client reached us on."""
    forwarded = request.headers.get("x-forwarded-host")
    host = forwarded or request.headers.get("host", "")
    host = host.split(",")[0].strip()
    if ":" in host:
        host = host.split(":")[0]
    return host.strip().lower()


def resolve_rp_id(request: Request, settings: Settings) -> str:
    configured = (settings.rp_id or "").strip()
    if configured and configured != AUTO_RP_ID:
        return configured
    return request_host(request) or DEFAULT_RP_ID


def _fingerprints_from_document(data: object) -> list[str]:
    entries = data if isinstance(data, list) else [data]
    fingerprints: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        target = entry.get("target")
        if not isinstance(target, dict):
            continue
        values = target.get("sha256_cert_fingerprints") or []
        if isinstance(values, list):
            fingerprints.extend(str(value) for value in values)
    return fingerprints


def asset_links_fingerprints(settings: Settings) -> list[str]:
    """SHA-256 fingerprints from the configured file, else the bundled defaults."""
    path = settings.asset_links_path
    if path:
        candidate = Path(path)
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if data is not None:
                fingerprints = _fingerprints_from_document(data)
                if fingerprints:
                    return fingerprints
    return list(static_assets.ANDROID_SHA256_FINGERPRINTS)


def android_origins(settings: Settings) -> list[str]:
    """Android WebAuthn origins derived from the app signing fingerprints."""
    origins: set[str] = set()
    for fingerprint in asset_links_fingerprints(settings):
        try:
            raw = bytes.fromhex(fingerprint.replace(":", ""))
        except ValueError:
            continue
        encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        origins.add(f"android:apk-key-hash:{encoded}")
    return sorted(origins)


def allowed_origins_for(settings: Settings, rp_id: str) -> list[str]:
    origins = set(settings.allowed_origins)
    if rp_id:
        origins.add(f"https://{rp_id}")
        if settings.is_development:
            origins.add(f"http://{rp_id}:8000")
    origins.update(android_origins(settings))
    return sorted(origin for origin in origins if origin)


def resolve_allowed_origins(request: Request, settings: Settings) -> list[str]:
    return allowed_origins_for(settings, resolve_rp_id(request, settings))
