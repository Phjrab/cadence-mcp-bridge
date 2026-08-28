"""Exception hierarchy that exposes only stable, sanitized error envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cadence_mcp_bridge.models import ErrorCode, ErrorEnvelope
from cadence_mcp_bridge.sanitization import sanitize_details, sanitize_text


class BridgeError(Exception):
    code = ErrorCode.INTERNAL_ERROR
    retryable = False

    def __init__(
        self,
        safe_message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.details = dict(details or {})

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            code=self.code,
            message=sanitize_text(self.safe_message, max_length=1_024),
            retryable=self.retryable,
            details=sanitize_details(self.details),
        )


class ConfigurationError(BridgeError):
    code = ErrorCode.INVALID_CONFIGURATION


class InvalidInputError(BridgeError):
    code = ErrorCode.INVALID_INPUT


class BackendUnavailableError(BridgeError):
    code = ErrorCode.BACKEND_UNAVAILABLE
    retryable = True


class AuthenticationError(BridgeError):
    code = ErrorCode.AUTHENTICATION_FAILED


class HostKeyError(BridgeError):
    code = ErrorCode.HOST_KEY_FAILED


class OperationTimeoutError(BridgeError):
    code = ErrorCode.TIMEOUT
    retryable = True


class RemoteFailureError(BridgeError):
    code = ErrorCode.REMOTE_FAILURE
