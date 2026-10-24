"""Auto-quarantine guard (SPEC section 12.14). Session-scoped and reversible."""

from __future__ import annotations

from collections import defaultdict

from ctxproxy.config import Config


class Guard:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._fallbacks: dict[tuple[str, str], int] = defaultdict(int)
        self._drift: dict[tuple[str, str], int] = defaultdict(int)
        self._quarantined: dict[tuple[str, str], str] = {}

    def quarantined_for(self, session_id: str) -> set[str]:
        return {transform_id for (sid, transform_id) in self._quarantined if sid == session_id}

    def is_quarantined(self, session_id: str, transform_id: str) -> bool:
        return (session_id, transform_id) in self._quarantined

    def observe_fallback(self, session_id: str, transform_ids: list[str]) -> None:
        if not self.config.guard.enabled:
            return
        for transform_id in transform_ids:
            key = (session_id, transform_id)
            self._fallbacks[key] += 1
            if self._fallbacks[key] > self.config.guard.fallback_limit:
                self._quarantined[key] = "fallbacks"

    def observe_final_drift(
        self, session_id: str, cause: str | None, transform_ids: list[str]
    ) -> None:
        if not self.config.guard.enabled or not cause:
            return
        for transform_id in transform_ids:
            key = (session_id, transform_id)
            self._drift[key] += 1
            if self._drift[key] >= self.config.guard.our_fault_drift_limit:
                self._quarantined[key] = "our_fault_drift"

    def enable(self, session_id: str, transform_id: str) -> None:
        self._quarantined.pop((session_id, transform_id), None)
        self._fallbacks.pop((session_id, transform_id), None)
        self._drift.pop((session_id, transform_id), None)

    def status(self) -> list[dict[str, str]]:
        return [
            {
                "session_id": session_id,
                "transform_id": transform_id,
                "reason": reason,
            }
            for (session_id, transform_id), reason in self._quarantined.items()
        ]


__all__ = ["Guard"]
