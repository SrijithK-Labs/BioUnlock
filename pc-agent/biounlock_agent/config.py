"""Agent configuration and on-disk layout.

Non-secret configuration lives in ``config.json`` under the agent home
directory (``%LOCALAPPDATA%\\BioUnlock`` on Windows). Secrets (the device
private key) are kept separate and protected by :mod:`biounlock_agent.storage`.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

APP_DIR_NAME = "BioUnlock"
ENV_HOME = "BIOUNLOCK_AGENT_HOME"
ENV_SHARED_HOME = "BIOUNLOCK_AGENT_SHARED_HOME"
CONFIG_FILENAME = "config.json"
REPLAY_FILENAME = "replay.sqlite3"
DEVICE_KEY_NAME = "device_key"


def default_home() -> Path:
    """Resolve the agent home directory, honoring ``BIOUNLOCK_AGENT_HOME``."""
    override = os.environ.get(ENV_HOME)
    if override:
        return Path(override)
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
    account_email: str | None = None

    @property
    def is_enrolled(self) -> bool:
        return bool(self.server_url and self.device_id and self.server_signing_public_key)

    @property
    def is_paired(self) -> bool:
        return bool(self.paired and self.is_enrolled)


class ConfigStore:
    """Load/save :class:`AgentConfig` as JSON with atomic replacement."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home) if home is not None else default_home()
        self.path = self.home / CONFIG_FILENAME

    def ensure_home(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> AgentConfig:
        if not self.path.exists():
            return AgentConfig()
        return AgentConfig.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, config: AgentConfig) -> None:
        self.ensure_home()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
