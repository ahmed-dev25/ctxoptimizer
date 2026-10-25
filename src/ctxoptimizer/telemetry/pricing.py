"""Model pricing lookup and cost math (SPEC section 14.2).

Provider-reported cost (OpenRouter) wins when present. Otherwise the bundled
table is used; an unknown model or a missing rate yields ``priced=False`` and a
NULL cost rather than an invented number (INV-13).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from ctxoptimizer.models import Usage

PriceSource = Literal["provider", "pricing", "none"]


@dataclass(frozen=True, slots=True)
class ModelPrice:
    provider: str
    match: str
    input: float
    output: float
    cache_read: float = 0.0
    cache_write_5m: float | None = None
    cache_write_1h: float | None = None
    cache_write_30m: float | None = None
    cache_write_12h: float | None = None
    verified: bool = False
    source: str = ""
    notes: str = ""


@dataclass(frozen=True, slots=True)
class PriceResult:
    cost_usd: float | None
    priced: bool
    source: PriceSource
    price: ModelPrice | None


class PricingTable:
    def __init__(
        self,
        models: list[ModelPrice],
        *,
        per: int = 1_000_000,
        currency: str = "USD",
        version: str = "",
    ) -> None:
        self.models = tuple(models)
        self.per = per
        self.currency = currency
        self.version = version

    def lookup(self, provider: str, model: str) -> ModelPrice | None:
        candidates = [
            price
            for price in self.models
            if price.provider == provider and fnmatchcase(model, price.match)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda price: (_literal_prefix(price.match), len(price.match)))

    def cost(
        self,
        usage: Usage,
        price: ModelPrice | None,
        *,
        prefer_provider_cost: bool = True,
    ) -> PriceResult:
        if prefer_provider_cost and usage.provider_cost_usd is not None:
            return PriceResult(usage.provider_cost_usd, True, "provider", price)
        if price is None:
            return PriceResult(None, False, "none", None)
        total = 0.0
        buckets = (
            (usage.fresh_input, price.input),
            (usage.cache_read, price.cache_read),
            (usage.cache_write_5m, price.cache_write_5m),
            (usage.cache_write_1h, price.cache_write_1h),
            (usage.cache_write_30m, price.cache_write_30m),
            (usage.cache_write_12h, price.cache_write_12h),
            (usage.output, price.output),
        )
        for tokens, rate in buckets:
            if not tokens:
                continue
            if rate is None:
                return PriceResult(None, False, "none", price)
            total += tokens * rate
        return PriceResult(total / self.per, True, "pricing", price)


def load_pricing(user_file: Path | None = None) -> PricingTable:
    """Load the bundled table and merge an optional user override."""
    bundled = _read_json(
        resources.files("ctxoptimizer").joinpath("data", "pricing.json").read_text("utf-8")
    )
    models = [_parse_price(raw) for raw in bundled.get("models", [])]
    if user_file is not None:
        user = _read_json(user_file.read_text(encoding="utf-8"))
        overrides = {(entry.provider, entry.match): entry for entry in models}
        for raw in user.get("models", []):
            parsed = _parse_price(raw)
            overrides[(parsed.provider, parsed.match)] = parsed
        models = list(overrides.values())
    return PricingTable(
        models,
        per=int(bundled.get("per", 1_000_000)),
        currency=str(bundled.get("currency", "USD")),
        version=str(bundled.get("version", "")),
    )


def price_usage(usage: Usage, table: PricingTable, provider: str, model: str | None) -> PriceResult:
    """Price one request. Unknown models stay unpriced, never guessed."""
    price = table.lookup(provider, model) if model else None
    return table.cost(usage, price)


def _parse_price(raw: dict[str, Any]) -> ModelPrice:
    return ModelPrice(
        provider=str(raw["provider"]),
        match=str(raw["match"]),
        input=float(raw["input"]),
        output=float(raw["output"]),
        cache_read=float(raw.get("cache_read", 0.0)),
        cache_write_5m=_optional_float(raw.get("cache_write_5m")),
        cache_write_1h=_optional_float(raw.get("cache_write_1h")),
        cache_write_30m=_optional_float(raw.get("cache_write_30m")),
        cache_write_12h=_optional_float(raw.get("cache_write_12h")),
        verified=bool(raw.get("verified", False)),
        source=str(raw.get("source", "")),
        notes=str(raw.get("notes", "")),
    )


def _read_json(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("pricing file must contain a JSON object")
    return value


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _literal_prefix(pattern: str) -> int:
    for index, char in enumerate(pattern):
        if char in "*?[":
            return index
    return len(pattern)


__all__ = [
    "ModelPrice",
    "PriceResult",
    "PricingTable",
    "load_pricing",
    "price_usage",
]
