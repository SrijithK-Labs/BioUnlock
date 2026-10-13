# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for the BioUnlock tray agent.

Build with::

    pyinstaller --clean --noconfirm BioUnlock.spec

Produces a single ``dist\\BioUnlock.exe`` (no console window).
"""

import os

import _sqlite3
from PyInstaller.utils.hooks import collect_submodules

# Bundle the SQLite client library next to _sqlite3.pyd explicitly. Without it a
# frozen build dies at startup with "DLL load failed while importing _sqlite3".
_sqlite_dir = os.path.dirname(_sqlite3.__file__)

# Bundle the native Credential Provider so the exe can self-install logon-screen
# unlock. Skipped automatically when it has not been built yet.
_datas = [
    ("biounlock_agent/assets/logo.png", "assets"),
    ("biounlock_agent/assets/BioUnlock.ico", "assets"),
]
_provider_dll = os.path.join("windows-credential-provider", "build", "BioUnlockProvider.dll")
if os.path.exists(_provider_dll):
    _datas.append((_provider_dll, "provider"))

a = Analysis(
    ["run_tray.py"],
    pathex=["."],
    binaries=[(os.path.join(_sqlite_dir, "sqlite3.dll"), ".")],
    datas=_datas,
    hiddenimports=[
        # pystray picks its backend dynamically; make the Win32 one explicit.
        "pystray._win32",
        "PIL._tkinter_finder",
        # segno is imported lazily when pairing, so PyInstaller cannot see it.
        *collect_submodules("segno"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BioUnlock",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/BioUnlock.ico",
)
