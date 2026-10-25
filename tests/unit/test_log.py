"""SEC-2 log sanitization and logging setup."""

from __future__ import annotations

import logging

import pytest

from ctxoptimizer.log import configure_logging, sanitize_headers, sanitize_url


def test_sanitize_headers_is_case_insensitive() -> None:
    cleaned = sanitize_headers(
        {
            "Authorization": "Bearer secret-value",
            "X-Api-Key": "sk-ant-secret",
            "x-goog-api-key": "AIza-secret",
            "Cookie": "session=abc",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
    )
    assert cleaned["Authorization"] == "REDACTED"
    assert cleaned["X-Api-Key"] == "REDACTED"
    assert cleaned["x-goog-api-key"] == "REDACTED"
    assert cleaned["Cookie"] == "REDACTED"
    assert cleaned["Content-Type"] == "application/json"
    assert cleaned["anthropic-version"] == "2023-06-01"


def test_sanitize_headers_does_not_mutate_input() -> None:
    original = {"authorization": "Bearer secret"}
    sanitize_headers(original)
    assert original["authorization"] == "Bearer secret"


def test_sanitize_url_redacts_key_and_keeps_other_params() -> None:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent"
        "?key=abc123&alt=sse"
    )
    cleaned = sanitize_url(url)
    assert "abc123" not in cleaned
    assert "key=REDACTED" in cleaned
    assert "alt=sse" in cleaned


def test_sanitize_url_redacts_userinfo() -> None:
    cleaned = sanitize_url("https://user:pass@example.com/v1/messages")
    assert "user" not in cleaned
    assert "pass" not in cleaned
    assert "example.com" in cleaned


def test_sanitize_url_without_query_is_unchanged() -> None:
    url = "https://api.anthropic.com/v1/messages"
    assert sanitize_url(url) == url


def test_configure_logging_sets_level() -> None:
    root = logging.getLogger()
    previous = root.level
    try:
        configure_logging("debug")
        assert root.level == logging.DEBUG
    finally:
        root.setLevel(previous)


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="unknown log level"):
        configure_logging("loud")
