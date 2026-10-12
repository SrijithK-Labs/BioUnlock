"""Console entrypoint for the BioUnlock PC agent.

Usage::

    python -m biounlock_agent tray
    python -m biounlock_agent enroll --server-url https://unlock.example.com --token <api-token>
    python -m biounlock_agent set-credential
    python -m biounlock_agent run
    python -m biounlock_agent status
    python -m biounlock_agent unenroll
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys

from biounlock_agent import __version__, unlock
from biounlock_agent.agent import Agent
from biounlock_agent.config import default_home
from biounlock_agent.errors import AgentError
from biounlock_agent.logging_setup import configure_logging


def _print_qr(payload: str) -> bool:
    try:
        import segno
    except Exception:  # noqa: BLE001 - QR rendering is optional
        return False
    try:
        segno.make(payload, error="m").terminal(compact=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def _cmd_enroll(args: argparse.Namespace) -> int:
    agent = Agent()
    try:
        enrollment = agent.enroll(args.server_url, device_name=args.name, api_token=args.token)
    except AgentError as exc:
        print(f"Enrollment failed: {exc}", file=sys.stderr)
        agent.close()
        return 1

    print("Enrolled. Scan this QR code with the BioUnlock app, or enter the code manually.")
    print(f"  Device name: {enrollment.device_name}")
    print(f"  Pairing code: {enrollment.pairing_code}")
    print(f"  Expires at:  {enrollment.expires_at}")
    if not _print_qr(enrollment.qr_payload):
        print("  (Install 'segno' to render a QR code here.)")
        print(f"  QR payload: {enrollment.qr_payload}")

    print("\nWaiting for the phone to confirm pairing...")
    try:
        paired = asyncio.run(agent.wait_for_pairing(timeout=args.timeout))
    except KeyboardInterrupt:
        paired = False
    finally:
        agent.close()

    if paired:
        print("Paired successfully. Run 'python -m biounlock_agent run' to start the agent.")
        return 0
    print("Not paired yet. Re-run enroll or confirm pairing on your phone.", file=sys.stderr)
    return 1


def _cmd_run(args: argparse.Namespace) -> int:
    agent = Agent()
    configure_logging(args.log_level)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        pass
    except AgentError as exc:
        print(f"Agent error: {exc}", file=sys.stderr)
        return 1
    finally:
        agent.close()
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    agent = Agent()
    status = agent.status()
    print(json.dumps(status.__dict__, indent=2, default=str))
    agent.close()
    return 0


def _cmd_unenroll(args: argparse.Namespace) -> int:
    agent = Agent()
    agent.unenroll()
    agent.close()
    print("Local enrollment removed. Pair again to re-enroll.")
    return 0


def _cmd_set_credential(args: argparse.Namespace) -> int:
    home = default_home()
    username = args.username or os.environ.get("USERNAME") or getpass.getuser()
    domain = args.domain
    if domain is None:
        domain = os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or ""
    if args.password is not None:
        password = args.password
        print(
            "Warning: --password may be recorded in your shell history; prefer the prompt.",
            file=sys.stderr,
        )
    else:
        password = getpass.getpass(f"Windows password for {username}: ")
    if not password:
        print("Refusing to store an empty password.", file=sys.stderr)
        return 1
    credential = unlock.WindowsCredential(username=username, password=password, domain=domain)
    try:
        path = unlock.save_windows_credential(home, credential)
    except unlock.UnlockError as exc:
        print(f"Could not store the credential: {exc}", file=sys.stderr)
        return 1
    print(f"Stored a DPAPI-protected Windows credential for '{username}' at {path}.")
    print("This PC can now be unlocked from your phone (Credential Provider must be installed).")
    return 0


def _cmd_clear_credential(args: argparse.Namespace) -> int:
    unlock.reset_windows_credential(default_home())
    print("Removed the stored Windows credential and any pending unlock ticket.")
    return 0


def _cmd_tray(args: argparse.Namespace) -> int:
    try:
        from biounlock_agent.tray import main as tray_main
    except ImportError as exc:  # pragma: no cover - depends on optional deps
        print(
            f"The tray app requires 'pystray' and 'Pillow' to be installed: {exc}",
            file=sys.stderr,
        )
        return 1

    return tray_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="biounlock_agent", description="BioUnlock PC agent")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command")

    enroll = sub.add_parser("enroll", help="Enroll this PC and show a pairing code")
    enroll.add_argument("--server-url", required=True)
    enroll.add_argument("--name", default=None)
    enroll.add_argument(
        "--token",
        default=None,
        help="Server API token (or set BIOUNLOCK_AGENT_TOKEN); required to enroll",
    )
    enroll.add_argument("--timeout", type=float, default=300.0)
    enroll.set_defaults(func=_cmd_enroll)

    run = sub.add_parser("run", help="Run the agent in the foreground")
    run.set_defaults(func=_cmd_run)

    status = sub.add_parser("status", help="Print local agent status")
    status.set_defaults(func=_cmd_status)

    unenroll = sub.add_parser("unenroll", help="Remove the local enrollment")
    unenroll.set_defaults(func=_cmd_unenroll)

    setcred = sub.add_parser(
        "set-credential",
        help="Store the Windows credential used for unlocking (DPAPI-protected)",
    )
    setcred.add_argument("--username", default=None, help="Windows username (default: current user)")
    setcred.add_argument("--domain", default=None, help="Domain or computer name (default: detected)")
    setcred.add_argument(
        "--password",
        default=None,
        help="Windows password (omit to be prompted securely; passing it is insecure)",
    )
    setcred.set_defaults(func=_cmd_set_credential)

    clearcred = sub.add_parser(
        "clear-credential", help="Remove the stored Windows credential and pending ticket"
    )
    clearcred.set_defaults(func=_cmd_clear_credential)

    gui = sub.add_parser("tray", help="Launch the system tray application")
    gui.set_defaults(func=_cmd_tray)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Double-clicking the app (or running with no arguments) opens the tray.
        return _cmd_tray(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
