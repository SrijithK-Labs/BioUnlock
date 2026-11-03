"""Installation of the BioUnlock tray app for the current user.

A packaged ``BioUnlock.exe`` that is run from a download folder (or
``python -m biounlock_agent install``) starts the setup wizard
(:mod:`biounlock_agent.installer_ui`), which performs the whole setup:

* copies the app into ``%LOCALAPPDATA%\\BioUnlock``,
* registers start-at-login,
* adds a Start Menu shortcut,
* copies the bundled Credential Provider next to the app and, after a single
  elevation prompt, registers it together with a SYSTEM startup task so the
  phone can unlock the logon screen, including after a reboot,
* moves the agent profile to ``%ProgramData%\\BioUnlock`` with machine-scope
  secrets so the startup task can read it before anyone signs in.

Scripted runs use ``--silent`` and print the same steps instead. Everything
except that one elevated step is per-user and needs no admin.
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from biounlock_agent import config

try:  # pragma: no cover - Windows only
    import winreg
except ImportError:  # pragma: no cover - non-Windows dev
    winreg = None

logger = logging.getLogger(__name__)

APP_EXE_NAME = "BioUnlock.exe"
PROVIDER_DLL_NAME = "BioUnlockProvider.dll"
APP_ICON_NAME = "BioUnlock.ico"

# COM in-proc server / credential provider id; must match the native provider.
PROVIDER_CLSID = "{B10F7A5E-3C41-4E9A-9F2B-7D6C1A2E3F40}"

AUTOSTART_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "BioUnlock"
SHORTCUT_FILENAME = "BioUnlock.lnk"
START_MENU_SUBPATH = r"Microsoft\Windows\Start Menu\Programs"

# Scheduled task that runs the agent as SYSTEM at boot, before anyone signs in.
MACHINE_TASK_NAME = "BioUnlockAgent"

# Fast Startup resumes a hibernated kernel, and Windows skips AtStartup tasks on
# that path, so the installer turns it off to keep the boot agent reliable.
FAST_STARTUP_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Power"

# Secrets that move from the per-user store to the machine-wide one. The blobs
# are re-protected with DPAPI machine scope so the SYSTEM task can read them.
SHARED_SECRET_FILES = ("device_key.bin", "api_token.bin", "windows_credential.bin")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """Per-user install directory (``%LOCALAPPDATA%\\BioUnlock``)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / config.APP_DIR_NAME
    return Path.home() / ".biounlock"


def installed_exe() -> Path:
    return install_dir() / APP_EXE_NAME


def running_exe() -> Path:
    return Path(sys.executable)


def should_self_install() -> bool:
    """True when a packaged app is running from outside its install location."""
    if not is_frozen() or os.name != "nt":
        return False
    try:
        return running_exe().resolve() != installed_exe().resolve()
    except OSError:
        return True


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def bundled_provider_dll() -> Path | None:
    """Locate the provider DLL bundled into the exe (or the repo build)."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "provider" / PROVIDER_DLL_NAME)
    repo = Path(__file__).resolve().parent.parent
    candidates.append(repo / "windows-credential-provider" / "build" / PROVIDER_DLL_NAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def bundled_icon() -> Path | None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / APP_ICON_NAME)
    candidates.append(Path(__file__).resolve().parent / "assets" / APP_ICON_NAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _notify(text: str, *, error: bool = False) -> None:
    """Print, and surface a single message box in a windowed (frozen) build.

    Set ``BIOUNLOCK_INSTALLER_QUIET=1`` to skip the dialog (scripted installs).
    """
    stream = sys.stderr if error else sys.stdout
    if stream is not None:  # a windowed PyInstaller build has no console
        print(text, file=stream)
    if not is_frozen() or os.name != "nt":  # pragma: no cover - non-Windows
        return
    if os.environ.get("BIOUNLOCK_INSTALLER_QUIET"):
        return
    try:
        icon = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, text, "BioUnlock", icon)
    except Exception:  # noqa: BLE001 - never fail because of a message box
        pass


def _powershell(script: str, *, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _stop_other_instances() -> None:
    """Stop a previously installed copy so its .exe can be replaced."""
    keep = [pid for pid in (os.getpid(), os.getppid()) if pid]
    condition = " -and ".join(f"$_.Id -ne {pid}" for pid in keep)
    script = (
        "Get-Process -Name BioUnlock -ErrorAction SilentlyContinue | "
        f"Where-Object {{ {condition} }} | Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    try:
        _powershell(script, timeout=30)
    except Exception as exc:  # noqa: BLE001 - best effort
        logger.warning("Could not stop the running app: %s", exc)


def _set_autostart(command: str) -> None:
    if winreg is None:  # pragma: no cover - non-Windows
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
        winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, command)


def fast_startup_enabled() -> bool:
    """True when Windows would skip the at-startup agent task after a shutdown."""
    if winreg is None:  # pragma: no cover - non-Windows
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, FAST_STARTUP_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "HiberbootEnabled")
    except OSError:
        return False
    return bool(value)


def _create_shortcut(target: Path, arguments: str, workdir: Path, icon: Path | None) -> Path:
    start_menu = Path(os.environ["APPDATA"]) / START_MENU_SUBPATH
    start_menu.mkdir(parents=True, exist_ok=True)
    shortcut = start_menu / SHORTCUT_FILENAME
    icon_line = f"$s.IconLocation = {_ps_quote(icon)} + ',0'; " if icon else ""
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut({_ps_quote(shortcut)}); "
        f"$s.TargetPath = {_ps_quote(target)}; "
        f"$s.Arguments = {_ps_quote(arguments)}; "
        f"$s.WorkingDirectory = {_ps_quote(workdir)}; "
        "$s.Description = 'BioUnlock phone unlock agent'; "
        f"{icon_line}"
        "$s.Save()"
    )
    _powershell(script, timeout=60)
    return shortcut


def provider_script(dll_source: Path, install_user_sid: str | None = None) -> str:
    """PowerShell that registers the provider and the pre-login task machine-wide."""
    sid_assignment = (
        f"$installSid = {_ps_quote(install_user_sid)}\n"
        if install_user_sid
        else "$installSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value\n"
    )
    return (
        "$ErrorActionPreference = 'Stop'\n"
        f"$source = {_ps_quote(dll_source)}\n"
        f"$clsid = {_ps_quote(PROVIDER_CLSID)}\n"
        "$installDir = Join-Path $env:ProgramFiles 'BioUnlock'\n"
        "New-Item -ItemType Directory -Force -Path $installDir | Out-Null\n"
        "$exeSource = " + _ps_quote(installed_exe()) + "\n"
        "$exeTarget = Join-Path $installDir 'BioUnlock.exe'\n"
        "if (-not (Test-Path -LiteralPath $exeSource)) { throw 'Installed BioUnlock executable is missing.' }\n"
        # A pre-login agent from an older install can still be running and holds
        # its .exe mapped, which makes Windows refuse the overwrite below. Stop
        # the boot task and the processes running from the target path first;
        # the installer process itself lives elsewhere, so it is not touched.
        f"Stop-ScheduledTask -TaskName {_ps_quote(MACHINE_TASK_NAME)} -ErrorAction SilentlyContinue\n"
        "Get-Process -Name BioUnlock -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -eq $exeTarget } | "
        "Stop-Process -Force -ErrorAction SilentlyContinue\n"
        "Start-Sleep -Milliseconds 500\n"
        "& icacls.exe $installDir /reset /T /C | Out-Null\n"
        "if ($LASTEXITCODE -ne 0) { throw 'Could not reset the protected program directory ACL.' }\n"
        # Directory only, deliberately no /T: the (OI)(CI) inheritance flags are
        # not valid on a file, and icacls strips a file's ACL instead of adding
        # the entry, leaving it unreadable even for Administrators. Children
        # inherit this ACL when they are created below.
        "& icacls.exe $installDir /inheritance:r /grant:r "
        "'*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null\n"
        "if ($LASTEXITCODE -ne 0) { throw 'Could not secure the protected program directory.' }\n"
        "Copy-Item -LiteralPath $exeSource -Destination $exeTarget -Force\n"
        f"$target = Join-Path $installDir '{PROVIDER_DLL_NAME}'\n"
        "Copy-Item -LiteralPath $source -Destination $target -Force\n"
        # Overwriting an existing file keeps its old ACL, which may be the
        # broken (empty) one from an earlier install, so set both files
        # explicitly with file-appropriate (no inheritance) permissions.
        "& icacls.exe $exeTarget /grant:r "
        "'*S-1-5-18:F' '*S-1-5-32-544:F' '*S-1-5-32-545:RX' | Out-Null\n"
        "if ($LASTEXITCODE -ne 0) { throw 'Could not secure the installed program file.' }\n"
        "& icacls.exe $target /grant:r "
        "'*S-1-5-18:F' '*S-1-5-32-544:F' '*S-1-5-32-545:RX' | Out-Null\n"
        "if ($LASTEXITCODE -ne 0) { throw 'Could not secure the credential provider file.' }\n"
        "$shared = Join-Path $env:ProgramData 'BioUnlock'\n"
        "New-Item -ItemType Directory -Force -Path $shared | Out-Null\n"
        + sid_assignment
        +
        "& icacls.exe $shared /inheritance:r /remove:g '*S-1-5-32-545' /grant:r "
        "'*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' "
        "('*{0}:(OI)(CI)M' -f $installSid) | Out-Null\n"
        "if ($LASTEXITCODE -ne 0) { throw 'Failed to secure the BioUnlock data directory.' }\n"
        '$clsidKey = "HKLM:\\SOFTWARE\\Classes\\CLSID\\$clsid"\n'
        "New-Item -Path $clsidKey -Force | Out-Null\n"
        "Set-ItemProperty -Path $clsidKey -Name '(default)' -Value 'BioUnlock Credential Provider'\n"
        'New-Item -Path "$clsidKey\\InprocServer32" -Force | Out-Null\n'
        "Set-ItemProperty -Path \"$clsidKey\\InprocServer32\" -Name '(default)' -Value $target\n"
        "Set-ItemProperty -Path \"$clsidKey\\InprocServer32\" -Name 'ThreadingModel' -Value 'Apartment'\n"
        '$cpKey = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\'
        'Credential Providers\\$clsid"\n'
        "New-Item -Path $cpKey -Force | Out-Null\n"
        "Set-ItemProperty -Path $cpKey -Name '(default)' -Value 'BioUnlock'\n" + startup_task_script()
        +
        # Fast Startup (hiberboot) resumes a hibernated kernel instead of
        # booting, and Windows does not run AtStartup tasks on that path, so a
        # "shut down" would leave the PC without a pre-login agent. This runs
        # last and is allowed to fail so it can never block the provider/task.
        f"$powerKey = 'HKLM:\\{FAST_STARTUP_KEY}'\n"
        "try {\n"
        "  Set-ItemProperty -Path $powerKey -Name 'HiberbootEnabled' "
        "-Value 0 -Type DWord -ErrorAction Stop\n"
        "} catch {\n"
        "  Write-Host 'Could not disable Fast Startup:' $_.Exception.Message\n"
        "}\n"
    )


def startup_task_script() -> str:
    """PowerShell block that registers the SYSTEM boot task (exit code 2 on failure).

    Runs the same executable with ``service-run``. SYSTEM is required because the
    per-user agent cannot decrypt a user-scope DPAPI secret before that user has
    signed in.
    """
    return (
        f"$taskName = {_ps_quote(MACHINE_TASK_NAME)}\n"
        "$exe = Join-Path $env:ProgramFiles 'BioUnlock\\BioUnlock.exe'\n"
        "try {\n"
        "  $action = New-ScheduledTaskAction -Execute $exe -Argument 'service-run'\n"
        "  $trigger = New-ScheduledTaskTrigger -AtStartup\n"
        "  $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' "
        "-LogonType ServiceAccount -RunLevel Highest\n"
        "  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -StartWhenAvailable\n"
        "  $settings.ExecutionTimeLimit = 'PT0S'\n"
        "  $settings.MultipleInstances = 'IgnoreNew'\n"
        "  $settings.RestartCount = 3\n"
        "  $settings.RestartInterval = 'PT1M'\n"
        "  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger "
        "-Principal $principal -Settings $settings -Force | Out-Null\n"
        "}\n"
        "catch {\n"
        "  Write-Host \"Pre-login task registration failed: $_\"\n"
        "  exit 2\n"
        "}\n"
    )


def _run_elevated(script: str, *, timeout: int = 180) -> int:
    """Run a PowerShell script elevated (one UAC prompt); return its exit code."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    inner = (
        "$p = Start-Process -Verb RunAs -Wait -PassThru -FilePath powershell.exe "
        f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand','{encoded}'); "
        "exit $p.ExitCode"
    )
    try:
        result = _powershell(inner, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("Timed out registering the credential provider.")
        return 1
    return result.returncode


def register_provider(dll: Path) -> int:
    """Register the provider and the SYSTEM startup task. Returns the exit code.

    ``0`` means both were installed; ``2`` means the credential provider is
    registered but the boot task could not be created.
    """
    if os.name != "nt":  # pragma: no cover - non-Windows
        return 1
    try:
        import win32api  # noqa: PLC0415 - Windows only
        import win32con  # noqa: PLC0415 - Windows only
        import win32security  # noqa: PLC0415 - Windows only

        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
        try:
            user_sid = win32security.GetTokenInformation(
                token, win32security.TokenUser
            )[0]
            install_user_sid = win32security.ConvertSidToStringSid(user_sid)
        finally:
            win32api.CloseHandle(token)
    except Exception as exc:  # noqa: BLE001 - never install with a broad ACL
        logger.warning("Could not identify the installing user for secure ACLs: %s", exc)
        return 1
    return _run_elevated(provider_script(dll, install_user_sid))


def reprotect_machine_scope(blob: bytes) -> bytes:
    """Decrypt a DPAPI blob (any scope) and re-protect it with machine scope."""
    import win32crypt  # noqa: PLC0415 - Windows only

    _description, data = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return win32crypt.CryptProtectData(data, "BioUnlock", None, None, None, 0x04)


def migrate_to_shared_home(source: Path | None = None, target: Path | None = None) -> bool:
    """Switch the agent to the machine-wide home used before login.

    The boot task runs as SYSTEM, long before any user profile is loaded, so it
    cannot decrypt per-user DPAPI blobs. Copy the (non-secret) config, re-protect
    the secrets to machine scope, and only then write the marker that makes
    :func:`config.default_home` resolve to the shared directory. The per-user
    files are left untouched so nothing is lost if this is interrupted.
    """
    if os.name != "nt":  # pragma: no cover - non-Windows
        return False
    from biounlock_agent.config import ConfigStore  # noqa: PLC0415 - avoid a cycle

    src = Path(source) if source is not None else install_dir()
    dst = Path(target) if target is not None else config.default_shared_home()
    try:
        dst.mkdir(parents=True, exist_ok=True)
        if not (dst / config.CONFIG_FILENAME).exists():
            loaded = ConfigStore(src).load()
            if loaded.is_enrolled or (src / config.CONFIG_FILENAME).exists():
                ConfigStore(dst).save(loaded)
        for name in SHARED_SECRET_FILES:
            source_file = src / name
            target_file = dst / name
            if source_file.is_file() and not target_file.exists():
                tmp = target_file.with_suffix(target_file.suffix + ".tmp")
                tmp.write_bytes(reprotect_machine_scope(source_file.read_bytes()))
                os.replace(tmp, target_file)
        (dst / config.SERVICE_MARKER).write_text(
            json.dumps({"installedAt": datetime.now(UTC).isoformat()}, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception as exc:  # noqa: BLE001 - keep the per-user install usable
        logger.warning("Could not switch to the machine-wide profile: %s", exc)
        return False


@dataclass(frozen=True)
class InstallOptions:
    """What the user chose in the setup wizard."""

    provider: bool = True
    autostart: bool = True
    shortcut: bool = True
    start: bool = True


@dataclass
class InstallResult:
    """Outcome of :func:`install_core`, shaped for both the console and the wizard."""

    ok: bool
    home: Path
    copied: bool = False
    autostart: bool = False
    shortcut: bool = False
    started: bool = False
    provider_requested: bool = False
    provider_bundled: bool = False
    provider_ok: bool = False
    task_ok: bool = False
    shared_ok: bool = False
    error: str | None = None
    details: list[str] = field(default_factory=list)

    @property
    def needs_retry(self) -> bool:
        """Whether re-running setup can fix the only thing that failed."""
        return self.provider_requested and self.provider_bundled and not self.provider_ok

    def notes(self) -> list[str]:
        """Follow-up advice shown after setup."""
        lines = ["Open the tray icon, enter your backend URL and API key, then Link this PC."]
        if self.provider_ok and self.shared_ok and self.task_ok:
            lines.append("Logon-screen unlock is enabled for this PC, including after a restart.")
        if self.provider_ok and not self.shared_ok:
            lines.append(
                "The machine-wide profile could not be prepared, so unlock at the sign-in "
                "screen after a restart is unavailable. Re-run the installer to retry."
            )
        if self.provider_ok and not self.task_ok:
            lines.append(
                "The boot task could not be created, so unlock at the sign-in screen after "
                "a restart may be unavailable. Re-run the installer to retry."
            )
        if self.provider_ok:
            lines.append("Set your Windows password in the tray to enable logon-screen unlock.")
        return lines

    def summary(self) -> str:
        """Full text for the console / message box."""
        if self.error:
            return "\n".join([*self.details, "", self.error])
        return "\n".join([*self.details, "", "Done.", *self.notes()])


def install_core(
    options: InstallOptions | None = None,
    *,
    on_step: Callable[[str], None] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> InstallResult:
    """Install the app, reporting progress to optional callbacks.

    ``on_step`` announces what is happening now (including the UAC prompt) and
    ``on_status`` reports a finished step. Neither callback may raise; the
    wizard feeds them into a queue, and the console runner leaves them unset.
    """
    options = options or InstallOptions()
    home = install_dir()
    result = InstallResult(ok=False, home=home)
    result.provider_requested = options.provider

    def step(text: str) -> None:
        logger.info("install: %s", text)
        if on_step is not None:
            on_step(text)

    def done(text: str) -> None:
        logger.info("install: %s", text)
        result.details.append(text)
        if on_status is not None:
            on_status(text)

    if os.name != "nt":
        result.error = "Installation is supported on Windows only."
        return result
    if not is_frozen():
        result.error = "Installation expects the packaged BioUnlock.exe (or install-agent.ps1)."
        return result

    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.error = f"Could not create {home}: {exc}"
        return result

    target = installed_exe()
    source = running_exe()

    if options.provider or not _same_file(source, target):
        # The tray is restarted below anyway; stopping it first frees the .exe
        # and lets the per-user profile be copied to the machine-wide one.
        step("Closing the running app...")
        _stop_other_instances()

    step("Copying BioUnlock to your user profile...")
    try:
        if not _same_file(source, target):
            shutil.copy2(source, target)
            result.copied = True
            done(f"Installed to {home}")
        else:
            done(f"Already installed at {home}")
    except OSError as exc:
        logger.warning("Could not copy the app: %s", exc)
        result.error = f"Could not copy the app to {home}: {exc}"
        return result

    icon: Path | None = None
    icon_source = bundled_icon()
    if icon_source is not None:
        try:
            icon = home / APP_ICON_NAME
            shutil.copy2(icon_source, icon)
        except OSError:
            icon = None

    if options.autostart:
        step("Enabling start at login...")
        try:
            _set_autostart(f'"{target}" tray')
            result.autostart = True
            done("Start-at-login enabled.")
        except OSError as exc:  # pragma: no cover - depends on the registry
            logger.warning("Could not enable start-at-login: %s", exc)

    if options.shortcut:
        step("Creating a Start Menu shortcut...")
        try:
            shortcut = _create_shortcut(target, "tray", home, icon or target)
            if shortcut.is_file():
                result.shortcut = True
                done("Start Menu shortcut created.")
        except Exception as exc:  # noqa: BLE001 - shortcut is best effort
            logger.warning("Could not create the Start Menu shortcut: %s", exc)

    if options.provider:
        dll = bundled_provider_dll()
        result.provider_bundled = dll is not None
        if dll is None:
            done("Credential Provider not bundled (logon-screen unlock unavailable).")
        else:
            step("Copying the Windows Credential Provider...")
            local_dll = dll
            if not _same_file(dll, home / PROVIDER_DLL_NAME):
                local_dll = home / PROVIDER_DLL_NAME
                shutil.copy2(dll, local_dll)
            step("Waiting for administrator approval...")
            code = register_provider(local_dll)
            result.provider_ok = code in (0, 2)
            result.task_ok = code == 0
            if result.provider_ok:
                done("Windows Credential Provider registered.")
                if fast_startup_enabled():
                    logger.warning(
                        "Windows Fast Startup is still on: the pre-login agent will not "
                        "start after a shut down, only after a restart."
                    )
                else:
                    done(
                        "Fast Startup disabled so the pre-login agent runs after every shutdown."
                    )
                # The boot task runs as SYSTEM, so the device key and Windows
                # credential move to the shared, machine-protected store.
                step("Preparing the machine-wide profile...")
                result.shared_ok = migrate_to_shared_home(source=home)
                if result.shared_ok:
                    done("Profile prepared for the background agent.")

    if options.start:
        step("Starting BioUnlock...")
        try:
            subprocess.Popen([str(target), "tray"], cwd=str(home))
            result.started = True
            done("BioUnlock started.")
        except OSError as exc:  # noqa: BLE001 - launching is best effort
            logger.warning("Could not start the app: %s", exc)

    result.ok = True
    if result.needs_retry:
        result.ok = False
        result.error = (
            "Credential Provider registration was cancelled or failed, so logon-screen "
            "unlock is not enabled. Re-run the installer to retry that step."
        )
    return result


def install_app(
    *,
    provider: bool = True,
    autostart: bool = True,
    shortcut: bool = True,
    start: bool = True,
) -> int:
    """Install the app for the current user. Returns a process exit code."""
    result = install_core(
        InstallOptions(
            provider=provider,
            autostart=autostart,
            shortcut=shortcut,
            start=start,
        )
    )
    _notify(result.summary(), error=not result.ok)
    return 0 if result.ok else 1
