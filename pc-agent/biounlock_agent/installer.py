"""One-step installation of the BioUnlock tray app for the current user.

A packaged ``BioUnlock.exe`` that is run from a download folder (or
``python -m biounlock_agent install``) performs the whole setup:

* copies the app into ``%LOCALAPPDATA%\\BioUnlock``,
* registers start-at-login,
* adds a Start Menu shortcut,
* copies the bundled Credential Provider next to the app and, after a single
  elevation prompt, registers it so the phone can unlock the logon screen.

Everything except the provider registration is per-user and needs no admin.
"""

from __future__ import annotations

import base64
import ctypes
import logging
import os
import shutil
import subprocess
import sys
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
    print(text, file=sys.stderr if error else sys.stdout)
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


def provider_script(dll_source: Path) -> str:
    """PowerShell that copies the provider DLL and registers it machine-wide."""
    return (
        "$ErrorActionPreference = 'Stop'\n"
        f"$source = {_ps_quote(dll_source)}\n"
        f"$clsid = {_ps_quote(PROVIDER_CLSID)}\n"
        "$installDir = Join-Path $env:ProgramFiles 'BioUnlock'\n"
        "New-Item -ItemType Directory -Force -Path $installDir | Out-Null\n"
        f"$target = Join-Path $installDir '{PROVIDER_DLL_NAME}'\n"
        "Copy-Item -LiteralPath $source -Destination $target -Force\n"
        "$shared = Join-Path $env:ProgramData 'BioUnlock'\n"
        "New-Item -ItemType Directory -Force -Path $shared | Out-Null\n"
        "icacls $shared /inheritance:r /grant '*S-1-5-18:(OI)(CI)F' "
        "'*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)M' | Out-Null\n"
        '$clsidKey = "HKLM:\\SOFTWARE\\Classes\\CLSID\\$clsid"\n'
        "New-Item -Path $clsidKey -Force | Out-Null\n"
        "Set-ItemProperty -Path $clsidKey -Name '(default)' -Value 'BioUnlock Credential Provider'\n"
        'New-Item -Path "$clsidKey\\InprocServer32" -Force | Out-Null\n'
        "Set-ItemProperty -Path \"$clsidKey\\InprocServer32\" -Name '(default)' -Value $target\n"
        "Set-ItemProperty -Path \"$clsidKey\\InprocServer32\" -Name 'ThreadingModel' -Value 'Apartment'\n"
        '$cpKey = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\'
        'Credential Providers\\$clsid"\n'
        "New-Item -Path $cpKey -Force | Out-Null\n"
        "Set-ItemProperty -Path $cpKey -Name '(default)' -Value 'BioUnlock'\n"
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


def register_provider(dll: Path) -> bool:
    if os.name != "nt":  # pragma: no cover - non-Windows
        return False
    return _run_elevated(provider_script(dll)) == 0


def install_app(
    *,
    provider: bool = True,
    autostart: bool = True,
    shortcut: bool = True,
    start: bool = True,
) -> int:
    """Install the app for the current user. Returns a process exit code."""
    if os.name != "nt":
        _notify("Installation is supported on Windows only.", error=True)
        return 1
    if not is_frozen():
        _notify("Installation expects the packaged BioUnlock.exe (or install-agent.ps1).", error=True)
        return 1

    steps: list[str] = []
    home = install_dir()
    home.mkdir(parents=True, exist_ok=True)
    target = installed_exe()
    source = running_exe()

    if not _same_file(source, target):
        _stop_other_instances()
        shutil.copy2(source, target)
        steps.append(f"Installed to {home}")
    else:
        steps.append(f"Already installed at {home}")

    icon = None
    icon_source = bundled_icon()
    if icon_source is not None:
        try:
            icon = home / APP_ICON_NAME
            shutil.copy2(icon_source, icon)
        except OSError:
            icon = None

    if autostart:
        _set_autostart(f'"{target}" tray')
        steps.append("Start-at-login enabled.")

    if shortcut:
        try:
            _create_shortcut(target, "tray", home, icon or target)
            steps.append("Start Menu shortcut created.")
        except Exception as exc:  # noqa: BLE001 - shortcut is best effort
            logger.warning("Could not create the Start Menu shortcut: %s", exc)

    provider_attempted = False
    provider_ok = False
    if provider:
        dll = bundled_provider_dll()
        if dll is None:
            steps.append("Credential Provider not bundled (logon-screen unlock unavailable).")
        else:
            local_dll = dll
            if not _same_file(dll, home / PROVIDER_DLL_NAME):
                local_dll = home / PROVIDER_DLL_NAME
                shutil.copy2(dll, local_dll)
            provider_attempted = True
            provider_ok = register_provider(local_dll)

    if start:
        try:
            subprocess.Popen([str(target), "tray"], cwd=str(home))
        except OSError as exc:  # noqa: BLE001 - launching is best effort
            logger.warning("Could not start the app: %s", exc)

    if provider_attempted and not provider_ok:
        _notify(
            "\n".join(
                [
                    *steps,
                    "",
                    "Credential Provider registration was cancelled or failed, so logon-screen",
                    "unlock is not enabled. Re-run the installer to retry that step.",
                ]
            ),
            error=True,
        )
        return 1

    tail = ["", "Done. Open the tray icon, enter your backend URL and API key, then Link this PC."]
    if provider_ok:
        tail.append("Finally, set your Windows password in the tray to enable logon-screen unlock.")
    _notify("\n".join([*steps, *tail]))
    return 0
