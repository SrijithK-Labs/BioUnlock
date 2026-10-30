"""Setup wizard for the BioUnlock tray app.

A small tkinter wizard (Welcome, Options, Installing, Finish) around
:func:`biounlock_agent.installer.install_core`. The install runs on a worker
thread so the window keeps painting while the single UAC prompt is open, and
progress arrives through a queue polled with ``after``.
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

from biounlock_agent.installer import InstallOptions, InstallResult, install_core, install_dir
from biounlock_agent.theme import Palette, apps_use_light_theme, palette_for

logger = logging.getLogger(__name__)

WIZARD_TITLE = "BioUnlock Setup"
WINDOW_WIDTH = 680
WINDOW_HEIGHT = 600
FONT = "Segoe UI"
LOG_LINES = 6


class InstallerUiUnavailable(RuntimeError):
    """Raised when Tk cannot open a window (headless or broken install)."""


def _asset(name: str) -> Path | None:
    candidates = [Path(__file__).resolve().parent / "assets" / name]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "assets" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _enable_dpi_awareness() -> None:
    if os.name != "nt":  # pragma: no cover - non-Windows
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - already set, or an old Windows build
        pass


def run_installer(options: InstallOptions | None = None) -> InstallResult | None:
    """Show the wizard and return the install result, or ``None`` if cancelled."""
    _enable_dpi_awareness()
    try:
        app = InstallerApp(options)
    except tk.TclError as exc:  # no display / Tk missing from the build
        raise InstallerUiUnavailable(f"Could not open the setup window: {exc}") from exc
    return app.run()


class _ProgressBar(tk.Canvas):
    """Slim indeterminate bar drawn in the same flat style as the tray."""

    def __init__(self, master: tk.Misc, palette: Palette, *, height: int = 6) -> None:
        super().__init__(
            master,
            height=height,
            bg=palette.subtle,
            highlightthickness=0,
            bd=0,
        )
        self._width = height
        self._p = palette
        self._offset = 0
        self._running = False
        self._chunk = self.create_rectangle(0, 0, 0, height, fill=palette.accent, width=0)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tick()

    def stop(self) -> None:
        self._running = False

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            width = self.winfo_width()
        except tk.TclError:  # pragma: no cover - window already gone
            return
        if width <= 1:
            width = int(self.cget("width")) or 1
        span = max(70, width // 3)
        x = self._offset % (width + span) - span
        self.coords(self._chunk, x, 0, x + span, self._width)
        self._offset += 7
        self.after(16, self._tick)


class _CheckRow(tk.Frame):
    """A flat checkbox row: square box, title, and a muted description."""

    def __init__(
        self,
        master: tk.Misc,
        palette: Palette,
        title: str,
        description: str = "",
        *,
        value: bool = True,
    ) -> None:
        super().__init__(master, bg=palette.card, cursor="hand2")
        self._p = palette
        self.value = value

        self._box = tk.Canvas(
            self,
            width=20,
            height=20,
            bg=palette.card,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._box.pack(side="left", anchor="n", padx=(0, 12), pady=2)

        text = tk.Frame(self, bg=palette.card, cursor="hand2")
        text.pack(side="left", fill="x", expand=True)
        self._title = tk.Label(
            text,
            text=title,
            font=(FONT, 10, "bold"),
            fg=palette.text,
            bg=palette.card,
            anchor="w",
            cursor="hand2",
        )
        self._title.pack(fill="x")
        self._description: tk.Label | None = None
        if description:
            self._description = tk.Label(
                text,
                text=description,
                font=(FONT, 9),
                fg=palette.muted,
                bg=palette.card,
                anchor="w",
                justify="left",
                wraplength=500,
                cursor="hand2",
            )
            self._description.pack(fill="x", pady=(2, 0))

        for widget in (self, self._box, text, self._title, self._description):
            if widget is not None:
                widget.bind("<Button-1>", self._toggle)

        self._draw()

    def _toggle(self, _event: tk.Event | None = None) -> None:
        self.value = not self.value
        self._draw()

    def _draw(self) -> None:
        p = self._p
        self._box.delete("all")
        if self.value:
            self._box.create_rectangle(2, 2, 18, 18, fill=p.accent, outline=p.accent)
            self._box.create_line(5, 10, 8, 14, 15, 6, fill=p.on_accent, width=2)
        else:
            self._box.create_rectangle(2, 2, 18, 18, fill=p.card, outline=p.border, width=2)


class InstallerApp:
    """The wizard window. Call :meth:`run` and read :attr:`result` afterwards."""

    def __init__(self, options: InstallOptions | None = None) -> None:
        self.options = options or InstallOptions()
        self.result: InstallResult | None = None
        self._p = palette_for(apps_use_light_theme())
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._busy = False
        self._poll_id: str | None = None
        self._bar: _ProgressBar | None = None
        self._buttons: list[tk.Widget] = []
        self._checks: dict[str, _CheckRow] = {}
        self._log_rows: list[tk.Frame] = []
        self._step_label: tk.Label | None = None
        self._current_step_label: tk.Label | None = None

        self.root = tk.Tk()
        self._logo: tk.PhotoImage | None = self._load_logo()
        self.root.title(WIZARD_TITLE)
        self.root.configure(bg=self._p.bg)
        self.root.resizable(False, False)
        self._set_window_icon()
        self._center_window()

        self._build_shell()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._show_welcome()

    # --- window chrome ----------------------------------------------------

    def _load_logo(self) -> tk.PhotoImage | None:
        path = _asset("logo.png")
        if path is None:
            return None
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
        factor = max(1, int(round(max(image.width(), image.height()) / 48)))
        if factor > 1:
            image = image.subsample(factor, factor)
        return image

    def _set_window_icon(self) -> None:
        ico = _asset("BioUnlock.ico")
        if ico is not None:
            try:
                self.root.iconbitmap(default=str(ico))
            except tk.TclError:  # pragma: no cover - unusual icon failure
                pass

    def _center_window(self) -> None:
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - WINDOW_WIDTH) // 2)
        y = max(0, (self.root.winfo_screenheight() - WINDOW_HEIGHT) // 3)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def _build_shell(self) -> None:
        p = self._p
        header = tk.Frame(self.root, bg=p.card)
        header.pack(fill="x")
        header_inner = tk.Frame(header, bg=p.card)
        header_inner.pack(fill="x", padx=26, pady=16)

        if self._logo is not None:
            tk.Label(header_inner, image=self._logo, bg=p.card).pack(side="left", padx=(0, 14))
        else:
            logo = tk.Canvas(
                header_inner, width=48, height=48, bg=p.card, highlightthickness=0
            )
            logo.create_rectangle(2, 2, 46, 46, fill=p.accent, outline=p.accent)
            for radius in (9, 14, 19):
                logo.create_arc(
                    24 - radius,
                    10 - radius,
                    24 + radius,
                    10 + radius,
                    start=205,
                    end=335,
                    style="arc",
                    outline=p.on_accent,
                    width=2,
                )
            logo.pack(side="left", padx=(0, 14))

        titles = tk.Frame(header_inner, bg=p.card)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(
            titles,
            text="BioUnlock",
            font=(FONT, 17, "bold"),
            fg=p.text,
            bg=p.card,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            titles,
            text="Unlock this PC from your phone",
            font=(FONT, 9),
            fg=p.muted,
            bg=p.card,
            anchor="w",
        ).pack(fill="x", pady=(1, 0))

        tk.Frame(self.root, bg=p.accent, height=2).pack(fill="x")

        footer = tk.Frame(self.root, bg=p.card)
        footer.pack(fill="x", side="bottom")
        tk.Frame(footer, bg=p.border, height=1).pack(fill="x")
        footer_inner = tk.Frame(footer, bg=p.card)
        footer_inner.pack(fill="x", padx=26, pady=12)
        self._step_label = tk.Label(
            footer_inner,
            text="",
            font=(FONT, 9),
            fg=self._p.muted,
            bg=self._p.card,
            anchor="w",
        )
        self._step_label.pack(side="left")
        self._button_bar = tk.Frame(footer_inner, bg=p.card)
        self._button_bar.pack(side="right")

        self._body = tk.Frame(self.root, bg=p.bg)
        self._body.pack(fill="both", expand=True, padx=26, pady=18)

    # --- shared widgets ---------------------------------------------------

    def _clear_body(self) -> None:
        if self._bar is not None:
            self._bar.stop()
            self._bar = None
        for child in self._body.winfo_children():
            child.destroy()

    def _heading(self, title: str, subtitle: str | None = None) -> None:
        p = self._p
        tk.Label(
            self._body,
            text=title,
            font=(FONT, 15, "bold"),
            fg=p.text,
            bg=p.bg,
            anchor="w",
        ).pack(fill="x")
        if subtitle:
            tk.Label(
                self._body,
                text=subtitle,
                font=(FONT, 9),
                fg=p.muted,
                bg=p.bg,
                anchor="w",
                justify="left",
                wraplength=600,
            ).pack(fill="x", pady=(4, 0))

    def _card(self, parent: tk.Misc) -> tk.Frame:
        border = tk.Frame(parent, bg=self._p.border)
        inner = tk.Frame(border, bg=self._p.card)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return border, inner

    def _bullet(self, parent: tk.Misc, text: str) -> None:
        p = self._p
        row = tk.Frame(parent, bg=p.bg)
        row.pack(fill="x", pady=3)
        dot = tk.Canvas(row, width=14, height=16, bg=p.bg, highlightthickness=0)
        dot.create_oval(5, 6, 11, 12, fill=p.accent, outline="")
        dot.pack(side="left", anchor="n")
        tk.Label(
            row,
            text=text,
            font=(FONT, 10),
            fg=p.text,
            bg=p.bg,
            anchor="w",
            justify="left",
            wraplength=590,
        ).pack(side="left", padx=(6, 0), fill="x", expand=True)

    def _status_row(self, parent: tk.Misc, text: str, *, ok: bool = True) -> None:
        p = self._p
        row = tk.Frame(parent, bg=p.card)
        row.pack(fill="x", pady=2)
        mark = tk.Canvas(row, width=14, height=16, bg=p.card, highlightthickness=0)
        if ok:
            mark.create_line(3, 8, 6, 12, 12, 4, fill=p.success, width=2)
        else:
            mark.create_line(4, 4, 12, 12, fill=p.danger, width=2)
            mark.create_line(12, 4, 4, 12, fill=p.danger, width=2)
        mark.pack(side="left", anchor="n")
        tk.Label(
            row,
            text=text,
            font=(FONT, 9),
            fg=p.text if ok else p.danger,
            bg=p.card,
            anchor="w",
            justify="left",
            wraplength=540,
        ).pack(side="left", padx=(6, 0), fill="x", expand=True)

    def _set_buttons(self, *specs: tuple[str, bool, Callable[[], None], bool]) -> None:
        for button in self._buttons:
            button.destroy()
        self._buttons.clear()
        for text, primary, command, enabled in specs:
            button = self._button(self._button_bar, text, primary=primary, command=command)
            if not enabled:
                button.configure(state="disabled")
            button.pack(side="left", padx=(8, 0))
            self._buttons.append(button)

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        *,
        primary: bool,
        command: Callable[[], None],
    ) -> tk.Button:
        p = self._p
        if primary:
            bg, hover, fg = p.accent, p.accent_hover, p.on_accent
        else:
            bg, hover, fg = p.subtle, p.border, p.text
        button = tk.Button(
            parent,
            text=text,
            command=command,
            font=(FONT, 10),
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            disabledforeground=p.muted,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=20,
            pady=6,
            cursor="hand2",
        )
        button.bind(
            "<Enter>",
            lambda _e: button.configure(bg=hover)
            if str(button.cget("state")) != "disabled"
            else None,
        )
        button.bind(
            "<Leave>",
            lambda _e: button.configure(bg=bg)
            if str(button.cget("state")) != "disabled"
            else None,
        )
        return button

    def _set_step(self, text: str, *, detail: str | None = None) -> None:
        if self._step_label is not None:
            self._step_label.configure(text=text)
        if self._current_step_label is not None:
            self._current_step_label.configure(text=detail or "")

    # --- pages ------------------------------------------------------------

    def _show_welcome(self) -> None:
        self._clear_body()
        self._current_step_label = None
        p = self._p
        self._heading(
            "Welcome to BioUnlock",
            "This wizard sets up the tray app that lets you unlock this PC with your phone.",
        )

        bullets = tk.Frame(self._body, bg=p.bg)
        bullets.pack(fill="x", pady=(18, 0))
        self._bullet(bullets, "Unlock your PC from the BioUnlock app, even at the sign-in screen.")
        self._bullet(bullets, "Starts with Windows, before anyone signs in.")
        self._bullet(bullets, "One administrator approval is needed for sign-in support.")

        path_box = tk.Frame(self._body, bg=p.subtle)
        path_box.pack(fill="x", pady=(20, 0))
        tk.Label(
            path_box,
            text="Install location",
            font=(FONT, 8, "bold"),
            fg=p.muted,
            bg=p.subtle,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(
            path_box,
            text=str(install_dir()),
            font=(FONT, 9),
            fg=p.text,
            bg=p.subtle,
            anchor="w",
            justify="left",
            wraplength=590,
        ).pack(fill="x", padx=12, pady=(1, 8))

        self._set_step("Step 1 of 3")
        self._set_buttons(
            ("Cancel", False, self._on_close, True),
            ("Next", True, self._show_options, True),
        )

    def _show_options(self) -> None:
        self._clear_body()
        self._current_step_label = None
        p = self._p
        self._heading(
            "Choose your setup",
            "You can change these later from the tray icon.",
        )

        border, card = self._card(self._body)
        border.pack(fill="x", pady=(16, 0))
        rows = tk.Frame(card, bg=p.card)
        rows.pack(fill="x", padx=14, pady=10)
        self._checks = {
            "provider": _CheckRow(
                rows,
                p,
                "Enable unlock at the Windows sign-in screen",
                "Adds the Windows Credential Provider and a background agent that starts "
                "before login. Needs one administrator approval.",
                value=self.options.provider,
            ),
            "autostart": _CheckRow(
                rows,
                p,
                "Start BioUnlock when I sign in",
                value=self.options.autostart,
            ),
            "shortcut": _CheckRow(
                rows,
                p,
                "Create a Start Menu shortcut",
                value=self.options.shortcut,
            ),
            "start": _CheckRow(
                rows,
                p,
                "Open BioUnlock after setup",
                value=self.options.start,
            ),
        }
        for row in self._checks.values():
            row.pack(fill="x", pady=4)

        note = tk.Frame(self._body, bg=p.subtle)
        note.pack(fill="x", pady=(16, 0))
        tk.Label(
            note,
            text="Without sign-in support, the PC can still be unlocked while you are "
            "signed in, but not from the logon screen after a restart.",
            font=(FONT, 9),
            fg=p.muted,
            bg=p.subtle,
            anchor="w",
            justify="left",
            wraplength=580,
        ).pack(fill="x", padx=12, pady=8)

        self._set_step("Step 2 of 3")
        self._set_buttons(
            ("Back", False, self._show_welcome, True),
            ("Install", True, self._begin_install, True),
        )

    def _show_progress(self) -> None:
        self._clear_body()
        self._current_step_label = None
        p = self._p
        self._set_step("Step 3 of 3")
        self._heading(
            "Installing BioUnlock",
            "This can take a moment. Windows will ask for administrator approval once.",
        )
        self._current_step_label = tk.Label(
            self._body,
            text="Starting...",
            font=(FONT, 11, "bold"),
            fg=p.text,
            bg=p.bg,
            anchor="w",
            justify="left",
            wraplength=600,
        )
        self._current_step_label.pack(fill="x", pady=(18, 0))

        self._bar = _ProgressBar(self._body, p)
        self._bar.pack(fill="x", pady=(14, 12))
        self._bar.start()

        border, card = self._card(self._body)
        border.pack(fill="both", expand=True)
        self._log_rows = []
        self._log = tk.Frame(card, bg=p.card)
        self._log.pack(fill="both", expand=True, padx=12, pady=8)

        self._set_buttons(("Installing...", True, self._noop, False))

    def _show_finish(self, result: InstallResult) -> None:
        self._clear_body()
        self._current_step_label = None
        p = self._p
        ok = result.ok

        top = tk.Frame(self._body, bg=p.bg)
        top.pack(fill="x")
        icon = tk.Canvas(top, width=52, height=52, bg=p.bg, highlightthickness=0)
        if ok:
            icon.create_oval(2, 2, 50, 50, fill=p.ok_bg, outline="")
            icon.create_line(15, 27, 23, 35, 38, 18, fill=p.success, width=3)
        else:
            icon.create_oval(2, 2, 50, 50, fill=p.warn_bg, outline="")
            icon.create_text(26, 26, text="!", fill=p.warning, font=(FONT, 20, "bold"))
        icon.pack(side="left", anchor="n")

        titles = tk.Frame(top, bg=p.bg)
        titles.pack(side="left", fill="x", expand=True, padx=(14, 0))
        tk.Label(
            titles,
            text="BioUnlock is installed" if ok else "Setup needs one more step",
            font=(FONT, 15, "bold"),
            fg=p.text,
            bg=p.bg,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            titles,
            text=(
                "Everything is ready. The tray icon is in the notification area."
                if ok
                else "The app is installed, but sign-in unlock is not enabled yet."
            ),
            font=(FONT, 9),
            fg=p.muted,
            bg=p.bg,
            anchor="w",
            justify="left",
            wraplength=540,
        ).pack(fill="x", pady=(3, 0))

        if result.error:
            error_box = tk.Frame(self._body, bg=p.err_bg)
            error_box.pack(fill="x", pady=(16, 0))
            tk.Label(
                error_box,
                text=result.error,
                font=(FONT, 9),
                fg=p.danger,
                bg=p.err_bg,
                anchor="w",
                justify="left",
                wraplength=580,
            ).pack(fill="x", padx=12, pady=8)

        if result.details:
            border, card = self._card(self._body)
            border.pack(fill="x", pady=(14, 0))
            rows = tk.Frame(card, bg=p.card)
            rows.pack(fill="x", padx=14, pady=10)
            for line in result.details:
                self._status_row(rows, line)

        if ok:
            notes = tk.Frame(self._body, bg=p.bg)
            notes.pack(fill="x", pady=(12, 0))
            for line in result.notes():
                tk.Label(
                    notes,
                    text=line,
                    font=(FONT, 9),
                    fg=p.muted,
                    bg=p.bg,
                    anchor="w",
                    justify="left",
                    wraplength=600,
                ).pack(fill="x", pady=1)

        if result.needs_retry:
            self._set_step("Step 3 of 3")
            self._set_buttons(
                ("Finish", False, self._on_close, True),
                ("Retry", True, self._begin_install, True),
            )
        else:
            self._set_step("")
            self._set_buttons(("Finish", True, self._on_close, True))

    # --- install worker ---------------------------------------------------

    def _begin_install(self) -> None:
        if self._busy:
            return
        if self._checks:
            self.options = InstallOptions(
                provider=self._checks["provider"].value,
                autostart=self._checks["autostart"].value,
                shortcut=self._checks["shortcut"].value,
                start=self._checks["start"].value,
            )
        self._checks = {}
        self._busy = True
        self._show_progress()
        threading.Thread(
            target=self._worker,
            name="biounlock-install",
            daemon=True,
        ).start()
        self._poll()

    def _worker(self) -> None:
        try:
            result = install_core(
                self.options,
                on_step=lambda text: self._queue.put(("step", text)),
                on_status=lambda text: self._queue.put(("status", text)),
            )
        except Exception as exc:  # noqa: BLE001 - show the failure instead of dying
            logger.exception("Unexpected installer failure")
            result = InstallResult(
                ok=False,
                home=install_dir(),
                error=f"Setup failed unexpectedly: {exc}",
            )
        self._queue.put(("done", result))

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "step":
                self._set_step("Step 3 of 3", detail=str(payload))
            elif kind == "status":
                self._append_log(str(payload))
            elif kind == "done":
                self._busy = False
                self.result = payload if isinstance(payload, InstallResult) else None
                if self._bar is not None:
                    self._bar.stop()
                if self.result is not None:
                    self._show_finish(self.result)
                return
        if self._busy:
            self._poll_id = self.root.after(90, self._poll)

    def _append_log(self, text: str) -> None:
        p = self._p
        row = tk.Frame(self._log, bg=p.card)
        row.pack(fill="x", pady=1)
        mark = tk.Canvas(row, width=14, height=16, bg=p.card, highlightthickness=0)
        mark.create_line(3, 8, 6, 12, 12, 4, fill=p.success, width=2)
        mark.pack(side="left", anchor="n")
        tk.Label(
            row,
            text=text,
            font=(FONT, 9),
            fg=p.text,
            bg=p.card,
            anchor="w",
            justify="left",
            wraplength=530,
        ).pack(side="left", padx=(6, 0), fill="x", expand=True)
        self._log_rows.append(row)
        while len(self._log_rows) > LOG_LINES:
            self._log_rows.pop(0).destroy()

    # --- lifecycle --------------------------------------------------------

    def _noop(self) -> None:
        return None

    def _on_close(self) -> None:
        if self._busy:
            return
        if not self.result:
            self.result = None
        self.root.destroy()

    def run(self) -> InstallResult | None:
        self.root.mainloop()
        return self.result
