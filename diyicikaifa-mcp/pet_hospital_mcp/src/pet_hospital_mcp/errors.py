"""Unified structured error contract shared across the whole MCP service.

Every failure surfaced to an MCP client — whether an invalid tool input or an
upstream (Go backend) exception — is rendered as::

    {
      "error": {
        "code": "ERROR_CODE",
        "message": "human readable message",
        "details": {}
      }
    }

The ``code`` is one of the stable identifiers below. ``PetHospitalError`` is
the domain exception carrying the structured payload; the tool layer converts
it into an ``isError=true`` ``CallToolResult`` whose text content is exactly
this JSON document. No HTTPX / Pydantic / SDK / Python stack trace is ever
leaked to the client.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

VALIDATION_ERROR = "VALIDATION_ERROR"
BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
BACKEND_API_ERROR = "BACKEND_API_ERROR"
BACKEND_INVALID_RESPONSE = "BACKEND_INVALID_RESPONSE"
INTERNAL_ERROR = "INTERNAL_ERROR"

#: Canonical set of error codes the service may emit.
ERROR_CODES = frozenset(
    {
        VALIDATION_ERROR,
        BACKEND_TIMEOUT,
        BACKEND_UNAVAILABLE,
        BACKEND_API_ERROR,
        BACKEND_INVALID_RESPONSE,
        INTERNAL_ERROR,
    }
)


class PetHospitalError(Exception):
    """A structured domain error that can be serialized to the unified shape."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code: {code!r}")
        self.code = code
        self.message = message
        self.details: Dict[str, Any] = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


def validation_error(message: str, details: Optional[Dict[str, Any]] = None) -> PetHospitalError:
    return PetHospitalError(VALIDATION_ERROR, message, details)
