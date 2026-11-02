"""Bundled Android app-association data.

Stored as Python constants (not a data file) so it is always included in
serverless bundles. Override at runtime by pointing ``BIO_ASSET_LINKS_PATH`` at
your own Digital Asset Links JSON.
"""

from __future__ import annotations

ANDROID_PACKAGE_NAME = "com.biounlock.biounlock_mobile"

# SHA-256 certificate fingerprints of the Android app signing certificate(s).
ANDROID_SHA256_FINGERPRINTS = [
    "30:EB:14:BE:00:34:AA:EC:BA:49:D4:E4:3D:73:6F:BE:"
    "3B:C0:00:A1:49:5A:85:93:76:C4:E6:E6:26:DA:40:8C",
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
