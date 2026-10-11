"""Console entrypoint for the BioUnlock PC agent.

Usage::

    python -m biounlock_agent enroll --server-url https://unlock.example.com
    python -m biounlock_agent run
    python -m biounlock_agent status
    python -m biounlock_agent unenroll
    python -m biounlock_agent gui
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from biounlock_agent import __version__
from biounlock_agent.agent import Agent
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
        enrollment = agent.enroll(args.server_url, device_name=args.name)
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


def _cmd_gui(args: argparse.Namespace) -> int:
    from biounlock_agent.gui import main as gui_main

    return gui_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="biounlock_agent", description="BioUnlock PC agent")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command")

    enroll = sub.add_parser("enroll", help="Enroll this PC and show a pairing code")
    enroll.add_argument("--server-url", required=True)
    enroll.add_argument("--name", default=None)
    enroll.add_argument("--timeout", type=float, default=300.0)
    enroll.set_defaults(func=_cmd_enroll)

    run = sub.add_parser("run", help="Run the agent in the foreground")
    run.set_defaults(func=_cmd_run)

    status = sub.add_parser("status", help="Print local agent status")
    status.set_defaults(func=_cmd_status)

    unenroll = sub.add_parser("unenroll", help="Remove the local enrollment")
    unenroll.set_defaults(func=_cmd_unenroll)

    gui = sub.add_parser("gui", help="Launch the setup GUI")
    gui.set_defaults(func=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
