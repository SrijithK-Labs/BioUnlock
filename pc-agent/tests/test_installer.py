"""Tests for the one-step installer (paths, decisions, and command wiring)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from biounlock_agent import installer


def test_install_dir_uses_localappdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert installer.install_dir() == tmp_path / "local" / "BioUnlock"
    assert installer.installed_exe() == tmp_path / "local" / "BioUnlock" / "BioUnlock.exe"


def test_should_self_install_requires_a_frozen_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert installer.should_self_install() is False


def test_should_self_install_when_run_outside_install_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Downloads" / "BioUnlock.exe"))
    assert installer.should_self_install() is True


def test_should_not_self_install_when_already_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(local / "BioUnlock" / "BioUnlock.exe"))
    assert installer.should_self_install() is False


def test_bundled_provider_dll_prefers_meipass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider_dir = tmp_path / "provider"
    provider_dir.mkdir()
    dll = provider_dir / installer.PROVIDER_DLL_NAME
    dll.write_bytes(b"dll")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert installer.bundled_provider_dll() == dll


def test_provider_script_registers_the_clsid(tmp_path: Path) -> None:
    dll = tmp_path / "BioUnlockProvider.dll"
    script = installer.provider_script(dll)
    assert installer.PROVIDER_CLSID in script
    assert installer.PROVIDER_DLL_NAME in script
    assert str(dll) in script
    assert "Credential Providers" in script
    assert "InprocServer32" in script


def test_install_command_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from biounlock_agent.__main__ import build_parser

    args = build_parser().parse_args(["install"])
    assert args.func is not None

    captured: dict = {}

    def fake_install_app(**kwargs) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(installer, "install_app", fake_install_app)
    assert args.func(args) == 0
    assert captured == {"provider": True, "autostart": True, "shortcut": True, "start": True}


def test_install_command_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    from biounlock_agent.__main__ import build_parser

    args = build_parser().parse_args(
        ["install", "--no-provider", "--no-autostart", "--no-shortcut", "--no-launch"]
    )
    captured: dict = {}
    monkeypatch.setattr(installer, "install_app", lambda **kw: captured.update(kw) or 0)
    assert args.func(args) == 0
    assert captured == {"provider": False, "autostart": False, "shortcut": False, "start": False}
