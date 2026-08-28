"""Redaction helpers for messages that may reach logs or MCP clients."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----.*?"
    r"-----END (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----",
    re.DOTALL,
)
_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
_LICENSE = re.compile(
    r"\b(CDS_LIC_FILE|LM_LICENSE_FILE)\s*=\s*(?!SET\b|UNSET\b)[^\s;]+",
    re.IGNORECASE,
)
_WINDOWS_PROFILE = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+")


def sanitize_text(value: str, *, max_length: int = 4_096) -> str:
    """Redact known secret forms and bound output without exposing raw values."""

    if max_length < 64:
        raise ValueError("max_length must be at least 64")
    sanitized = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    sanitized = _TOKEN.sub("[REDACTED TOKEN]", sanitized)
    sanitized = _LICENSE.sub(lambda match: f"{match.group(1)}=[REDACTED]", sanitized)
    sanitized = _WINDOWS_PROFILE.sub("%USERPROFILE%", sanitized)
    if len(sanitized) > max_length:
        marker = "...[TRUNCATED]"
        sanitized = sanitized[: max_length - len(marker)] + marker
    return sanitized


def sanitize_details(details: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize string values in a shallow, structured error detail mapping."""

    return {
        key: sanitize_text(value) if isinstance(value, str) else value
        for key, value in details.items()
    }

