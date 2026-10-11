"""PyInstaller entry point for the BioUnlock Windows app.

When frozen with no arguments this launches the system tray application.
Command line subcommands (``enroll``, ``set-credential``, ``run`` ...) keep
working from the packaged executable as well.
"""

from __future__ import annotations

from biounlock_agent.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
