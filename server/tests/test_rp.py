"""Tests for runtime RP ID / allowed-origin resolution.

These keep the server usable on any host (e.g. a Vercel domain) with no config:
the RP ID comes from the request host and the Android origin from the asset
links fingerprints.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app import static_assets
from app.config import AUTO_RP_ID, Settings
from app.core.rp import allowed_origins_for, android_origins, resolve_rp_id

DEBUG_FINGERPRINT = static_assets.ANDROID_SHA256_FINGERPRINTS[0]
DEBUG_ANDROID_ORIGIN = "android:apk-key-hash:5DVyir7YN4Fg8vd14Av1I_5Ao1FkP4pMZXdn0638qAI"


def _request(host: str) -> SimpleNamespace:
    return SimpleNamespace(headers={"host": host})


def test_bundled_asset_links_yields_debug_android_origin():
    settings = Settings(_env_file=None)
    assert DEBUG_FINGERPRINT == (
        "E4:35:72:8A:BE:D8:37:81:60:F2:F7:75:E0:0B:F5:23:"
        "FE:40:A3:51:64:3F:8A:4C:65:77:67:D3:AD:FC:A8:02"
    )
    assert android_origins(settings) == [DEBUG_ANDROID_ORIGIN]


def test_android_origins_from_arbitrary_fingerprint(tmp_path):
    path = tmp_path / "assetlinks.json"
    path.write_text(
        json.dumps([{"target": {"sha256_cert_fingerprints": [DEBUG_FINGERPRINT]}}]),
        encoding="utf-8",
    )
    settings = Settings(_env_file=None, asset_links_path=str(path))
    assert android_origins(settings) == [DEBUG_ANDROID_ORIGIN]


def test_rp_id_is_derived_from_host_when_auto():
    settings = Settings(_env_file=None, rp_id=AUTO_RP_ID)
    host = "app.example.com"
    assert resolve_rp_id(_request(host), settings) == host


def test_explicit_rp_id_is_respected():
    settings = Settings(_env_file=None, rp_id="example.com")
    assert resolve_rp_id(_request("other.example.com"), settings) == "example.com"


def test_allowed_origins_merge_config_host_and_android():
    settings = Settings(
        _env_file=None,
        rp_id=AUTO_RP_ID,
        allowed_origins=["https://configured.example.com"],
    )
    origins = allowed_origins_for(settings, "app.example.com")

    assert "https://configured.example.com" in origins
    assert "https://app.example.com" in origins
    assert DEBUG_ANDROID_ORIGIN in origins
