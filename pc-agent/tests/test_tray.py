"""Regression tests for the tray QR rendering.

The tray used to call ``segno.QRCode.png_data``, which does not exist in segno
1.x, so every link attempt failed with "(Could not render QR code.)".
"""

from __future__ import annotations

from biounlock_agent.tray import render_qr_image

PAYLOAD = '{"type":"biounlock-pairing","version":1}'


def test_render_qr_image_returns_grayscale_square():
    image = render_qr_image(PAYLOAD)
    assert image is not None
    assert image.mode == "L"
    width, height = image.size
    assert width == height > 0
