"""Windows Service wrapper for the BioUnlock agent.

This is what lets the phone control the PC **before anyone logs in** — at the
sign-in screen after a reboot. The service runs as LocalSystem at boot and:

* uses the machine-wide home (``%ProgramData%\\BioUnlock``) with DPAPI
  *machine*-scope secrets, so the device key and Windows credential written by
  the in-session tray are readable before login;
* runs the agent only while no interactive user is signed in. As soon as a user
  logs on it hands control back to the tray (which, being in the interactive
  session, is the only one that can lock the desktop), so the two never fight.

Install/uninstall via the elevated ``install-service.ps1`` / ``uninstall-service.ps1``
scripts, or directly with::

    python -m biounlock_agent.service install
    python -m biounlock_agent.service start
    python -m biounlock_agent.service stop
    python -m biounlock_agent.service remove
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from typing import Any

from biounlock_agent import config
from biounlock_agent.agent import Agent
from biounlock_agent.config import default_shared_home
from biounlock_agent.logging_setup import configure_logging

try:  # pragma: no cover - depends on the Windows-only pywin32 package
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
    import win32ts

    _PYWIN32_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYWIN32_AVAILABLE = False

logger = logging.getLogger(__name__)

SESSION_POLL_SECONDS = 5.0
IDLE_POLL_SECONDS = 10.0


def session_has_signed_in_user(state: Any, username: str | None, *, active: int) -> bool:
    """Whether a WTS session is an *active* session with a signed-in user.

    ``state`` is the raw WTS connect state and ``active`` the ``WTSActive`` value.
    Session 0 is the services session and is ignored. Kept side-effect free so it
    can be unit-tested without Windows.
    """
    if state != active:
        return False
    return bool(username)


def interactive_user_present() -> bool:
    """True while any interactive session has a signed-in user (i.e. not pre-login)."""
    if os.name != "nt":  # pragma: no cover - Windows only
        return False
    try:  # pragma: no cover - Windows API calls
        server = win32ts.WTS_CURRENT_SERVER_HANDLE
        sessions = win32ts.WTSEnumerateSessions(server, 0, 1)
    except Exception:  # noqa: BLE001 - a probe failure must not stop the service
        return True  # conservative: assume signed in, leave the tray in charge
    for session in sessions:
        session_id = session.get("SessionID", session.get("SessionId", -1))
        if session_id in (-1, 0):
            continue
        try:
            username = win32ts.WTSQuerySessionInformation(
                win32ts.WTS_CURRENT_SERVER_HANDLE, session_id, win32ts.WTSUserName
            )
        except Exception:  # noqa: BLE001
            username = None
        if session_has_signed_in_user(
            session.get("State"), username, active=getattr(win32ts, "WTSActive", 0)
        ):
            return True
    return False


if _PYWIN32_AVAILABLE:  # pragma: no cover - Windows-only

    class BioUnlockAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = "BioUnlockAgent"
        _svc_display_name_ = "BioUnlock PC Agent"
        _svc_description_ = (
            "Lets a paired phone unlock this PC before login, over an outbound connection."
        )

        def __init__(self, args):
            super().__init__(args)
            self._stop_handle = win32event.CreateEvent(None, 0, 0, None)
            self._agent: Agent | None = None
            self._agent_lock = threading.Lock()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_handle)
            with self._agent_lock:
                agent = self._agent
            if agent is not None:
                agent.request_stop()

        def _stop_requested(self) -> bool:
            return (
                win32event.WaitForSingleObject(self._stop_handle, 0)
                == win32event.WAIT_OBJECT_0
            )

        def _sleep_interruptible(self, seconds: float) -> None:
            win32event.WaitForSingleObject(self._stop_handle, int(seconds * 1000))

        def SvcDoRun(self):
            servicemanager.LogInfoMsg("BioUnlock agent service starting")
            # Force the machine-wide, machine-scope layout regardless of the
            # service account's own profile.
            os.environ[config.ENV_HOME] = str(default_shared_home())
            os.environ[config.ENV_MACHINE_SECRETS] = "1"
            configure_logging("INFO", default_shared_home() / "agent.log")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                while not self._stop_requested():
                    if interactive_user_present():
                        # Someone is signed in: the tray owns the agent.
                        self._sleep_interruptible(IDLE_POLL_SECONDS)
                        continue
                    self._run_agent_until_session(loop)
            finally:
                loop.close()

        def _run_agent_until_session(self, loop: asyncio.AbstractEventLoop) -> None:
            agent = Agent()
            with self._agent_lock:
                self._agent = agent
            watcher = threading.Thread(
                target=self._stop_agent_when_user_signs_in, args=(agent,), daemon=True
            )
            watcher.start()
            try:
                loop.run_until_complete(agent.run())
            except Exception:  # noqa: BLE001 - never crash the SCM
                logger.exception("Agent service run loop stopped with an error")
            finally:
                agent.close()
                with self._agent_lock:
                    self._agent = None

        def _stop_agent_when_user_signs_in(self, agent: Agent) -> None:
            while not self._stop_requested():
                if interactive_user_present():
                    logger.info("User signed in; handing the agent back to the tray")
                    agent.request_stop()
                    return
                time.sleep(SESSION_POLL_SECONDS)


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
