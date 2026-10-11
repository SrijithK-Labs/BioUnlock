"""Secret storage for the device private key.

Secrets are stored through a small :class:`SecretStore` interface:

- :class:`DpapiSecretStore` protects blobs with Windows DPAPI (current-user
  scope). This is the production path on Windows.
- :class:`FileSecretStore` is a plaintext, owner-only fallback used on
  non-Windows platforms and when DPAPI is unavailable (development/tests).

The device private key is never written to ``config.json`` and never logged.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class SecretStore(Protocol):
    def get(self, name: str) -> bytes | None: ...

    def set(self, name: str, value: bytes) -> None: ...

    def delete(self, name: str) -> None: ...


class FileSecretStore:
    """Plaintext files with best-effort owner-only permissions.

    Suitable for development, tests, and non-Windows use. On Windows prefer
    :class:`DpapiSecretStore`.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def _path(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe}.bin"

    def get(self, name: str) -> bytes | None:
        path = self._path(name)
        if not path.exists():
            return None
        return path.read_bytes()

    def set(self, name: str, value: bytes) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(name)
        tmp = path.with_suffix(".bin.tmp")
        tmp.write_bytes(value)
        try:
            os.chmod(tmp, 0o600)
        except (NotImplementedError, OSError):
            pass
        os.replace(tmp, path)

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.exists():
            path.unlink()


class DpapiSecretStore:
    """Windows DPAPI (current-user) protected secret store.

    Requires ``pywin32``. Blobs are protected with ``CryptProtectData`` and are
    only decryptable by the same Windows user on the same machine.
    """

    def __init__(self, base_dir: Path) -> None:
        import win32crypt  # noqa: F401  (imported for availability check)

        self._win32crypt = win32crypt
        self.base_dir = Path(base_dir)

    def _path(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe}.bin"

    def get(self, name: str) -> bytes | None:
        path = self._path(name)
        if not path.exists():
            return None
        blob = path.read_bytes()
        _description, data = self._win32crypt.CryptUnprotectData(blob, None, None, None, 0)
        return data

    def set(self, name: str, value: bytes) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        blob = self._win32crypt.CryptProtectData(
            value, "BioUnlock device key", None, None, None, 0
        )
        path = self._path(name)
        tmp = path.with_suffix(".bin.tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, path)

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.exists():
            path.unlink()


def dpapi_available() -> bool:
    try:
        import win32crypt  # noqa: F401
    except Exception:  # noqa: BLE001 - any import failure means unavailable
        return False
    return True


def default_secret_store(base_dir: Path) -> SecretStore:
    """Return DPAPI storage on Windows, otherwise a plaintext fallback."""
    base_dir = Path(base_dir)
    if os.name == "nt" and dpapi_available():
        return DpapiSecretStore(base_dir)
    if os.name == "nt":
        logger.warning(
            "pywin32 is not installed; the device key will be stored WITHOUT DPAPI "
            "protection. Install pywin32 for production use."
        )
    return FileSecretStore(base_dir)
