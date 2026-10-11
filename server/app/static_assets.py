"""Bundled Android app-association data.

Stored as Python constants (not a data file) so it is always included in
serverless bundles. Override at runtime by pointing ``BIO_ASSET_LINKS_PATH`` at
your own Digital Asset Links JSON.
"""

from __future__ import annotations

ANDROID_PACKAGE_NAME = "com.biounlock.biounlock_mobile"

# SHA-256 certificate fingerprints of the Android app signing certificate(s).
ANDROID_SHA256_FINGERPRINTS = [
    "E4:35:72:8A:BE:D8:37:81:60:F2:F7:75:E0:0B:F5:23:"
    "FE:40:A3:51:64:3F:8A:4C:65:77:67:D3:AD:FC:A8:02",
]


def asset_links_document() -> list[dict]:
    """The Digital Asset Links document served at ``/.well-known/assetlinks.json``."""
    return [
        {
            "relation": [
                "delegate_permission/common.handle_all_urls",
                "delegate_permission/common.get_login_creds",
            ],
            "target": {
                "namespace": "android_app",
                "package_name": ANDROID_PACKAGE_NAME,
                "sha256_cert_fingerprints": list(ANDROID_SHA256_FINGERPRINTS),
            },
        }
    ]
