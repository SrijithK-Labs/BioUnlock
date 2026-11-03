"""Run the packaged BioUnlock agent before login from its protected install path."""

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

    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

try:
    import win32ts

    HAS_WIN32TS = True
except ImportError:  # pragma: no cover - pywin32 is a runtime dependency
    HAS_WIN32TS = False

logger = logging.getLogger(__name__)

SESSION_POLL_SECONDS = 2.0
IDLE_POLL_SECONDS = 10.0
RESTART_DELAY_SECONDS = 5.0

# WTS_SESSION_STATE values that never carry a signed-in user.
_NON_USER_STATES = (6, 7, 8)  # WTSListen, WTSReset, WTSDown

# Last probe failure, so a persistent error is logged once instead of on every
# two-second poll.
_probe_failure: str | None = None


def session_has_signed_in_user(state: Any, username: str | None) -> bool:
    """True when a session still has a signed-in user.

    A locked desktop and a disconnected RDP session both keep the tray (and its
    agent) running, so the startup agent must treat them as signed in and stay
    out of the way. Only a logoff or a shutdown clears the user name.
    """
    if not username:
        return False
    return int(state) not in _NON_USER_STATES


def interactive_user_present() -> bool:
    """True while any session still has a signed-in user."""
    global _probe_failure
    if os.name != "nt" or not HAS_WIN32TS:
        return False
    try:
        # Call without arguments: some pywin32 builds reject the documented
        # (*server*, *reserved*, *version*) triple with error 87
        # ("The parameter is incorrect"), which used to trip the except branch
        # below and idle the pre-login agent forever.
        sessions = win32ts.WTSEnumerateSessions()
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
            if session_has_signed_in_user(session.get("State"), username):
                _probe_failure = None
                return True
        _probe_failure = None
        return False
    except Exception as exc:  # noqa: BLE001 - fail safe, but never silently
        # Assume a user is signed in: running a second agent against the same
        # device key would race the tray on acknowledgements. Log it, though,
        # because the symptom is "phone unlock does nothing at the sign-in
        # screen" with no other clue.
        message = f"{type(exc).__name__}: {exc}"
        if message != _probe_failure:
            _probe_failure = message
            logger.warning(
                "Could not enumerate sessions, assuming a user is signed in: %s",
                message,
            )
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
            idle: bool | None = None
            try:
                while not self._stop_requested():
                    if interactive_user_present():
                        if idle is not True:
                            logger.info(
                                "Agent service idle: a user is signed in, "
                                "leaving delivery to the tray"
                            )
                            idle = True
                        self._sleep_interruptible(IDLE_POLL_SECONDS)
                    else:
                        if idle is not False:
                            logger.info(
                                "Agent service serving: no signed-in user, "
                                "waiting for a phone request"
                            )
                            idle = False
                        self._run_agent_until_session(loop)
            finally:
                loop.close()

        def _run_agent_until_session(self, loop: asyncio.AbstractEventLoop) -> None:
            agent = Agent()
            with self._agent_lock:
                self._agent = agent
            threading.Thread(
                target=self._stop_agent_when_user_signs_in, args=(agent, loop), daemon=True
            ).start()
            try:
                loop.run_until_complete(agent.run())
            except Exception:  # noqa: BLE001 - never crash the SCM
                logger.exception("Agent run loop stopped with an error")
            finally:
                agent.close()
                with self._agent_lock:
                    self._agent = None

        def _stop_agent_when_user_signs_in(
            self, agent: Agent, loop: asyncio.AbstractEventLoop
        ) -> None:
            while not self._stop_requested():
                if interactive_user_present():
                    logger.info("User signed in, handing the agent back to the tray")
                    try:
                        loop.call_soon_threadsafe(agent.request_stop)
                    except RuntimeError:  # loop already closed
                        pass
                    return
                time.sleep(SESSION_POLL_SECONDS)


def _stop_agent_at_sign_in(
    stop: asyncio.Event, loop: asyncio.AbstractEventLoop
) -> None:  # pragma: no cover - Windows-only
    """Set the agent's stop event as soon as a user is signed in."""
    while not stop.is_set():
        if interactive_user_present():
            logger.info("User signed in, handing the agent back to the tray")
            try:
                loop.call_soon_threadsafe(stop.set)
            except RuntimeError:  # loop already closed
                stop.set()
            return
        time.sleep(SESSION_POLL_SECONDS)


def run_foreground() -> int:  # pragma: no cover - Windows-only
    """Run the agent before login until the process is killed.

    Launched by the SYSTEM startup task created by the installer. It mirrors the
    service loop but never talks to the service control manager, so the same
    packaged executable can cover the sign-in screen without a second install
    mechanism. While any user is signed in (including a locked desktop) the
    agent idles and leaves delivery to the tray.
    """
    os.environ[config.ENV_HOME] = str(default_shared_home())
    os.environ[config.ENV_MACHINE_SECRETS] = "1"
    configure_logging("INFO", default_shared_home() / "agent.log")
    logger.info("Pre-login agent starting; home=%s", default_shared_home())
    if os.name == "nt" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    idle: bool | None = None
    try:
        while True:
            if interactive_user_present():
                if idle is not True:
                    logger.info(
                        "Pre-login agent idle: a user is signed in, leaving delivery to the tray"
                    )
                    idle = True
                time.sleep(IDLE_POLL_SECONDS)
                continue
            if idle is not False:
                logger.info(
                    "Pre-login agent serving: no signed-in user, waiting for a phone request"
                )
                idle = False
            agent = Agent()
            try:
                if not agent.config.is_enrolled:
                    logger.info("Pre-login agent idle: this PC is not enrolled yet")
                    time.sleep(IDLE_POLL_SECONDS)
                    continue
                # Share the same event with the watcher so a sign-in that lands
                # before the loop starts still stops it (a pre-set event is
                # honoured by Agent.run).
                stop = asyncio.Event()
                threading.Thread(
                    target=_stop_agent_at_sign_in, args=(stop, loop), daemon=True
                ).start()
                loop.run_until_complete(agent.run(stop))
            except Exception:  # noqa: BLE001 - keep the task running, retry
                logger.exception("Pre-login agent stopped with an error")
                _write_crash_log(traceback.format_exc())
            finally:
                agent.close()
            time.sleep(RESTART_DELAY_SECONDS)
    except KeyboardInterrupt:
        return 0
    finally:
        loop.close()


def main() -> int:  # pragma: no cover - Windows-only
    print(
        "Source-based Windows service installation is disabled because a "
        "LocalSystem service must not load code from a user-writable source tree. "
        "Use the packaged BioUnlock installer for pre-login unlock.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
