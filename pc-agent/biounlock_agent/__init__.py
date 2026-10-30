"""BioUnlock PC agent.

An outbound-only Windows agent that pairs a PC with a BioUnlock backend,
keeps the server's signing key pinned, independently verifies signed
authorization envelopes, and reports a truthful result. On a verified
``remote_unlock`` it hands a short-lived ticket to the native Windows
Credential Provider, which performs the real sign-in; ``remote_lock`` locks
the workstation.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
