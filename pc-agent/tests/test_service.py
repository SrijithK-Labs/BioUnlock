"""Tests for the pre-login session gating."""

from __future__ import annotations

import asyncio
import logging
import types

import pytest

from biounlock_agent import service
from biounlock_agent.service import session_has_signed_in_user


class _FakeWin32TS:
    """Minimal ``win32ts`` stand-in.

    Deliberately rejects any argument: some pywin32 builds raise error 87 for
    the documented ``(server, reserved, version)`` call, which made the probe
    fail on every boot.
    """

    WTS_CURRENT_SERVER_HANDLE = 0
    WTSUserName = 5

    def __init__(self, sessions, users=None, error=None):
        self.sessions = sessions
        self.users = users or {}
        self.error = error
        self.calls = 0

    def WTSEnumerateSessions(self, *args):
        self.calls += 1
        if args:
            raise AssertionError("WTSEnumerateSessions must be called without arguments")
        if self.error is not None:
            raise self.error
        return self.sessions

    def WTSQuerySessionInformation(self, server, session_id, info):
        return self.users.get(session_id, "")


def _use_fake_ts(monkeypatch: pytest.MonkeyPatch, fake: _FakeWin32TS) -> None:
    monkeypatch.setattr(service, "HAS_WIN32TS", True)
    monkeypatch.setattr(service, "win32ts", fake)
    monkeypatch.setattr(service, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(service, "_probe_failure", None)


def _boot_sessions() -> list:
    return [
        {"SessionId": 0, "State": 4, "WinStationName": "Services"},
        {"SessionId": 1, "State": 0, "WinStationName": "Console"},
    ]


def test_session_with_user_is_detected():
    assert session_has_signed_in_user(0, "alice") is True


def test_session_without_user_is_not_detected():
    assert session_has_signed_in_user(0, "") is False
    assert session_has_signed_in_user(0, None) is False


def test_locked_or_disconnected_session_still_counts_as_signed_in():
    # A locked desktop and a disconnected RDP session both keep the tray and its
    # agent alive, so the startup agent must stay out of the way (running two
    # agents against one device key races on acknowledgements).
    assert session_has_signed_in_user(4, "alice") is True


def test_listen_session_is_ignored():
    assert session_has_signed_in_user(6, "alice") is False


def test_probe_serves_at_the_sign_in_screen(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeWin32TS(_boot_sessions(), users={0: "", 1: ""})
    _use_fake_ts(monkeypatch, fake)

    assert service.interactive_user_present() is False
    assert fake.calls == 1


def test_probe_steps_aside_once_a_user_is_signed_in(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeWin32TS(_boot_sessions(), users={0: "", 1: "alice"})
    _use_fake_ts(monkeypatch, fake)

    assert service.interactive_user_present() is True


def test_probe_failure_fails_safe_and_is_logged_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    fake = _FakeWin32TS([], error=OSError(87, "The parameter is incorrect"))
    _use_fake_ts(monkeypatch, fake)

    with caplog.at_level(logging.WARNING, logger="biounlock_agent.service"):
        assert service.interactive_user_present() is True
        assert service.interactive_user_present() is True

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "assuming a user is signed in" in warnings[0].getMessage()
    assert "The parameter is incorrect" in warnings[0].getMessage()


def test_probe_logs_again_after_success_and_a_new_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    fake = _FakeWin32TS(_boot_sessions(), users={0: "", 1: ""})
    fake.error = OSError(87, "The parameter is incorrect")
    _use_fake_ts(monkeypatch, fake)

    with caplog.at_level(logging.WARNING, logger="biounlock_agent.service"):
        assert service.interactive_user_present() is True
        fake.error = None
        assert service.interactive_user_present() is False
        fake.error = OSError(87, "The parameter is incorrect")
        assert service.interactive_user_present() is True

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2


def test_source_service_install_is_disabled(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(service, "HAS_PYWIN32", True)

    assert service.main() == 1
    assert "Source-based Windows service installation is disabled" in capsys.readouterr().err


def test_watcher_stops_the_agent_on_sign_in(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "interactive_user_present", lambda: True)
    stop = asyncio.Event()
    calls: list = []

    class _Loop:
        def call_soon_threadsafe(self, callback) -> None:
            calls.append(callback)

    service._stop_agent_at_sign_in(stop, _Loop())

    assert len(calls) == 1
    calls[0]()
    assert stop.is_set()
