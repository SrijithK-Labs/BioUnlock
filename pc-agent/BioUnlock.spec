# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for the BioUnlock tray agent.

Build with::

    pyinstaller --clean --noconfirm BioUnlock.spec

Produces a single ``dist\\BioUnlock.exe`` (no console window).
"""

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["run_tray.py"],
    pathex=["."],
    binaries=[],
    datas=[],
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
)
