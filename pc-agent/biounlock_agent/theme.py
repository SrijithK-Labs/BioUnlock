"""Shared flat colour palette for the Windows windows and the setup wizard.

The same values are used by the phone app so the tray, the settings window and
the installer look like one product: neutral surfaces, one blue accent.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover - Windows-only registry integration
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


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
