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
    assert "/remove:g '*S-1-5-32-545'" in script
    assert "WindowsIdentity]::GetCurrent().User.Value" in script
    assert "S-1-5-32-545:(OI)(CI)M" not in script


def test_provider_script_can_acl_the_original_installing_user(tmp_path: Path) -> None:
    script = installer.provider_script(
        tmp_path / "BioUnlockProvider.dll", install_user_sid="S-1-5-21-123-456-789-1001"
    )

    assert "$installSid = 'S-1-5-21-123-456-789-1001'" in script


def test_provider_script_registers_the_startup_task(tmp_path: Path) -> None:
    script = installer.provider_script(tmp_path / "BioUnlockProvider.dll")
    assert installer.MACHINE_TASK_NAME in script
    assert "service-run" in script
    assert "-AtStartup" in script
    assert "SYSTEM" in script
    assert "Join-Path $env:ProgramFiles 'BioUnlock\\BioUnlock.exe'" in script
    assert "icacls.exe $installDir /inheritance:r" in script
    assert "BioUnlock.exe'" in script


def test_migrate_to_shared_home_moves_config_and_reprotects_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "local"
    target = tmp_path / "shared"
    source.mkdir()
    (source / "config.json").write_text('{"device_id": "abc"}', encoding="utf-8")
    (source / "device_key.bin").write_bytes(b"user-scope")
    (source / "windows_credential.bin").write_bytes(b"secret")
    monkeypatch.setattr(installer, "reprotect_machine_scope", lambda blob: b"machine:" + blob)

    assert installer.migrate_to_shared_home(source=source, target=target) is True

    assert (target / "config.json").is_file()
    assert (target / "device_key.bin").read_bytes() == b"machine:user-scope"
    assert (target / "windows_credential.bin").read_bytes() == b"machine:secret"
    assert (target / installer.config.SERVICE_MARKER).is_file()
    # The per-user files are kept so the change can be undone.
    assert (source / "device_key.bin").read_bytes() == b"user-scope"


def test_migrate_to_shared_home_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "local"
    target = tmp_path / "shared"
    source.mkdir()
    (source / "config.json").write_text('{"device_id": "abc"}', encoding="utf-8")
    (source / "device_key.bin").write_bytes(b"user-scope")
    monkeypatch.setattr(installer, "reprotect_machine_scope", lambda blob: b"machine:" + blob)

    assert installer.migrate_to_shared_home(source=source, target=target) is True
    (target / "device_key.bin").write_bytes(b"already-migrated")

    assert installer.migrate_to_shared_home(source=source, target=target) is True
    assert (target / "device_key.bin").read_bytes() == b"already-migrated"


def test_migrate_to_shared_home_leaves_the_marker_out_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "local"
    target = tmp_path / "shared"
    source.mkdir()
    (source / "device_key.bin").write_bytes(b"broken")

    def fail(_blob: bytes) -> bytes:
        raise OSError("DPAPI unavailable")

    monkeypatch.setattr(installer, "reprotect_machine_scope", fail)

    assert installer.migrate_to_shared_home(source=source, target=target) is False
    assert not (target / installer.config.SERVICE_MARKER).exists()



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


def test_set_credential_does_not_accept_password_argument() -> None:
    from biounlock_agent.__main__ import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["set-credential", "--password", "dummy"])


def test_install_core_reports_progress_and_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "local" / "BioUnlock"
    source = tmp_path / "downloads" / "BioUnlock.exe"
    source.parent.mkdir()
    source.write_bytes(b"exe")

    monkeypatch.setattr(installer.os, "name", "nt")
    monkeypatch.setattr(installer, "is_frozen", lambda: True)
    monkeypatch.setattr(installer, "install_dir", lambda: app_dir)
    monkeypatch.setattr(installer, "running_exe", lambda: source)
    monkeypatch.setattr(installer, "bundled_icon", lambda: None)
    monkeypatch.setattr(installer, "_stop_other_instances", lambda: None)
    monkeypatch.setattr(installer, "_set_autostart", lambda _command: None)

    def fake_shortcut(*_args, **_kwargs) -> Path:
        shortcut = app_dir / installer.SHORTCUT_FILENAME
        shortcut.write_text("lnk", encoding="utf-8")
        return shortcut

    monkeypatch.setattr(installer, "_create_shortcut", fake_shortcut)
    dll = tmp_path / "BioUnlockProvider.dll"
    dll.write_bytes(b"dll")
    monkeypatch.setattr(installer, "bundled_provider_dll", lambda: dll)
    monkeypatch.setattr(installer, "register_provider", lambda _dll: 0)
    monkeypatch.setattr(installer, "migrate_to_shared_home", lambda **_kw: True)
    launched: list[list[str]] = []
    monkeypatch.setattr(installer.subprocess, "Popen", lambda args, **_kw: launched.append(args))

    steps: list[str] = []
    statuses: list[str] = []
    result = installer.install_core(
        installer.InstallOptions(),
        on_step=steps.append,
        on_status=statuses.append,
    )

    assert result.ok is True
    assert result.copied is True
    assert result.provider_ok and result.task_ok and result.shared_ok
    assert result.autostart and result.shortcut and result.started
    assert (app_dir / "BioUnlock.exe").read_bytes() == b"exe"
    assert "Waiting for administrator approval..." in steps
    assert any(line.startswith("Installed to ") for line in statuses)
    assert "Windows Credential Provider registered." in statuses
    assert launched and launched[0][1] == "tray"
    assert "Logon-screen unlock is enabled" in result.summary()


def test_install_core_marks_a_declined_uac_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "local" / "BioUnlock"
    source = tmp_path / "BioUnlock.exe"
    source.write_bytes(b"exe")

    monkeypatch.setattr(installer.os, "name", "nt")
    monkeypatch.setattr(installer, "is_frozen", lambda: True)
    monkeypatch.setattr(installer, "install_dir", lambda: app_dir)
    monkeypatch.setattr(installer, "running_exe", lambda: source)
    monkeypatch.setattr(installer, "bundled_icon", lambda: None)
    monkeypatch.setattr(installer, "_stop_other_instances", lambda: None)
    dll = tmp_path / "BioUnlockProvider.dll"
    dll.write_bytes(b"dll")
    monkeypatch.setattr(installer, "bundled_provider_dll", lambda: dll)
    monkeypatch.setattr(installer, "register_provider", lambda _dll: 1)

    result = installer.install_core(
        installer.InstallOptions(autostart=False, shortcut=False, start=False)
    )

    assert result.ok is False
    assert result.needs_retry is True
    assert result.error is not None and "cancelled or failed" in result.error
    assert result.provider_ok is False
    assert "Credential Provider registration was cancelled" in result.summary()


def test_install_core_refuses_an_unpackaged_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installer.os, "name", "nt")
    monkeypatch.setattr(installer, "is_frozen", lambda: False)
    monkeypatch.setattr(installer, "install_dir", lambda: tmp_path / "app")

    result = installer.install_core()

    assert result.ok is False
    assert result.error is not None and "packaged BioUnlock.exe" in result.error
    assert not (tmp_path / "app").exists()


def test_silent_install_skips_the_wizard(monkeypatch: pytest.MonkeyPatch) -> None:
    from biounlock_agent.__main__ import build_parser

    monkeypatch.delenv("BIOUNLOCK_INSTALLER_QUIET", raising=False)
    args = build_parser().parse_args(["install", "--silent"])
    captured: dict = {}
    monkeypatch.setattr(installer, "install_app", lambda **kw: captured.update(kw) or 0)

    assert args.func(args) == 0
    assert captured == {"provider": True, "autostart": True, "shortcut": True, "start": True}
    assert installer.os.environ.get("BIOUNLOCK_INSTALLER_QUIET") == "1"
    installer.os.environ.pop("BIOUNLOCK_INSTALLER_QUIET", None)


def test_windowed_build_falls_back_to_the_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("tkinter")
    from biounlock_agent import installer_ui
    from biounlock_agent.__main__ import _run_install

    monkeypatch.setattr(installer, "is_frozen", lambda: True)

    def unavailable(_options: installer.InstallOptions) -> None:
        raise installer_ui.InstallerUiUnavailable("no display")

    monkeypatch.setattr(installer_ui, "run_installer", unavailable)
    captured: dict = {}
    monkeypatch.setattr(installer, "install_app", lambda **kw: captured.update(kw) or 0)

    assert _run_install(installer.InstallOptions(), quiet=False) == 0
    assert captured == {"provider": True, "autostart": True, "shortcut": True, "start": True}


def test_notify_survives_a_windowed_build_without_a_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(installer.sys, "stdout", None)
    monkeypatch.setattr(installer.sys, "stderr", None)
    monkeypatch.setattr(installer, "is_frozen", lambda: False)

    installer._notify("installed")
    installer._notify("failed", error=True)
