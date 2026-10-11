"""Tests for Windows credential storage and unlock tickets (DPAPI)."""

from __future__ import annotations

import time

import pytest

from biounlock_agent import unlock

pytestmark = pytest.mark.skipif(
    not unlock.dpapi_available(), reason="Windows DPAPI (pywin32) is not available"
)


def test_credential_roundtrip(home):
    assert unlock.has_windows_credential(home) is False

    unlock.save_windows_credential(home, unlock.WindowsCredential("user", "secret", "DOMAIN"))
    assert unlock.has_windows_credential(home) is True

    cred = unlock.load_windows_credential(home)
    assert (cred.username, cred.password, cred.domain) == ("user", "secret", "DOMAIN")

    unlock.delete_windows_credential(home)
    assert unlock.has_windows_credential(home) is False


def test_load_missing_credential_raises(home):
    with pytest.raises(unlock.NoCredentialEnrolledError):
        unlock.load_windows_credential(home)


def test_empty_username_rejected(home):
    with pytest.raises(unlock.UnlockError):
        unlock.save_windows_credential(home, unlock.WindowsCredential("", "x"))


def test_credential_roundtrip_machine_scope(home):
    unlock.save_windows_credential(
        home, unlock.WindowsCredential("user", "secret", "DOMAIN"), machine=True
    )
    cred = unlock.load_windows_credential(home)
    assert (cred.username, cred.password, cred.domain) == ("user", "secret", "DOMAIN")


def test_ticket_issue_and_read(home):
    now = time.time()
    unlock.issue_unlock_ticket(
        home,
        request_id="req-9",
        credential=unlock.WindowsCredential("u", "p"),
        ttl_seconds=30,
        now=now,
    )
    ticket = unlock.read_unlock_ticket(home, now=now + 5)
    assert ticket is not None
    assert ticket["request_id"] == "req-9"
    assert ticket["password"] == "p"
    assert ticket["expires_at"] == int(now) + 30


def test_ticket_expires(home):
    now = time.time()
    unlock.issue_unlock_ticket(
        home, request_id="r", credential=unlock.WindowsCredential("u", "p"), ttl_seconds=10, now=now
    )
    assert unlock.read_unlock_ticket(home, now=now + 11) is None


def test_ticket_ttl_is_capped(home):
    now = time.time()
    unlock.issue_unlock_ticket(
        home, request_id="r", credential=unlock.WindowsCredential("u", "p"), ttl_seconds=10_000, now=now
    )
    assert unlock.read_unlock_ticket(home, now=now + unlock.MAX_TICKET_TTL_SECONDS + 1) is None


def test_reset_clears_credential_and_ticket(home):
    unlock.save_windows_credential(home, unlock.WindowsCredential("u", "p"))
    unlock.issue_unlock_ticket(home, request_id="r", credential=unlock.WindowsCredential("u", "p"))

    unlock.reset_windows_credential(home)

    assert unlock.has_windows_credential(home) is False
    assert unlock.read_unlock_ticket(home) is None
