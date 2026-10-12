"""Run the BioUnlock agent as a Windows service so it can unlock the PC before
anyone logs in. Starts at boot as LocalSystem, runs the agent only while no
interactive user is signed in, then hands off to the tray at logon.

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
import traceback
from typing import Any

from biounlock_agent import config
from biounlock_agent.agent import Agent
from biounlock_agent.config import default_shared_home
from biounlock_agent.logging_setup import configure_logging

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
    import win32ts

    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

logger = logging.getLogger(__name__)

SESSION_POLL_SECONDS = 5.0
IDLE_POLL_SECONDS = 10.0


def session_has_signed_in_user(state: Any, username: str | None, active: int = 0) -> bool:
    return state == active and bool(username)


def interactive_user_present() -> bool:
    """True while an interactive session has a signed-in user."""
    if os.name != "nt":
        return False
    try:
        sessions = win32ts.WTSEnumerateSessions(win32ts.WTS_CURRENT_SERVER_HANDLE, 0, 1)
        active = getattr(win32ts, "WTSActive", 0)
        for session in sessions:
            session_id = session.get("SessionID", session.get("SessionId", -1))
            if session_id <= 0:
                continue
            try:
                username = win32ts.WTSQuerySessionInformation(
                    win32ts.WTS_CURRENT_SERVER_HANDLE, session_id, win32ts.WTSUserName
                )
            except Exception:  # noqa: BLE001
                username = None
            if session_has_signed_in_user(session.get("State"), username, active):
                return True
        return False
    except Exception:  # noqa: BLE001 - if the probe fails, let the tray keep control
        return True


def _write_crash_log(text: str) -> None:
    # pywin32 runs the service without a console, so its own traceback print
    # fails and the event log only says "SvcRun() method failed".
    try:
        path = default_shared_home() / "agent-service-crash.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
    except OSError:
        pass


if HAS_PYWIN32:  # pragma: no cover - Windows-only

    class BioUnlockAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = "BioUnlockAgent"
        _svc_display_name_ = "BioUnlock PC Agent"
        _svc_description_ = "Unlocks this PC for a paired phone before login."

        def __init__(self, args):
            super().__init__(args)
            # Manual-reset so a stop stays set for every future Wait (an
            # auto-reset event would be consumed by the idle sleep and the
            # service would never see the stop).
            self._stop_handle = win32event.CreateEvent(None, 1, 0, None)
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
            try:
                self._serve()
            except Exception:  # noqa: BLE001 - save the traceback, then let SCM see the failure
                _write_crash_log(traceback.format_exc())
                raise

        def _serve(self):
            os.environ[config.ENV_HOME] = str(default_shared_home())
            os.environ[config.ENV_MACHINE_SECRETS] = "1"
            configure_logging("INFO", default_shared_home() / "agent.log")

            # pywin32 runs us off the main thread, where the Proactor loop can't
            # start (signal.set_wakeup_fd needs the main thread). websockets and
            # httpx work fine on the selector loop.
            if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                while not self._stop_requested():
                    if interactive_user_present():
                        self._sleep_interruptible(IDLE_POLL_SECONDS)
                    else:
                        self._run_agent_until_session(loop)
            finally:
                loop.close()

        def _run_agent_until_session(self, loop: asyncio.AbstractEventLoop) -> None:
            agent = Agent()
            with self._agent_lock:
                self._agent = agent
            threading.Thread(
                target=self._stop_agent_when_user_signs_in, args=(agent,), daemon=True
            ).start()
            try:
                loop.run_until_complete(agent.run())
            except Exception:  # noqa: BLE001 - never crash the SCM
                logger.exception("Agent run loop stopped with an error")
            finally:
                agent.close()
                with self._agent_lock:
                    self._agent = None

        def _stop_agent_when_user_signs_in(self, agent: Agent) -> None:
            while not self._stop_requested():
                if interactive_user_present():
                    logger.info("User signed in, handing the agent back to the tray")
                    agent.request_stop()
                    return
                time.sleep(SESSION_POLL_SECONDS)


def main() -> int:  # pragma: no cover - Windows-only
    if not HAS_PYWIN32:
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
