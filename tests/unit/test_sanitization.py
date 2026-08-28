from __future__ import annotations

from cadence_mcp_bridge.sanitization import sanitize_text


def test_redacts_secrets_and_user_profile() -> None:
    token = "ghp_" + ("a" * 32)
    license_endpoint = "27000@" + "fixture.invalid"
    value = (
        f"token={token} CDS_LIC_FILE={license_endpoint} "
        r"path=C:\Users\private-user\work"
    )

    sanitized = sanitize_text(value)

    assert token not in sanitized
    assert license_endpoint not in sanitized
    assert "private-user" not in sanitized
    assert "[REDACTED TOKEN]" in sanitized
    assert "CDS_LIC_FILE=[REDACTED]" in sanitized
    assert "%USERPROFILE%" in sanitized


def test_preserves_safe_license_state() -> None:
    assert sanitize_text("CDS_LIC_FILE=SET") == "CDS_LIC_FILE=SET"


def test_bounds_output() -> None:
    sanitized = sanitize_text("x" * 200, max_length=64)

    assert len(sanitized) == 64
    assert sanitized.endswith("...[TRUNCATED]")
