"""Pricing lookup, specificity and cost math (SPEC section 14.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctxproxy.models import Usage
from ctxproxy.telemetry.pricing import (
    ModelPrice,
    PricingTable,
    load_pricing,
    price_usage,
)


def test_bundled_table_loads() -> None:
    table = load_pricing()
    assert table.version
    assert table.currency == "USD"
    assert table.per == 1_000_000
    assert table.models


def test_specific_glob_wins() -> None:
    table = load_pricing()
    opus_55 = table.lookup("anthropic", "claude-opus-5-5")
    opus_5 = table.lookup("anthropic", "claude-opus-5")
    assert opus_55 is not None and opus_55.input == 4.0
    assert opus_5 is not None and opus_5.input == 5.0


def test_provider_scoping() -> None:
    table = load_pricing()
    assert table.lookup("openai", "deepseek-flash") is None
    assert table.lookup("deepseek", "deepseek-flash") is not None


def test_cost_math_including_cache_buckets() -> None:
    table = PricingTable(
        [
            ModelPrice(
                provider="test",
                match="m*",
                input=3.0,
                output=15.0,
                cache_read=0.3,
                cache_write_5m=3.75,
            )
        ]
    )
    usage = Usage(
        fresh_input=1000,
        cache_read=2000,
        cache_write_5m=500,
        output=100,
        source="provider",
    )
    result = price_usage(usage, table, "test", "m1")
    assert result.priced is True
    assert result.source == "pricing"
    expected = (1000 * 3.0 + 2000 * 0.3 + 500 * 3.75 + 100 * 15.0) / 1_000_000
    assert result.cost_usd == pytest.approx(expected)


def test_provider_reported_cost_wins() -> None:
    usage = Usage(fresh_input=100, output=10, provider_cost_usd=0.42, source="provider")
    result = PricingTable([]).cost(usage, None)
    assert result.priced is True
    assert result.source == "provider"
    assert result.cost_usd == pytest.approx(0.42)


def test_missing_rate_is_unpriced() -> None:
    price = ModelPrice(
        provider="test",
        match="m",
        input=1.0,
        output=1.0,
        cache_read=1.0,
        cache_write_5m=None,
    )
    table = PricingTable([price])
    usage = Usage(fresh_input=1, cache_write_5m=10, source="provider")
    result = table.cost(usage, price)
    assert result.priced is False
    assert result.cost_usd is None


def test_unknown_model_is_unpriced() -> None:
    result = price_usage(
        Usage(fresh_input=10, source="provider"),
        load_pricing(),
        "openai",
        "not-a-real-model",
    )
    assert result.priced is False
    assert result.cost_usd is None


def test_no_model_is_unpriced() -> None:
    result = price_usage(Usage(fresh_input=10, source="provider"), load_pricing(), "openai", None)
    assert result.priced is False


def test_user_override_merges(tmp_path: Path) -> None:
    override = tmp_path / "pricing.json"
    override.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "match": "gpt-6.1-sol*",
                        "input": 1.0,
                        "output": 2.0,
                        "cache_read": 0.05,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    table = load_pricing(override)
    price = table.lookup("openai", "gpt-6.1-sol")
    assert price is not None
    assert price.input == 1.0
    assert price.output == 2.0


def test_deepseek_cost_uses_hit_rate() -> None:
    table = load_pricing()
    usage = Usage(fresh_input=40, cache_read=60, output=10, source="provider")
    result = price_usage(usage, table, "deepseek", "deepseek-flash")
    assert result.priced is True
    expected = (40 * 0.3 + 60 * 0.006 + 10 * 1.2) / 1_000_000
    assert result.cost_usd == pytest.approx(expected)
