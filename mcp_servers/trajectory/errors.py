"""Trajectory MCP error types."""


class ValidationError(Exception):
    """Raised when input validation fails before calling Tawhiri."""


class TawhiriError(Exception):
    """Raised when the Tawhiri upstream call fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def error_response(kind: str, detail: str) -> dict:
    """Build a stable error dict for MCP tool responses."""
    return {"ok": False, "error": kind, "detail": detail}
