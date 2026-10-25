"""Stored request-header redaction (INV-14)."""

from __future__ import annotations

from ctxproxy.proxy import _safe_headers


def test_safe_headers_redacts_secrets_but_keeps_context() -> None:
    safe = _safe_headers(
        {
            "authorization": "Bearer secret",
            "x-api-key": "sk-secret",
            "x-goog-api-key": "AIza-secret",
            "cookie": "session=secret",
            "user-agent": "opencode/2.0",
            "anthropic-version": "2023-06-01",
        }
    )
    assert safe["authorization"] == "[redacted]"
    assert safe["x-api-key"] == "[redacted]"
    assert safe["x-goog-api-key"] == "[redacted]"
    assert safe["cookie"] == "[redacted]"
    assert safe["user-agent"] == "opencode/2.0"
    assert safe["anthropic-version"] == "2023-06-01"
