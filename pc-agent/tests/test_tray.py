"""Regression tests for the tray QR rendering and pairing watcher.

The tray used to call ``segno.QRCode.png_data``, which does not exist in segno
1.x, so every link attempt failed with "(Could not render QR code.)". It also
only watched for a phone-side pairing for a few minutes after "Link this PC",
so a pairing that landed later was missed until the app was restarted.
"""

from __future__ import annotations

from biounlock_agent.tray import render_qr_image, watch_for_pairing

PAYLOAD = '{"type":"biounlock-pairing","version":1}'


def test_render_qr_image_returns_grayscale_square():
    image = render_qr_image(PAYLOAD)
    assert image is not None
    assert image.mode == "L"
    width, height = image.size
    assert width == height > 0


class _FakeConfig:
    def __init__(self, *, enrolled: bool = True, paired: bool = False) -> None:
        self.is_enrolled = enrolled
        self.is_paired = paired


class _FakeHeartbeat:
    def __init__(self, paired: bool) -> None:
        self.paired = paired


class _FakeAgent:
    def __init__(self, config: _FakeConfig, results: list[bool]) -> None:
        self.config = config
        self._results = list(results)
        self.calls = 0

    def refresh_pairing(self) -> _FakeHeartbeat:
        self.calls += 1
        paired = self._results.pop(0) if self._results else False
        return _FakeHeartbeat(paired)


class _FlakyAgent:
    def __init__(self, config: _FakeConfig) -> None:
        self.config = config
        self.calls = 0

    def refresh_pairing(self) -> _FakeHeartbeat:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary network error")
        return _FakeHeartbeat(True)


def test_watch_for_pairing_stops_once_paired():
    agent = _FakeAgent(_FakeConfig(), [False, False, True])
    events: list[str] = []
    sleeps: list[float] = []

    watch_for_pairing(
        agent,
        closing=lambda: False,
        on_paired=lambda: events.append("paired"),
        sleep=sleeps.append,
    )

    assert events == ["paired"]
    assert agent.calls == 3
    assert sleeps  # it waited between polls


def test_watch_for_pairing_returns_when_already_paired():
    agent = _FakeAgent(_FakeConfig(paired=True), [True])
    events: list[str] = []

    watch_for_pairing(agent, closing=lambda: False, on_paired=lambda: events.append("paired"))

    assert events == []
    assert agent.calls == 0


def test_watch_for_pairing_stops_when_not_enrolled():
    agent = _FakeAgent(_FakeConfig(enrolled=False), [False])
    events: list[str] = []

    watch_for_pairing(agent, closing=lambda: False, on_paired=lambda: events.append("paired"))

    assert events == []
    assert agent.calls == 0


def test_watch_for_pairing_stops_when_closing():
    agent = _FakeAgent(_FakeConfig(), [True])

    watch_for_pairing(agent, closing=lambda: True, on_paired=lambda: None)

    assert agent.calls == 0


def test_watch_for_pairing_survives_transient_errors():
    agent = _FlakyAgent(_FakeConfig())
    events: list[str] = []

    watch_for_pairing(
        agent,
        closing=lambda: False,
        on_paired=lambda: events.append("paired"),
        sleep=lambda _seconds: None,
    )

    assert events == ["paired"]
    assert agent.calls == 2

