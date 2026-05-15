"""Typed exception hierarchy for orchestrator API interactions.

Every exception carries ``status_code: int | None`` and
``error_code: str | None`` extracted from the server's uniform error envelope
(``{"error": {"code": "...", "message": "...", "details": ...}}``), making
it easy for callers to handle specific error conditions programmatically.
"""

from typing import Any


class OrchestratorError(Exception):
    """Base exception for all orchestrator-related errors."""

    def __init__(
        self,
        detail: str,
        status_code: int | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(detail)


class OrchestratorConnectionError(OrchestratorError):
    """Orchestrator is unreachable (network / DNS / timeout)."""

    def __init__(self, detail: str):
        super().__init__(detail, status_code=None)


class OrchestratorAuthError(OrchestratorError):
    """Authentication or authorization failure (401/403)."""

    def __init__(self, detail: str, status_code: int = 401):
        super().__init__(detail, status_code=status_code)


class OrchestratorNotFoundError(OrchestratorError):
    """Requested resource does not exist (404)."""

    def __init__(self, resource_type: str, resource_id: str, detail: str | None = None):
        self.resource_type = resource_type
        self.resource_id = resource_id
        message = detail or f"{resource_type} not found: {resource_id}"
        super().__init__(message, status_code=404)


class OrchestratorAPIError(OrchestratorError):
    """Non-2xx response from the orchestrator API.

    Covers 400 Bad Request, 500 Internal Server Error, and any other
    unexpected status that isn't auth or not-found specific.
    """

    def __init__(
        self,
        detail: str,
        status_code: int,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(detail, status_code=status_code, error_code=error_code, details=details)


class OrchestratorConfigError(OrchestratorError):
    """Invalid or missing client configuration (bad env vars, etc.)."""

    def __init__(self, detail: str):
        super().__init__(detail, status_code=None)
