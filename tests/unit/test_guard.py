"""Auto-quarantine guard (P3-7)."""

from __future__ import annotations

from ctxproxy.config import Config
from ctxproxy.guard import Guard
from ctxproxy.transforms import build_transforms


def test_fallback_quarantine_and_enable() -> None:
    config = Config.model_validate({"guard": {"fallback_limit": 1}})
    guard = Guard(config)
    guard.observe_fallback("s", ["ansi_strip"])
    assert guard.is_quarantined("s", "ansi_strip") is False
    guard.observe_fallback("s", ["ansi_strip"])
    assert guard.is_quarantined("s", "ansi_strip") is True
    assert guard.quarantined_for("s") == {"ansi_strip"}
    assert guard.status()[0]["reason"] == "fallbacks"
    guard.enable("s", "ansi_strip")
    assert guard.is_quarantined("s", "ansi_strip") is False


def test_our_fault_drift_quarantines() -> None:
    config = Config()
    guard = Guard(config)
    guard.observe_final_drift("s", "config_changed", ["smart_truncate"])
    assert guard.is_quarantined("s", "smart_truncate") is True


def test_disabled_transform_is_not_built() -> None:
    config = Config()
    names = [transform.id for transform in build_transforms(config, disabled={"ansi_strip"})]
    assert "ansi_strip" not in names
    assert "progress_collapse" in names
