"""Taskbar tray application for the BioUnlock PC agent.

The tray app is the recommended way to run BioUnlock on Windows. It:

* lives in the notification area (system tray) and starts the agent in the
  background as soon as the PC is linked;
* provides a small settings window that mirrors the phone app's look and feel
  (flat surfaces, one blue accent, card layout) to enter the server URL, link
  this PC (pairing QR/code), and store the Windows credential used for
  unlocking;
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
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
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
THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# Kept alive for the whole process so Windows does not release the lock early.
_instance_mutex: object | None = None


# --- theme ----------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """Flat colour set shared with the phone app (one accent, neutral surfaces)."""

    bg: str
    card: str
    border: str
    subtle: str
    text: str
    muted: str
    accent: str
    on_accent: str
    accent_hover: str
    success: str
    warning: str
    danger: str
    ok_bg: str
    warn_bg: str
    err_bg: str
    scroll_thumb: str
    scroll_thumb_active: str


def apps_use_light_theme() -> bool:
    """Whether Windows is set to light app mode (defaults to light)."""
    if winreg is None:  # pragma: no cover - non-Windows
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
    except OSError:
        return True


def palette_for(light: bool) -> Palette:
    """Return the flat palette for the given Windows app theme."""
    if light:
        return Palette(
            bg="#F4F5F7",
            card="#FFFFFF",
            border="#E3E6EB",
            subtle="#EEF1F5",
            text="#1A1D20",
            muted="#5B6470",
            accent="#2F6FEB",
            on_accent="#FFFFFF",
            accent_hover="#255BC7",
            success="#1E9E62",
            warning="#B7791F",
            danger="#D64545",
            ok_bg="#E3F5EC",
            warn_bg="#FBF1DD",
            err_bg="#FBE9E9",
            scroll_thumb="#CDD3DB",
            scroll_thumb_active="#9AA4B2",
        )
    return Palette(
        bg="#0F1113",
        card="#1A1D20",
        border="#2A2F35",
        subtle="#22262B",
        text="#F2F4F7",
        muted="#9AA4B2",
        accent="#6E9DF7",
        on_accent="#0B0D10",
        accent_hover="#8AAFFA",
        success="#4ADE80",
        warning="#FACC15",
        danger="#F87171",
        ok_bg="#12301F",
        warn_bg="#2E2711",
        err_bg="#331A1A",
        scroll_thumb="#333A42",
        scroll_thumb_active="#4A525C",
    )


class FlatScrollbar(tk.Canvas):
    """A slim, arrow-free scrollbar drawn to match the flat card theme.

    Behaves like a normal scrollbar: ``set`` is wired to the scrolled widget's
    ``yscrollcommand``, and the thumb can be dragged or the track clicked to page.
    """

    def __init__(self, master, command, *, palette: Palette, width: int = 10, **kwargs) -> None:
        super().__init__(master, width=width, highlightthickness=0, bd=0, bg=palette.bg, **kwargs)
        self._command = command
        self._p = palette
        self._first = 0.0
        self._last = 1.0
        self._thumb: tuple[float, float] | None = None
        self._drag_origin: float | None = None
        self._drag_first = 0.0
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda _e: self._end_drag())

    def set(self, first, last) -> None:  # noqa: A003 - matches Tk's scrollbar contract
        self._first, self._last = float(first), float(last)
        self._redraw()

    def _round_rect(self, x0, y0, x1, y1, r, **kwargs):
        points = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _redraw(self) -> None:
        self.delete("all")
        height = self.winfo_height()
        width = self.winfo_width()
        if height <= 1 or width <= 1:
            return
        if self._first <= 0.0 and self._last >= 1.0:
            self._thumb = None
            return
        pad = 2
        track_top = pad
        track_height = (height - 2 * pad) or 1
        thumb_top = track_top + track_height * self._first
        thumb_bottom = track_top + track_height * self._last
        min_height = min(28, track_height)
        if thumb_bottom - thumb_top < min_height:
            thumb_bottom = thumb_top + min_height
            if thumb_bottom > height - pad:
                thumb_bottom = height - pad
                thumb_top = thumb_bottom - min_height
        self._thumb = (thumb_top, thumb_bottom)
        fill = self._p.scroll_thumb_active if self._drag_origin is not None else self._p.scroll_thumb
        self._round_rect(pad, thumb_top, width - pad, thumb_bottom, (width - 2 * pad) / 2, fill=fill, outline="")

    def _on_press(self, event) -> None:
        if self._thumb is None:
            return
        top, bottom = self._thumb
        if top <= event.y <= bottom:
            self._drag_origin = event.y
            self._drag_first = self._first
            self._redraw()
        else:
            step = 0.1 if event.y > bottom else -0.1
            self._command("moveto", max(0.0, min(1.0, self._first + step)))

    def _on_drag(self, event) -> None:
        if self._drag_origin is None:
            return
        height = self.winfo_height()
        track_height = (height - 4) or 1
        fraction = (event.y - self._drag_origin) / track_height
        max_first = max(0.0, 1.0 - (self._last - self._first))
        self._command("moveto", max(0.0, min(max_first, self._drag_first + fraction)))

    def _end_drag(self) -> None:
        self._drag_origin = None
        self._redraw()


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


def _relaunch_environment() -> dict[str, str]:
    """Environment for the replacement copy of a packaged app.

    PyInstaller's onefile bootloader tells its child which extraction folder to
    reuse through ``_PYI_*`` variables. This process deletes that folder as it
    exits, so a child that inherits them imports from a directory that is
    vanishing underneath it and dies with a misleading ``No module named ...``
    or ``DLL load failed``. Dropping them makes the replacement extract its own
    files into a fresh folder instead.
    """
    env = dict(os.environ)
    if not getattr(sys, "frozen", False):  # pragma: no cover - source run
        return env
    for key in [key for key in env if key.startswith("_PYI_")]:
        del env[key]
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


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
    """A tray icon plus an on-demand settings window that matches the phone app."""

    def __init__(self) -> None:
        self.agent = Agent()
        self.runner = AgentRunner(self.agent)
        self._closing = False
        self._p = palette_for(apps_use_light_theme())

        self._ui_queue: queue.Queue = queue.Queue()
        self._ui_ready = threading.Event()
        self._root = None
        self._settings = None

        # Form state.
        self._url_var = None
        self._name_var = None
        self._token_var = None
        self._autostart_var = None
        self._hint_var = None

        # Widgets refreshed live (kept as attributes so they are updated in place).
        self._link_pill = None
        self._agent_pill = None
        self._meta_label = None
        self._error_label = None
        self._link_button = None
        self._unlink_button = None
        self._start_button = None
        self._stop_button = None
        self._pairing_pill = None
        self._pairing_code = None
        self._pairing_hint = None
        self._qr_label = None
        self._credential_pill = None

        self._photo = None
        self._logo_photo = None
        self._window_icon = None
        self._pairing_thread: threading.Thread | None = None

        self.icon = pystray.Icon(
            "BioUnlock", create_icon_image(), "BioUnlock", menu=self._build_menu()
        )

        self._ui_thread = threading.Thread(target=self._ui_main, name="biounlock-ui", daemon=True)
        self._ui_thread.start()
        self._ui_ready.wait(timeout=10)

    # --- tkinter plumbing (all UI work happens on the UI thread) ----------

    def _ui_main(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("BioUnlock")
        self._apply_icon(self._root)
        self._ui_ready.set()
        self._root.after(50, self._pump)
        self._root.mainloop()

    def _apply_icon(self, window) -> None:
        """Give a window BioUnlock's icon (title bar and taskbar where relevant)."""
        ico = asset_path("BioUnlock.ico")
        if ico is not None and os.name == "nt":
            try:
                window.iconbitmap(default=str(ico))
                return
            except tk.TclError:
                pass
        logo = asset_path("logo.png")
        if logo is not None:
            try:
                image = Image.open(logo).convert("RGBA").resize((64, 64), Image.LANCZOS)
                self._window_icon = ImageTk.PhotoImage(image)
                window.iconphoto(True, self._window_icon)
            except Exception:  # noqa: BLE001 - icon is cosmetic
                pass

    def _pump(self) -> None:
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:  # noqa: BLE001 - one bad callback must not kill the pump
                logger.exception("UI callback failed")
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
        if self._autostart_var is not None:
            self._autostart_var.set(is_autostart_enabled())
        icon.update_menu()

    def _on_autostart_changed(self) -> None:
        if self._autostart_var is None:
            return
        set_autostart(bool(self._autostart_var.get()))
        self.icon.update_menu()

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

    # --- reusable flat widgets -------------------------------------------

    def _card(self, parent) -> tk.Frame:
        """A flat surface with a hairline border, returning its content frame."""
        p = self._p
        outer = tk.Frame(parent, bg=p.border)
        outer.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(outer, bg=p.card)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        content = tk.Frame(inner, bg=p.card)
        content.pack(fill="both", expand=True, padx=16, pady=14)
        return content

    def _card_title(self, parent, text: str) -> tk.Label:
        p = self._p
        label = tk.Label(
            parent,
            text=text.upper(),
            font=("Segoe UI", 8, "bold"),
            fg=p.muted,
            bg=p.card,
            anchor="w",
        )
        label.pack(fill="x", pady=(0, 10))
        return label

    def _pill(self, parent, text: str, tone: str = "neutral") -> tk.Label:
        bg, fg = self._pill_colors(tone)
        return tk.Label(
            parent,
            text=f"  {text}  ",
            font=("Segoe UI", 9, "bold"),
            fg=fg,
            bg=bg,
            padx=8,
            pady=3,
        )

    def _pill_colors(self, tone: str) -> tuple[str, str]:
        p = self._p
        if tone == "ok":
            return p.ok_bg, p.success
        if tone == "warn":
            return p.warn_bg, p.warning
        if tone == "err":
            return p.err_bg, p.danger
        return p.subtle, p.muted

    def _set_pill(self, label: tk.Label | None, text: str, tone: str) -> None:
        if label is None:
            return
        bg, fg = self._pill_colors(tone)
        label.configure(text=f"  {text}  ", bg=bg, fg=fg)

    def _field(self, parent, label: str, var: tk.StringVar, *, secret: bool = False, helper: str | None = None) -> tk.Entry:
        p = self._p
        tk.Label(parent, text=label, font=("Segoe UI", 9), fg=p.muted, bg=p.card, anchor="w").pack(fill="x")
        entry = tk.Entry(
            parent,
            textvariable=var,
            font=("Segoe UI", 10),
            fg=p.text,
            bg=p.subtle,
            insertbackground=p.text,
            relief="flat",
            show="\u2022" if secret else "",
            highlightthickness=1,
            highlightbackground=p.border,
            highlightcolor=p.accent,
        )
        entry.pack(fill="x", ipady=6, pady=(3, 0 if helper else 12))
        if helper:
            tk.Label(
                parent, text=helper, font=("Segoe UI", 8), fg=p.muted, bg=p.card,
                anchor="w", justify="left", wraplength=360,
            ).pack(fill="x", pady=(4, 12))
        return entry

    def _button(self, parent, text: str, command, *, kind: str = "accent") -> tk.Button:
        p = self._p
        if kind == "accent":
            bg, fg, hover, weight = p.accent, p.on_accent, p.accent_hover, "bold"
        else:
            bg, fg, hover, weight = p.subtle, p.text, p.border, "normal"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 10, weight),
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            disabledforeground=p.muted,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=8,
            borderwidth=0,
            highlightthickness=0,
        )
        return button

    # --- settings window --------------------------------------------------

    def _show_settings(self) -> None:
        if self._settings is not None and self._settings.winfo_exists():
            self._settings.deiconify()
            self._settings.lift()
            self._settings.focus_force()
            self._refresh_status()
            return

        window = tk.Toplevel(self._root)
        self._settings = window
        window.title("BioUnlock")
        window.geometry("480x760")
        window.minsize(420, 560)
        window.configure(bg=self._p.bg)
        window.protocol("WM_DELETE_WINDOW", self._hide_settings)
        self._apply_icon(window)
        self._build_settings(window)
        self._refresh_status()
        window.after(1000, self._tick)

    def _build_settings(self, window: tk.Toplevel) -> None:
        p = self._p

        header = tk.Frame(window, bg=p.bg)
        header.pack(fill="x", padx=20, pady=(18, 10))
        self._add_logo(header, 48)
        title_box = tk.Frame(header, bg=p.bg)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(title_box, text="BioUnlock", font=("Segoe UI", 17, "bold"), fg=p.text, bg=p.bg, anchor="w").pack(
            fill="x"
        )
        tk.Label(
            title_box,
            text="Unlock this PC from your phone.",
            font=("Segoe UI", 9),
            fg=p.muted,
            bg=p.bg,
            anchor="w",
        ).pack(fill="x")

        body_wrap = tk.Frame(window, bg=p.bg)
        body_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(body_wrap, bg=p.bg, highlightthickness=0, bd=0)
        scrollbar = FlatScrollbar(body_wrap, canvas.yview, palette=p, width=10)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(6, 0))
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=p.bg)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        window.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        pad = tk.Frame(body, bg=p.bg)
        pad.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Status summary.
        status_card = self._card(pad)
        row = tk.Frame(status_card, bg=p.card)
        row.pack(fill="x")
        self._link_pill = self._pill(row, "Not linked", "neutral")
        self._link_pill.pack(side="left")
        self._agent_pill = self._pill(row, "Agent stopped", "neutral")
        self._agent_pill.pack(side="right")
        self._meta_label = tk.Label(
            status_card, text="", font=("Segoe UI", 9), fg=p.muted, bg=p.card,
            anchor="w", justify="left", wraplength=380,
        )
        self._meta_label.pack(fill="x", pady=(10, 0))
        self._error_label = tk.Label(
            status_card, text="", font=("Segoe UI", 9), fg=p.danger, bg=p.card,
            anchor="w", justify="left", wraplength=380,
        )
        self._error_label.pack(fill="x", pady=(6, 0))

        # Server + linking.
        server_card = self._card(pad)
        self._card_title(server_card, "Server")
        self._url_var = tk.StringVar(value=self.agent.config.server_url or "")
        self._name_var = tk.StringVar(value=self.agent.config.device_name or "")
        self._token_var = tk.StringVar()
        self._field(server_card, "Server URL", self._url_var)
        self._field(
            server_card,
            "API key",
            self._token_var,
            secret=True,
            helper="Required once to link this PC. Stored locally and reused for re-links.",
        )
        self._field(server_card, "PC name", self._name_var)
        self._link_button = self._button(server_card, "Link this PC", self._on_link, kind="accent")
        self._link_button.pack(fill="x", pady=(2, 0))
        self._unlink_button = self._button(server_card, "Unlink this PC", self._unlink, kind="secondary")
        self._unlink_button.pack(fill="x", pady=(8, 0))

        # Pairing.
        pairing_card = self._card(pad)
        self._card_title(pairing_card, "Pairing")
        self._pairing_pill = self._pill(pairing_card, "Not started", "neutral")
        self._pairing_pill.pack(anchor="w")
        self._qr_label = tk.Label(pairing_card, bg=p.card)
        self._qr_label.pack(pady=(10, 4))
        self._pairing_code = tk.Label(
            pairing_card, text="", font=("Consolas", 15, "bold"), fg=p.text, bg=p.card, anchor="w"
        )
        self._pairing_code.pack(fill="x")
        self._pairing_hint = tk.Label(
            pairing_card, text="", font=("Segoe UI", 9), fg=p.muted, bg=p.card,
            anchor="w", justify="left", wraplength=380,
        )
        self._pairing_hint.pack(fill="x", pady=(6, 0))

        # Windows credential.
        cred_card = self._card(pad)
        self._card_title(cred_card, "Windows password")
        self._credential_pill = self._pill(cred_card, "Not set", "warn")
        self._credential_pill.pack(anchor="w")
        tk.Label(
            cred_card,
            text="Stored locally (DPAPI-protected) and only used by the Windows "
            "sign-in screen. It is never sent to the server.",
            font=("Segoe UI", 9),
            fg=p.muted,
            bg=p.card,
            anchor="w",
            justify="left",
            wraplength=380,
        ).pack(fill="x", pady=(10, 10))
        self._button(cred_card, "Set Windows password\u2026", self._open_password_dialog, kind="secondary").pack(
            fill="x"
        )

        # Agent controls.
        agent_card = self._card(pad)
        self._card_title(agent_card, "Agent")
        agent_row = tk.Frame(agent_card, bg=p.card)
        agent_row.pack(fill="x")
        self._start_button = self._button(agent_row, "Start", self._start_agent, kind="accent")
        self._start_button.pack(side="left", fill="x", expand=True)
        self._stop_button = self._button(agent_row, "Stop", self._stop_agent, kind="secondary")
        self._stop_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        tk.Checkbutton(
            agent_card,
            text="Start automatically at login",
            variable=self._autostart_var,
            command=self._on_autostart_changed,
            font=("Segoe UI", 9),
            fg=p.text,
            bg=p.card,
            activebackground=p.card,
            activeforeground=p.text,
            selectcolor=p.card,
            anchor="w",
            cursor="hand2",
            highlightthickness=0,
            bd=0,
        ).pack(fill="x", pady=(12, 0))

        # Transient hint + footer.
        self._hint_var = tk.StringVar(value="")
        tk.Label(
            pad, textvariable=self._hint_var, font=("Segoe UI", 9), fg=p.muted,
            bg=p.bg, anchor="w", justify="left", wraplength=380,
        ).pack(fill="x", pady=(0, 8))
        logs = tk.Label(
            pad,
            text="Open log folder",
            font=("Segoe UI", 9, "underline"),
            fg=p.accent,
            bg=p.bg,
            cursor="hand2",
            anchor="w",
        )
        logs.pack(fill="x")
        logs.bind("<Button-1>", lambda _e: self._on_open_logs(None, None))

    def _add_logo(self, parent, size: int) -> None:
        logo = asset_path("logo.png")
        if logo is None:
            return
        try:
            image = Image.open(logo).convert("RGBA").resize((size, size), Image.LANCZOS)
            self._logo_photo = ImageTk.PhotoImage(image)
            tk.Label(parent, image=self._logo_photo, bg=self._p.bg).pack(side="left", padx=(0, 12))
        except Exception:  # noqa: BLE001 - the title alone is enough
            self._logo_photo = None

    def _hide_settings(self) -> None:
        if self._settings is not None:
            self._settings.withdraw()

    def _tick(self) -> None:
        if self._settings is None or not self._settings.winfo_exists():
            return
        self._refresh_status()
        self._settings.after(1000, self._tick)

    def _set_status(self, text: str) -> None:
        if self._hint_var is not None:
            self._hint_var.set(text)

    def _refresh_status(self) -> None:
        if self._link_pill is None:
            return
        status = self.agent.status()
        running = self.runner.is_running()

        if status.paired:
            self._set_pill(self._link_pill, "Linked", "ok")
        elif status.enrolled:
            self._set_pill(self._link_pill, "Awaiting phone", "warn")
        else:
            self._set_pill(self._link_pill, "Not linked", "neutral")
        self._set_pill(self._agent_pill, "Agent running" if running else "Agent stopped", "ok" if running else "neutral")

        bits: list[str] = []
        if status.server_url:
            bits.append(status.server_url)
        if status.connected:
            bits.append("connected")
        plural = "" if status.processed_count == 1 else "s"
        bits.append(f"{status.processed_count} request{plural} handled")
        self._meta_label.configure(text="  \u00b7  ".join(bits))
        self._error_label.configure(text=status.last_error or "")

        self._set_pill(self._credential_pill, "Stored" if status.credential_enrolled else "Not set",
                       "ok" if status.credential_enrolled else "warn")

        if status.paired:
            self._set_pill(self._pairing_pill, "Paired", "ok")
            self._pairing_code.configure(text="")
            self._pairing_hint.configure(text="This PC is paired. Approve unlock requests from your phone.")
            self._qr_label.configure(image="", text="")
        elif status.enrolled:
            self._set_pill(self._pairing_pill, "Waiting for the phone", "warn")
            self._pairing_hint.configure(
                text="Scan the code with the BioUnlock app, or enter the code below. "
                "Waiting for the phone to confirm\u2026"
            )
        else:
            self._set_pill(self._pairing_pill, "Not started", "neutral")
            self._pairing_code.configure(text="")
            self._pairing_hint.configure(text="Link this PC to get a pairing code.")
            self._qr_label.configure(image="", text="")

        if status.enrolled:
            self._unlink_button.pack(fill="x", pady=(8, 0))
        else:
            self._unlink_button.pack_forget()
        self._start_button.configure(state="normal" if (status.enrolled and not running) else "disabled")
        self._stop_button.configure(state="normal" if running else "disabled")

    # --- linking ----------------------------------------------------------

    def _on_link(self) -> None:
        url = (self._url_var.get() if self._url_var else "").strip()
        name = (self._name_var.get() if self._name_var else "").strip()
        token = (self._token_var.get() if self._token_var else "").strip()
        if not url:
            self._set_status("Enter the server URL first.")
            return
        if self.runner.is_running():
            self.runner.stop()
        if self._link_button is not None:
            self._link_button.config(state="disabled")
        self._set_status("Linking\u2026")
        threading.Thread(target=self._enroll_worker, args=(url, name, token), daemon=True).start()

    def _enroll_worker(self, url: str, name: str, token: str) -> None:
        try:
            enrollment = self.agent.enroll(url, device_name=name or None, api_token=token or None)
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
        if self._pairing_code is not None:
            self._pairing_code.configure(text=pairing_code)
        self._show_qr(qr_payload)
        self._set_status("Enrolled. Waiting for the phone to confirm\u2026")
        self._refresh_status()

    def _on_paired(self) -> None:
        self._set_status("Paired. Restarting BioUnlock\u2026")
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
                env=_relaunch_environment(),
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
            self._qr_label.configure(image="", text="(Could not render QR code.)")
            return
        if image is None:
            self._qr_label.configure(image="", text="(Install 'segno' to show a QR code.)")
            return
        try:
            self._photo = ImageTk.PhotoImage(image)
            self._qr_label.configure(image=self._photo, text="")
        except Exception:  # noqa: BLE001
            self._qr_label.configure(image="", text="(Could not render QR code.)")

    # --- credential / agent controls --------------------------------------

    def _open_password_dialog(self) -> None:
        import getpass

        p = self._p
        dialog = tk.Toplevel(self._root)
        dialog.title("Windows password")
        dialog.geometry("420x400")
        dialog.configure(bg=p.bg)
        dialog.transient(self._settings)
        self._apply_icon(dialog)

        frame = tk.Frame(dialog, bg=p.bg)
        frame.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(
            frame, text="Windows sign-in password", font=("Segoe UI", 14, "bold"), fg=p.text, bg=p.bg, anchor="w"
        ).pack(fill="x")
        tk.Label(
            frame,
            text="Stored locally (DPAPI-protected) and only submitted by the Windows "
            "sign-in screen at unlock time. It is never sent to the server.",
            font=("Segoe UI", 9),
            fg=p.muted,
            bg=p.bg,
            anchor="w",
            justify="left",
            wraplength=380,
        ).pack(fill="x", pady=(6, 14))

        body = self._card(frame)
        default_user = os.environ.get("USERNAME") or getpass.getuser()
        default_domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or ""
        user_var = tk.StringVar(value=default_user)
        domain_var = tk.StringVar(value=default_domain)
        password_var = tk.StringVar()
        self._field(body, "Windows username", user_var)
        self._field(body, "Domain / computer", domain_var)
        self._field(body, "Windows password", password_var, secret=True)

        error_label = tk.Label(body, text="", font=("Segoe UI", 9), fg=p.danger, bg=p.card, anchor="w", justify="left", wraplength=340)
        error_label.pack(fill="x")

        def save() -> None:
            password = password_var.get()
            if not password:
                error_label.configure(text="Password cannot be empty.")
                return
            credential = unlock.WindowsCredential(
                username=user_var.get().strip(),
                password=password,
                domain=domain_var.get().strip(),
            )
            try:
                unlock.save_windows_credential(default_home(), credential)
            except unlock.UnlockError as exc:
                error_label.configure(text=f"Could not store: {exc}")
                return
            password_var.set("")
            dialog.destroy()
            self._set_status("Windows password stored.")
            self._refresh_status()

        self._button(frame, "Save", save, kind="accent").pack(fill="x", pady=(10, 0))

    def _start_agent(self) -> None:
        if not self.agent.config.is_enrolled:
            self._set_status("Link this PC first.")
            return
        self.runner.start()
        self._set_status("")
        self.icon.update_menu()
        self._refresh_status()

    def _stop_agent(self) -> None:
        self.runner.stop()
        self.icon.update_menu()
        self._refresh_status()

    def _unlink(self) -> None:
        from tkinter import messagebox

        if not messagebox.askyesno("BioUnlock", "Remove the local link and device key from this PC?"):
            return
        self.runner.stop()
        self.agent.unenroll()
        if self._url_var is not None:
            self._url_var.set("")
        if self._pairing_code is not None:
            self._pairing_code.configure(text="")
        if self._qr_label is not None:
            self._qr_label.configure(image="", text="")
        self._set_status("Unlinked from the server.")
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
