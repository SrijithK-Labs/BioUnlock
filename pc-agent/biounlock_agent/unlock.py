"""Windows credential storage and short-lived unlock tickets.

This is the agent half of the Windows logon integration (see
``docs/windows-authentication.md``). It is deliberately small so the security
properties are easy to audit:

- The user's Windows credential is stored **only** through Windows DPAPI in
  *current-user* scope (``CryptoProtectData`` without ``LOCAL_MACHINE``). It can
  be decrypted only by the same Windows user on the same machine, and it is
  never written to ``config.json``, never logged, and never transmitted.
- On a verified ``remote_unlock`` the agent mints a **single-use, short-lived
  ticket** next to the credential. The ticket is protected with DPAPI in
  *machine* scope so the native Credential Provider (which runs as SYSTEM on the
  secure desktop, in a different session) can unprotect it, and it embeds its
  own expiry so a stale file is useless.

Nothing here touches the secure desktop, injects input, or tampers with LSASS.
The normal Windows sign-in method always remains available because the provider
is added, not replacing.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from biounlock_agent.errors import AgentError

logger = logging.getLogger(__name__)

CREDENTIAL_FILENAME = "windows_credential.bin"
TICKET_FILENAME = "unlock_ticket.bin"

CREDENTIAL_VERSION = 1
TICKET_VERSION = 1

# Tickets cross the language boundary into the native Credential Provider, so
# the payload is a fixed, little-endian binary record rather than JSON.
TICKET_MAGIC = b"BIOUNLOCK-TICKET"  # exactly 16 bytes
_TICKET_HEADER = struct.Struct("<IQQ")  # version, issued_at, expires_at
_TICKET_LEN = struct.Struct("<H")

# A ticket only needs to survive long enough for the credential provider to
# notice it and for the user to reach the lock screen.
DEFAULT_TICKET_TTL_SECONDS = 60
MAX_TICKET_TTL_SECONDS = 300

# CRYPTPROTECT_LOCAL_MACHINE from dpapi.h. pywin32's win32crypt does not expose
# the flag constants, so the numeric values are used directly.
_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_CRYPTPROTECT_LOCAL_MACHINE = 0x04


class UnlockError(AgentError):
    """Base class for Windows-unlock integration errors."""


class UnlockNotSupportedError(UnlockError):
    """Raised when DPAPI is unavailable (non-Windows or missing pywin32)."""


class NoCredentialEnrolledError(UnlockError):
    """Raised when no Windows credential has been enrolled for unlocking."""


@dataclass(frozen=True)
class WindowsCredential:
    """A stored Windows sign-in credential (local or domain account)."""

    username: str
    password: str
    domain: str = ""


def _win32crypt():
    try:
        import win32crypt  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - any import failure means unavailable
        raise UnlockNotSupportedError(
            "Windows DPAPI (pywin32) is not available; cannot store or unlock credentials"
        ) from exc
    return win32crypt


def dpapi_available() -> bool:
    try:
        _win32crypt()
    except UnlockNotSupportedError:
        return False
    return True


def is_workstation_locked() -> bool:
    """Return True while the Windows logon/lock UI (``LogonUI.exe``) is running.

    ``LogonUI.exe`` only runs while the workstation is locked or sitting at the
    sign-in screen, so its presence reliably means the user is not signed in.
    ``OpenInputDesktop`` is *not* used because it keeps reporting the ``Default``
    desktop while locked on some machines. If the state cannot be determined this
    returns ``True`` so callers keep the conservative behaviour of still issuing
    a ticket (never breaking a legitimate unlock).
    """
    if os.name != "nt":
        return False
    try:
        import subprocess  # noqa: PLC0415

        result = subprocess.run(
            ["tasklist", "/fi", "imagename eq LogonUI.exe", "/nh"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:  # noqa: BLE001 - never let a probe failure break unlocking
        return True
    return "logonui.exe" in result.stdout.lower()


def lock_workstation() -> None:
    """Lock the workstation immediately (the same action as Win+L)."""
    if os.name != "nt":
        raise UnlockNotSupportedError("locking the workstation is only supported on Windows")
    try:
        import ctypes  # noqa: PLC0415

        if not ctypes.windll.user32.LockWorkStation():
            raise UnlockError("LockWorkStation reported failure")
    except OSError as exc:  # noqa: BLE001 - ctypes raises OSError on load failure
        raise UnlockError(f"could not lock the workstation: {exc}") from exc


def _protect(blob: bytes, *, machine: bool) -> bytes:
    win32crypt = _win32crypt()
    flags = _CRYPTPROTECT_UI_FORBIDDEN | (_CRYPTPROTECT_LOCAL_MACHINE if machine else 0)
    description = "BioUnlock unlock ticket" if machine else "BioUnlock Windows credential"
    return win32crypt.CryptProtectData(blob, description, None, None, None, flags)


def _unprotect(blob: bytes) -> bytes:
    win32crypt = _win32crypt()
    _description, data = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return data


def credential_path(home: Path) -> Path:
    return Path(home) / CREDENTIAL_FILENAME


def ticket_path(home: Path) -> Path:
    return Path(home) / TICKET_FILENAME


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _encode_ticket(
    *,
    request_id: str,
    username: str,
    domain: str,
    password: str,
    issued_at: int,
    expires_at: int,
) -> bytes:
    def field(value: str) -> bytes:
        raw = value.encode("utf-8")
        if len(raw) > 0xFFFF:
            raise UnlockError("ticket field is too long")
        return _TICKET_LEN.pack(len(raw)) + raw

    return (
        TICKET_MAGIC
        + _TICKET_HEADER.pack(TICKET_VERSION, issued_at, expires_at)
        + field(request_id)
        + field(username)
        + field(domain)
        + field(password)
    )


def _decode_ticket(payload: bytes) -> dict:
    header_end = len(TICKET_MAGIC) + _TICKET_HEADER.size
    if len(payload) < header_end or payload[: len(TICKET_MAGIC)] != TICKET_MAGIC:
        raise UnlockError("ticket header is invalid")
    version, issued_at, expires_at = _TICKET_HEADER.unpack_from(payload, len(TICKET_MAGIC))
    if version != TICKET_VERSION:
        raise UnlockError("unsupported ticket version")

    offset = header_end

    def read_field() -> str:
        nonlocal offset
        if offset + _TICKET_LEN.size > len(payload):
            raise UnlockError("ticket is truncated")
        (length,) = _TICKET_LEN.unpack_from(payload, offset)
        offset += _TICKET_LEN.size
        end = offset + length
        if end > len(payload):
            raise UnlockError("ticket is truncated")
        value = payload[offset:end].decode("utf-8")
        offset = end
        return value

    return {
        "v": version,
        "request_id": read_field(),
        "username": read_field(),
        "domain": read_field(),
        "password": read_field(),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def save_windows_credential(
    home: Path, credential: WindowsCredential, *, machine: bool | None = None
) -> Path:
    """DPAPI-protect and persist a Windows credential.

    Uses current-user scope by default; when ``machine`` is ``None`` this follows
    the service mode, since a SYSTEM-run service can't read a user-scope blob.
    """
    if not credential.username:
        raise UnlockError("username must not be empty")
    if machine is None:
        from biounlock_agent.config import service_mode

        machine = service_mode()
    payload = json.dumps(
        {
            "v": CREDENTIAL_VERSION,
            "username": credential.username,
            "domain": credential.domain,
            "password": credential.password,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    blob = _protect(payload, machine=machine)
    path = credential_path(home)
    _atomic_write(path, blob)
    return path


def load_windows_credential(home: Path) -> WindowsCredential:
    path = credential_path(home)
    if not path.exists():
        raise NoCredentialEnrolledError("no Windows credential is enrolled")
    try:
        data = json.loads(_unprotect(path.read_bytes()).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - DPAPI failure or corrupt blob
        raise UnlockError(f"could not read the stored Windows credential: {exc}") from exc
    return WindowsCredential(
        username=str(data["username"]),
        password=str(data.get("password", "")),
        domain=str(data.get("domain", "")),
    )


def has_windows_credential(home: Path) -> bool:
    return credential_path(home).exists()


def delete_windows_credential(home: Path) -> None:
    for path in (credential_path(home), ticket_path(home)):
        if path.exists():
            path.unlink()


def issue_unlock_ticket(
    home: Path,
    *,
    request_id: str,
    credential: WindowsCredential,
    ttl_seconds: int = DEFAULT_TICKET_TTL_SECONDS,
    now: float | None = None,
) -> Path:
    """Mint a machine-scope DPAPI ticket that the credential provider will consume."""
    ttl = max(1, min(int(ttl_seconds), MAX_TICKET_TTL_SECONDS))
    issued = int(now if now is not None else time.time())
    payload = _encode_ticket(
        request_id=request_id,
        username=credential.username,
        domain=credential.domain,
        password=credential.password,
        issued_at=issued,
        expires_at=issued + ttl,
    )
    blob = _protect(payload, machine=True)
    path = ticket_path(home)
    _atomic_write(path, blob)
    return path


def read_unlock_ticket(home: Path, *, now: float | None = None) -> dict | None:
    """Read and validate a ticket, returning ``None`` if missing, corrupt or expired."""
    path = ticket_path(home)
    if not path.exists():
        return None
    try:
        data = _decode_ticket(_unprotect(path.read_bytes()))
    except Exception:  # noqa: BLE001 - treat a corrupt/unreadable ticket as absent
        return None
    current = int(now if now is not None else time.time())
    if int(data.get("expires_at", 0)) <= current:
        return None
    return data


def clear_unlock_ticket(home: Path) -> None:
    path = ticket_path(home)
    if path.exists():
        path.unlink()


def reset_windows_credential(home: Path) -> None:
    delete_windows_credential(home)
