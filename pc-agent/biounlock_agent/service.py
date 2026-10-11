"""Windows Service wrapper for the BioUnlock agent (optional).

Requires ``pywin32`` and is only usable on Windows. Install/uninstall with::

    python -m biounlock_agent.service install
    python -m biounlock_agent.service start
    python -m biounlock_agent.service stop
    python -m biounlock_agent.service remove

The service runs the same :class:`~biounlock_agent.agent.Agent` in a dedicated
asyncio loop.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from biounlock_agent.agent import Agent
from biounlock_agent.config import default_home
from biounlock_agent.logging_setup import configure_logging

try:  # pragma: no cover - depends on the Windows-only pywin32 package
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    _PYWIN32_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYWIN32_AVAILABLE = False

logger = logging.getLogger(__name__)

if _PYWIN32_AVAILABLE:  # pragma: no cover - Windows-only

    class BioUnlockAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = "BioUnlockAgent"
        _svc_display_name_ = "BioUnlock PC Agent"
        _svc_description_ = (
            "Verifies BioUnlock authorization requests over an outbound connection."
        )

        def __init__(self, args):
            super().__init__(args)
            self._stop_handle = win32event.CreateEvent(None, 0, 0, None)
            self._agent = Agent()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self._agent.request_stop()
            win32event.SetEvent(self._stop_handle)

        def SvcDoRun(self):
            servicemanager.LogInfoMsg("BioUnlock agent service starting")
            configure_logging("INFO", default_home() / "agent.log")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._agent.run())
            except Exception:  # noqa: BLE001 - never crash the SCM
                logger.exception("Agent service stopped with an error")
            finally:
                self._agent.close()
                loop.close()


def main() -> int:  # pragma: no cover - Windows-only
    if not _PYWIN32_AVAILABLE:
        print(
            "pywin32 is required to run the agent as a Windows service. "
            "Install it with 'pip install pywin32'.",
            file=sys.stderr,
        )
        return 1
    win32serviceutil.HandleCommandLine(BioUnlockAgentService)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
