"""Taskbar tray application for the BioUnlock PC agent.

The tray app is the recommended way to run BioUnlock on Windows. It:

* lives in the notification area (system tray) and starts the agent in the
  background as soon as the PC is linked;
* provides a small settings window (tkinter) to enter the server URL, link this
  PC (pairing QR/code), and store the Windows credential used for unlocking;
* can start automatically when the user logs in.

The heavy lifting is unchanged: :class:`~biounlock_agent.agent.Agent` verifies
every server-signed envelope independently before acting.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageTk

from biounlock_agent import unlock
from biounlock_agent.agent import Agent
from biounlock_agent.config import default_home
from biounlock_agent.logging_setup import configure_logging

logger = logging.getLogger(__name__)


try:  # pragma: no cover - Windows-only registry integration
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "BioUnlock"
INSTANCE_MUTEX_NAME = "BioUnlockTray"
ICON_SIZE = 64

# Kept alive for the whole process so Windows does not release the lock early.
_instance_mutex: object | None = None


def render_qr_image(payload: str) -> Image.Image | None:
    """Render *payload* to a grayscale PIL image, or ``None`` if unavailable.

    Returns ``None`` when segno is not installed; raises if rendering itself
    fails. Kept separate from the widget code so it can be tested directly.
    """
    try:
        import segno
    except Exception:  # noqa: BLE001 - QR is optional
        return None
    buffer = io.BytesIO()
    segno.make(payload, error="m").save(buffer, kind="png", scale=4)
    buffer.seek(0)
    image = Image.open(buffer).convert("L")
    image.load()
    return image


def watch_for_pairing(
    agent: Agent,
    *,
    closing: Callable[[], bool],
    on_paired: Callable[[], None],
    poll_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll the server until this PC is paired, then call *on_paired*.

    Runs off the UI thread and keeps going until the PC is paired, is no longer
    enrolled, or *closing* returns ``True``. This is what lets the tray notice a
    phone-side pairing on its own, instead of only during the brief window right
    after "Link this PC" (which forced users to restart the app).
    """
    while not closing():
        if agent.config.is_paired:
            return
        if not agent.config.is_enrolled:
            return
        try:
            paired = agent.refresh_pairing().paired
        except Exception:  # noqa: BLE001 - keep watching through transient errors
            paired = False
        if paired:
            on_paired()
            return
        sleep(poll_interval)


def _acquire_single_instance() -> bool:
    """Allow only one tray (and therefore one agent) per login session.

    Without this, a second launch (double-click while the start-at-login copy is
    already running) would run two agents against the same device key, racing on
    the replay database and duplicating deliveries. Returns ``True`` when this
    process owns the lock.
    """
    global _instance_mutex
    if os.name != "nt":  # pragma: no cover - single instance guard is Windows-only
        _instance_mutex = object()
        return True
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, INSTANCE_MUTEX_NAME)
    if not handle:
        return True
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return False
    _instance_mutex = handle
    return True


def _release_single_instance() -> None:
    """Drop the single-instance lock so a freshly launched copy can take over."""
    global _instance_mutex
    handle = _instance_mutex
    _instance_mutex = None
    if handle is None or os.name != "nt":  # pragma: no cover - Windows-only
        return
    try:  # pragma: no cover - Windows API call
        import ctypes

        ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - best effort
        pass


def _relaunch_arguments() -> list[str]:
    """Command line that launches another copy of this tray app."""
    if getattr(sys, "frozen", False):  # pragma: no cover - packaged build
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, "-m", "biounlock_agent", "tray"]


def _relaunch_working_dir() -> str:
    if getattr(sys, "frozen", False):  # pragma: no cover - packaged build
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- autostart at login ---------------------------------------------------


def _pythonw_path() -> str:
    # Prefer pythonw.exe so no console window flashes at login.
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def _source_launcher_path() -> Path:
    return default_home() / "biounlock-tray.cmd"


def _write_source_launcher() -> Path | None:
    """Write a login-friendly launcher for running the app from source.

    A ``.cmd`` script (rather than the Python module directly) fixes the working
    directory so ``-m biounlock_agent`` always resolves, and because script
    files are not blocked by Windows Smart App Control the way an unsigned
    ``.exe`` is. Returns the path, or ``None`` if it cannot be written.
    """
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(package_dir)
    try:
        home = default_home()
        home.mkdir(parents=True, exist_ok=True)
        path = _source_launcher_path()
        path.write_text(
            "@echo off\r\n"
            f'cd /d "{project_dir}"\r\n'
            f'start "" "{_pythonw_path()}" -m biounlock_agent tray\r\n',
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def _startup_command() -> str:
    """Return the command to register under the per-user Run key."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" tray'
    launcher = _write_source_launcher()
    if launcher is not None:
        return f'"{launcher}"'
    return f'"{_pythonw_path()}" -m biounlock_agent tray'


def is_autostart_enabled() -> bool:
    if winreg is None:  # pragma: no cover - non-Windows
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if winreg is None:  # pragma: no cover - non-Windows
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
            except FileNotFoundError:
                pass


# --- icon -----------------------------------------------------------------


def asset_path(name: str) -> Path | None:
    """Locate a bundled asset, working both from source and a PyInstaller build."""
    candidates = [Path(__file__).resolve().parent / "assets" / name]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "assets" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def create_icon_image() -> Image.Image:
    """Return the BioUnlock tray icon, falling back to a drawn glyph."""
    logo = asset_path("logo.png")
    if logo is not None:
        try:
            image = Image.open(logo).convert("RGBA")
            image.thumbnail((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
            return image
        except Exception:  # noqa: BLE001 - never let a bad logo break the tray
            logger.warning("Could not load the tray logo; using the fallback icon.")
    return _fallback_icon_image()


def _fallback_icon_image() -> Image.Image:
    """Draw a simple BioUnlock tray icon when no logo asset is available."""
    size = ICON_SIZE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=16, fill=(46, 107, 230, 255))
    cx = cy = size / 2
    for radius in (11, 17, 23):
        draw.arc(
            [cx - radius, cy - radius + 6, cx + radius, cy + radius + 6],
            start=205,
            end=335,
            fill=(255, 255, 255, 255),
            width=3,
        )
    draw.rounded_rectangle([cx - 5, cy - 4, cx + 5, cy + 10], radius=5, fill=(255, 255, 255, 255))
    return image


# --- agent runner ---------------------------------------------------------


class AgentRunner:
    """Runs the agent's asyncio loop on a background thread."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.is_running():
            return
        self._loop = asyncio.new_event_loop()

        def _run() -> None:
            loop = self._loop
            if loop is None:  # pragma: no cover - defensive
                return
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.agent.run())
            except Exception:  # noqa: BLE001 - keep the tray alive
                pass
            finally:
                loop.close()

        self._thread = threading.Thread(target=_run, name="biounlock-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self.agent.request_stop)
        else:
            self.agent.request_stop()


# --- tray application -----------------------------------------------------


class TrayApp:
    """A tray icon plus an on-demand tkinter settings window."""

    def __init__(self) -> None:
        self.agent = Agent()
        self.runner = AgentRunner(self.agent)
        self._closing = False

        self._ui_queue: queue.Queue = queue.Queue()
        self._ui_ready = threading.Event()
        self._root = None
        self._settings = None
        self._url_var = None
        self._name_var = None
        self._status_var = None
        self._link_button = None
        self._qr_label = None
        self._pairing_label = None
        self._photo = None
        self._pairing_thread: threading.Thread | None = None
        self._logo_photo = None

        self.icon = pystray.Icon(
            "BioUnlock", create_icon_image(), "BioUnlock", menu=self._build_menu()
        )

        self._ui_thread = threading.Thread(target=self._ui_main, name="biounlock-ui", daemon=True)
        self._ui_thread.start()
        self._ui_ready.wait(timeout=10)

    # --- tkinter plumbing (all UI work happens on the UI thread) ----------

    def _ui_main(self) -> None:
        import tkinter as tk

        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("BioUnlock")
        self._ui_ready.set()
        self._root.after(50, self._pump)
        self._root.mainloop()

    def _pump(self) -> None:
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:  # noqa: BLE001 - one bad callback must not kill the pump
                pass
        if self._root is not None:
            self._root.after(50, self._pump)

    def post(self, callback) -> None:
        """Schedule ``callback`` to run on the UI thread."""
        self._ui_queue.put(callback)

    # --- menu -------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Open BioUnlock", self._on_open, default=True),
            pystray.MenuItem("Link this PC\u2026", self._on_open),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._agent_label, self._on_toggle_agent),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start at login", self._on_toggle_autostart, checked=lambda _item: is_autostart_enabled()
            ),
            pystray.MenuItem("Open log folder", self._on_open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _agent_label(self, _item) -> str:
        return "Stop agent" if self.runner.is_running() else "Start agent"

    def _on_open(self, _icon, _item) -> None:
        self.post(self._show_settings)

    def _on_toggle_agent(self, icon, _item) -> None:
        if self.runner.is_running():
            self.runner.stop()
        else:
            if not self.agent.config.is_enrolled:
                self.post(lambda: self._set_status("Link this PC before starting the agent."))
                self.post(self._show_settings)
                return
            self.runner.start()
        icon.update_menu()

    def _on_toggle_autostart(self, icon, _item) -> None:
        set_autostart(not is_autostart_enabled())
        icon.update_menu()

    def _on_open_logs(self, _icon, _item) -> None:
        home = default_home()
        home.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(home))  # noqa: S606

    def _on_quit(self, icon, _item) -> None:
        self._closing = True
        self.runner.stop()
        with_close = getattr(self.agent, "close", None)
        if callable(with_close):
            with_close()
        icon.stop()
        self.post(self._shutdown_ui)

    def _shutdown_ui(self) -> None:
        if self._root is not None:
            self._root.quit()

    # --- settings window --------------------------------------------------

    def _show_settings(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        if self._settings is not None and self._settings.winfo_exists():
            self._settings.deiconify()
            self._settings.lift()
            self._settings.focus_force()
            self._refresh_status()
            return

        window = tk.Toplevel(self._root)
        self._settings = window
        window.title("BioUnlock")
        window.geometry("460x640")
        window.protocol("WM_DELETE_WINDOW", self._hide_settings)

        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)

        logo = asset_path("logo.png")
        if logo is not None:
            try:
                logo_image = Image.open(logo).convert("RGBA")
                logo_image.thumbnail((56, 56), Image.LANCZOS)
                self._logo_photo = ImageTk.PhotoImage(logo_image)
                ttk.Label(frame, image=self._logo_photo).pack(anchor="w", pady=(0, 6))
            except Exception:  # noqa: BLE001 - the title alone is enough
                self._logo_photo = None

        ttk.Label(frame, text="BioUnlock", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Link this PC to your own BioUnlock server, then approve unlocks "
            "from your phone.",
            wraplength=400,
            justify="left",
        ).pack(anchor="w", pady=(2, 12))

        self._url_var = tk.StringVar(value=self.agent.config.server_url or "")
        self._name_var = tk.StringVar(value=self.agent.config.device_name or "")
        ttk.Label(frame, text="Server URL").pack(anchor="w")
        ttk.Entry(frame, textvariable=self._url_var).pack(fill="x", pady=(0, 8))
        ttk.Label(frame, text="PC name").pack(anchor="w")
        ttk.Entry(frame, textvariable=self._name_var).pack(fill="x", pady=(0, 12))

        self._link_button = ttk.Button(frame, text="Link this PC", command=self._on_link)
        self._link_button.pack(fill="x")

        self._pairing_label = ttk.Label(frame, text="", wraplength=400, justify="left")
        self._pairing_label.pack(anchor="w", pady=(10, 4))
        self._qr_label = ttk.Label(frame)
        self._qr_label.pack()

        password_button = ttk.Button(
            frame, text="Set Windows password\u2026", command=self._open_password_dialog
        )
        password_button.pack(fill="x", pady=(12, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Start agent", command=self._start_agent).pack(
            side="left", expand=True, fill="x"
        )
        ttk.Button(buttons, text="Stop agent", command=self._stop_agent).pack(
            side="left", expand=True, fill="x", padx=(6, 0)
        )
        ttk.Button(frame, text="Unlink", command=self._unlink).pack(fill="x", pady=(6, 0))

        self._status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self._status_var, wraplength=400, justify="left").pack(
            anchor="w", pady=(12, 0)
        )

        self._refresh_status()
        window.after(1000, self._tick)

    def _hide_settings(self) -> None:
        if self._settings is not None:
            self._settings.withdraw()

    def _tick(self) -> None:
        if self._settings is None or not self._settings.winfo_exists():
            return
        self._refresh_status()
        self._settings.after(1000, self._tick)

    def _set_status(self, text: str) -> None:
        if self._status_var is not None:
            self._status_var.set(text)

    def _refresh_status(self) -> None:
        status = self.agent.status()
        state = "running" if self.runner.is_running() else "stopped"
        linked = "linked" if status.paired else ("enrolled, not linked" if status.enrolled else "not linked")
        parts = [f"Agent: {state} | {linked}"]
        if status.credential_enrolled:
            parts.append("Windows password: stored")
        else:
            parts.append("Windows password: not set (needed to really unlock)")
        if status.device_id:
            parts.append(f"Device: {status.device_name} ({status.device_id})")
        if status.server_url:
            parts.append(f"Server: {status.server_url}")
        if status.last_error:
            parts.append(f"Last error: {status.last_error}")
        self._set_status("\n".join(parts))

    # --- linking ----------------------------------------------------------

    def _on_link(self) -> None:
        url = (self._url_var.get() if self._url_var else "").strip()
        name = (self._name_var.get() if self._name_var else "").strip()
        if not url:
            self._set_status("Enter the server URL first.")
            return
        if self.runner.is_running():
            self.runner.stop()
        if self._link_button is not None:
            self._link_button.config(state="disabled")
        self._set_status("Linking\u2026")
        threading.Thread(target=self._enroll_worker, args=(url, name), daemon=True).start()

    def _enroll_worker(self, url: str, name: str) -> None:
        try:
            enrollment = self.agent.enroll(url, device_name=name or None)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self.post(lambda error=str(exc): self._on_link_failed(error))
            return
        self.post(lambda: self._on_enrolled(enrollment.pairing_code, enrollment.qr_payload))
        self._start_pairing_watch()

    def _start_pairing_watch(self) -> None:
        """Watch for a phone-side pairing without blocking the UI or exiting early."""
        if self._pairing_thread is not None and self._pairing_thread.is_alive():
            return
        self._pairing_thread = threading.Thread(
            target=watch_for_pairing,
            args=(self.agent,),
            kwargs={
                "closing": lambda: self._closing,
                "on_paired": lambda: self.post(self._on_paired),
            },
            name="biounlock-pairing",
            daemon=True,
        )
        self._pairing_thread.start()

    def _on_enrolled(self, pairing_code: str, qr_payload: str) -> None:
        if self._link_button is not None:
            self._link_button.config(state="normal")
        if self._pairing_label is not None:
            self._pairing_label.config(
                text=f"Scan this code with the BioUnlock app (or enter it):\n{pairing_code}\n"
                "Waiting for the phone to confirm\u2026"
            )
        self._show_qr(qr_payload)
        self._refresh_status()

    def _on_paired(self) -> None:
        if self._pairing_label is not None:
            self._pairing_label.config(text="Paired. Restarting BioUnlock\u2026")
        self._set_status("Linked. Restarting the app to finish\u2026")
        self._restart_app()

    def _restart_app(self) -> None:
        """Relaunch the tray so the freshly paired state takes effect cleanly.

        Users found that a manual restart was needed after linking, so we do it
        for them: launch a replacement copy, hand over the single-instance lock,
        and quit this one. If the relaunch fails we stay alive and just start the
        agent instead, so the PC still works.
        """
        self._closing = True
        try:
            self.runner.stop()
        except Exception:  # noqa: BLE001 - never block the restart
            pass
        _release_single_instance()
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
            )
        try:
            subprocess.Popen(  # noqa: S603 - fixed, self-authored command line
                _relaunch_arguments(),
                cwd=_relaunch_working_dir(),
                creationflags=creationflags,
                close_fds=True,
            )
        except Exception as exc:  # noqa: BLE001 - fall back to running in place
            logger.error("Could not restart BioUnlock: %s", exc)
            _acquire_single_instance()
            self._closing = False
            self._set_status("Linked. The agent is starting.")
            if not self.runner.is_running():
                self.runner.start()
            self.icon.update_menu()
            self._refresh_status()
            return
        self.icon.stop()
        self.post(self._shutdown_ui)

    def _on_link_failed(self, message: str) -> None:
        if self._link_button is not None:
            self._link_button.config(state="normal")
        self._set_status(f"Linking failed: {message}")

    def _show_qr(self, payload: str) -> None:
        if self._qr_label is None:
            return
        try:
            image = render_qr_image(payload)
        except Exception:  # noqa: BLE001
            self._qr_label.configure(text="(Could not render QR code.)")
            return
        if image is None:
            self._qr_label.configure(text="(Install 'segno' to show a QR code.)")
            return
        try:
            self._photo = ImageTk.PhotoImage(image)
            self._qr_label.configure(image=self._photo, text="")
        except Exception:  # noqa: BLE001
            self._qr_label.configure(text="(Could not render QR code.)")

    # --- credential / agent controls --------------------------------------

    def _open_password_dialog(self) -> None:
        import getpass
        import tkinter as tk
        from tkinter import ttk

        dialog = tk.Toplevel(self._root)
        dialog.title("Windows password")
        dialog.geometry("400x280")
        dialog.transient(self._settings)

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="Stored locally (DPAPI-protected) and only submitted by the "
            "Credential Provider at unlock time. It is never sent to the server.",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        default_user = os.environ.get("USERNAME") or getpass.getuser()
        default_domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or ""
        user_var = tk.StringVar(value=default_user)
        domain_var = tk.StringVar(value=default_domain)
        password_var = tk.StringVar()

        for label, var, secret in (
            ("Windows username", user_var, False),
            ("Domain / computer", domain_var, False),
            ("Windows password", password_var, True),
        ):
            ttk.Label(frame, text=label).pack(anchor="w")
            ttk.Entry(frame, textvariable=var, show="*" if secret else "").pack(
                fill="x", pady=(0, 8)
            )

        def save() -> None:
            password = password_var.get()
            if not password:
                ttk.Label(frame, text="Password cannot be empty.").pack(anchor="w")
                return
            credential = unlock.WindowsCredential(
                username=user_var.get().strip(),
                password=password,
                domain=domain_var.get().strip(),
            )
            try:
                unlock.save_windows_credential(default_home(), credential)
            except unlock.UnlockError as exc:
                ttk.Label(frame, text=f"Could not store: {exc}").pack(anchor="w")
                return
            password_var.set("")
            dialog.destroy()
            self._set_status("Windows password stored.")
            self._refresh_status()

        ttk.Button(frame, text="Save", command=save).pack(fill="x", pady=(4, 0))

    def _start_agent(self) -> None:
        if not self.agent.config.is_enrolled:
            self._set_status("Link this PC first.")
            return
        self.runner.start()
        self.icon.update_menu()
        self._refresh_status()

    def _stop_agent(self) -> None:
        self.runner.stop()
        self.icon.update_menu()
        self._refresh_status()

    def _unlink(self) -> None:
        from tkinter import messagebox

        if not messagebox.askyesno("BioUnlock", "Remove the local link and device key?"):
            return
        self.runner.stop()
        self.agent.unenroll()
        if self._url_var is not None:
            self._url_var.set("")
        if self._pairing_label is not None:
            self._pairing_label.config(text="")
        if self._qr_label is not None:
            self._qr_label.configure(image="")
        self.icon.update_menu()
        self._refresh_status()

    # --- lifecycle --------------------------------------------------------

    def run(self) -> None:
        if self.agent.config.is_enrolled and self.agent.config.is_paired:
            self.runner.start()
        elif self.agent.config.is_enrolled:
            # Enrolled but waiting on the phone: keep watching so a pairing that
            # happens later (or after the link window) is picked up on its own.
            self._start_pairing_watch()
        self.icon.run()


def main() -> int:
    if not _acquire_single_instance():
        # Another BioUnlock is already in the tray; step aside quietly.
        return 0
    configure_logging("INFO", default_home() / "agent.log")
    try:
        app = TrayApp()
    except Exception as exc:  # noqa: BLE001 - report a clean startup failure
        print(f"Could not start the BioUnlock tray app: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
