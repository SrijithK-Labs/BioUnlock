"""Tests for the Windows service pre-login session gating."""

from __future__ import annotations

from biounlock_agent.service import session_has_signed_in_user


def test_active_session_with_user_is_detected():
    assert session_has_signed_in_user(0, "alice", active=0) is True


def test_active_session_without_user_is_not_detected():
    assert session_has_signed_in_user(0, "", active=0) is False
    assert session_has_signed_in_user(0, None, active=0) is False


def test_inactive_session_is_ignored():
    assert session_has_signed_in_user(4, "alice", active=0) is False


def test_disconnected_session_is_ignored():
    # WTSDisconnected==4 must not count as a signed-in interactive session.
    assert session_has_signed_in_user(4, "alice", active=0) is False
