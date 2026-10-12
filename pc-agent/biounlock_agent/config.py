"""Agent configuration and on-disk layout.

Non-secret configuration lives in ``config.json`` under the agent home
directory (``%LOCALAPPDATA%\\BioUnlock`` on Windows). Secrets (the device
private key) are kept separate and protected by :mod:`biounlock_agent.storage`.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

APP_DIR_NAME = "BioUnlock"
ENV_HOME = "BIOUNLOCK_AGENT_HOME"
ENV_SHARED_HOME = "BIOUNLOCK_AGENT_SHARED_HOME"
ENV_MACHINE_SECRETS = "BIOUNLOCK_AGENT_MACHINE_SECRETS"
CONFIG_FILENAME = "config.json"
REPLAY_FILENAME = "replay.sqlite3"
DEVICE_KEY_NAME = "device_key"
SERVICE_MARKER = "service.json"


def _env_truthy(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def service_mode() -> bool:
    """Whether the agent is installed machine-wide by the service installer."""
    if _env_truthy(ENV_MACHINE_SECRETS):
        return True
    try:
        return (default_shared_home() / SERVICE_MARKER).exists()
    except OSError:
        return False


def default_home() -> Path:
    """Resolve the agent home directory, honoring ``BIOUNLOCK_AGENT_HOME``.

    When the boot-start service is installed this is the shared machine home so
    the service and the tray read the same config and secrets.
    """
    override = os.environ.get(ENV_HOME)
    if override:
        return Path(override)
    if service_mode():
        return default_shared_home()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
    return Path.home() / ".biounlock"


def default_shared_home() -> Path:
    """Directory shared with the SYSTEM-run Credential Provider.

    Unlock tickets are written here (``%ProgramData%\\BioUnlock``) so the native
    provider, running on the secure desktop as SYSTEM, can read them. Override
    with ``BIOUNLOCK_AGENT_SHARED_HOME``.
    """
    override = os.environ.get(ENV_SHARED_HOME)
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
        return Path(base) / APP_DIR_NAME
    return Path.home() / ".biounlock"


def default_device_name() -> str:
    return socket.gethostname() or "Windows PC"


class AgentConfig(BaseModel):
    """Persisted, non-secret agent state."""

    server_url: str | None = None
    device_id: str | None = None
    device_name: str = Field(default_factory=default_device_name)
    platform: str = "windows"
    server_signing_public_key: str | None = None
    server_signing_key_fingerprint: str | None = None
    enrolled_at: datetime | None = None
    paired: bool = False
    paired_at: datetime | None = None

    @property
    def is_enrolled(self) -> bool:
        return bool(self.server_url and self.device_id and self.server_signing_public_key)

    @property
    def is_paired(self) -> bool:
        return bool(self.paired and self.is_enrolled)


class ConfigStore:
    """Load/save :class:`AgentConfig` as JSON with atomic replacement.

    Saves are atomic and keep a ``config.json.bak`` copy of the previous good
    file, so an interrupted write, a crash or a power cut can never lose the
    saved link. :meth:`load` transparently falls back to the backup and never
    raises on a corrupt file.
    """

    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home) if home is not None else default_home()
        self.path = self.home / CONFIG_FILENAME
        self.backup_path = self.path.with_suffix(".json.bak")

    def ensure_home(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> AgentConfig:
        if self.path.exists():
            config = self._try_load(self.path)
            if config is not None:
                return config
            logger.warning("Configuration file is unreadable; trying the backup")
        if self.backup_path.exists():
            config = self._try_load(self.backup_path)
            if config is not None:
                logger.warning("Recovered configuration from %s", self.backup_path)
                return config
        return AgentConfig()

    @staticmethod
    def _try_load(path: Path) -> AgentConfig | None:
        try:
            return AgentConfig.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self, config: AgentConfig) -> None:
        self.ensure_home()
        serialized = config.model_dump_json(indent=2)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(serialized, encoding="utf-8")
        # Keep the last known-good file as a backup before replacing it.
        if self.path.exists():
            try:
                shutil.copy2(self.path, self.backup_path)
            except OSError:
                pass
        os.replace(tmp, self.path)

    def reset(self) -> None:
        for path in (self.path, self.backup_path):
            if path.exists():
                path.unlink()
