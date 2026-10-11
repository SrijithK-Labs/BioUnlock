"""Exception hierarchy for the BioUnlock PC agent."""

from __future__ import annotations


class AgentError(Exception):
    """Base class for all agent errors."""


class NotEnrolledError(AgentError):
    """Raised when an operation needs an enrollment that does not exist yet."""


class ApiError(AgentError):
    """A structured error returned by the backend.

    ``code`` and ``message`` mirror the server's ``{"error": {...}}`` body when
    available; ``status_code`` is the HTTP status when the failure came from a
    response.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "api_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class EnvelopeVerificationError(AgentError):
    """Raised when a delivered authorization envelope fails verification.

    ``reason_code`` is a short, non-secret code suitable for reporting back to
    the server (e.g. ``bad_signature``, ``expired``, ``replayed``).
    """

    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code
