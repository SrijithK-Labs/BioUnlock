"""BioUnlock PC agent.

An outbound-only Windows agent that pairs a PC with a BioUnlock backend,
keeps the server's signing key pinned, independently verifies signed
authorization envelopes, and reports a truthful result.

This package never unlocks a Windows session in the current milestone; it
verifies requests and reports status honestly.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
