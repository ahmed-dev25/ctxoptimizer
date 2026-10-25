"""Auto-quarantine guard (SPEC section 12.14). Session-scoped and reversible."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from ctxproxy.config import Config


class Guard:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._fallbacks: dict[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(
                maxlen=max(
                    1,
                    config.guard.fallback_window,
                    config.guard.fallback_limit + 1,
                )
            )
        )
        self._drift: dict[tuple[str, str], int] = defaultdict(int)
        self._quarantined: dict[tuple[str, str], str] = {}
        self._recovery: dict[tuple[str, str], int] = defaultdict(int)
        self._store: object | None = None

    def bind_store(self, store: object) -> None:
        """Attach the telemetry store so quarantine events are persisted."""
        self._store = store

    def _record(self, session_id: str, transform_id: str, reason: str) -> None:
        record = getattr(self._store, "record_guard_event", None)
        if callable(record):
            record(session_id, transform_id, reason, {"limit": self.config.guard.fallback_limit})

    def quarantined_for(self, session_id: str) -> set[str]:
        return {transform_id for (sid, transform_id) in self._quarantined if sid == session_id}

    def is_quarantined(self, session_id: str, transform_id: str) -> bool:
        return (session_id, transform_id) in self._quarantined

    def observe_fallback(self, session_id: str, transform_ids: list[str]) -> None:
        if not self.config.guard.enabled:
            return
        for transform_id in transform_ids:
            key = (session_id, transform_id)
            self._fallbacks[key].append(time.time())
            if len(self._fallbacks[key]) > self.config.guard.fallback_limit:
                self._quarantined[key] = "fallbacks"
                self._record(session_id, transform_id, "fallbacks")

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
                self._record(session_id, transform_id, "our_fault_drift")

    def observe_request(self, session_id: str) -> None:
        """Count successful requests and optionally auto-re-enable."""
        if not self.config.guard.enabled or self.config.guard.auto_reenable <= 0:
            return
        for key in list(self._quarantined):
            if key[0] != session_id:
                continue
            self._recovery[key] += 1
            if self._recovery[key] >= self.config.guard.auto_reenable:
                self.enable(*key)

    def observe_expand_health(self, session_id: str) -> None:
        """Quarantine omission transforms when expand errors are too high."""
        if not self.config.guard.enabled or self._store is None:
            return
        from ctxproxy.telemetry.expand import expand_stats

        path = getattr(self._store, "path", None)
        stats = expand_stats(db_path=path) if path is not None else expand_stats()
        if stats["total"] < 10:
            return
        errors = int(stats["errors"])
        if errors / max(int(stats["total"]), 1) <= self.config.guard.expand_error_rate:
            return
        for transform_id in ("cache_serve", "stale_result_elision"):
            key = (session_id, transform_id)
            if key not in self._quarantined:
                self._quarantined[key] = "expand_errors"
                self._record(session_id, transform_id, "expand_errors")

    def enable(self, session_id: str, transform_id: str) -> None:
        self._quarantined.pop((session_id, transform_id), None)
        self._fallbacks.pop((session_id, transform_id), None)
        self._drift.pop((session_id, transform_id), None)
        self._recovery.pop((session_id, transform_id), None)
        record = getattr(self._store, "record_guard_event", None)
        if callable(record):
            record(session_id, transform_id, "enabled", {"cleared": True}, cleared_ts=time.time())

    def disable(self, session_id: str, transform_id: str, reason: str = "manual") -> None:
        self._quarantined[(session_id, transform_id)] = reason
        self._record(session_id, transform_id, reason)

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
