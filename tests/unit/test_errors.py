from __future__ import annotations

from cadence_mcp_bridge.errors import BackendUnavailableError
from cadence_mcp_bridge.models import ErrorCode


def test_error_envelope_is_stable_and_sanitized() -> None:
    token = "github_pat_" + ("a" * 40)
    error = BackendUnavailableError(
        f"backend failed with {token}",
        details={"path": r"C:\Users\private-user\.ssh"},
    )

    envelope = error.to_envelope()

    assert envelope.code is ErrorCode.BACKEND_UNAVAILABLE
    assert envelope.retryable is True
    assert token not in envelope.message
    assert envelope.details["path"] == r"%USERPROFILE%\.ssh"
