"""Tests for the pre-login session gating."""

from __future__ import annotations

import asyncio

import pytest

from biounlock_agent import service
from biounlock_agent.service import session_has_signed_in_user


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
