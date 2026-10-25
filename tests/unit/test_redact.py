"""Redaction patterns (SEC-5 / SPEC 14.4)."""

from __future__ import annotations

from ctxoptimizer.telemetry.redact import redact_bytes, redact_text


def test_redacts_common_credentials() -> None:
    cases = [
        "sk-ant-api03-abcdefghijklmnop",
        "sk-proj-abcdefghijklmnopqrstuvwxyz",
        "AIzaSyA1234567890abcdefghijklmnopq",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "AKIAABCDEFGHIJKLMNOP",
        "xoxb-1234567890-abcdef",
        "Authorization: Bearer abcdefgh.123456",
        "API_KEY=super-secret-value",
        "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----",
    ]
    for value in cases:
        redacted = redact_text(value)
        assert "[REDACTED]" in redacted, value


def test_does_not_redact_ordinary_code() -> None:
    text = "def token_count(value):\n    return len(value.split())\n"
    assert redact_text(text) == text
    assert redact_bytes(text.encode()).decode() == text
