"""Admin mutating APIs, detail pages and diff/pricing (P5)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from starlette.testclient import TestClient

from ctxproxy.config import Config
from ctxproxy.models import WasteFinding
from ctxproxy.server import create_app


@contextmanager
def _client(tmp_path: Path) -> Iterator[tuple[TestClient, object]]:
    config = Config.model_validate(
        {
            "telemetry": {"db_path": str(tmp_path / "ctxproxy.db")},
            "pricing": {"file": str(tmp_path / "pricing.json")},
        }
    )
    app = create_app(config)
    headers = {
        "x-ctxproxy-admin-token": app.state.admin_token,
        "x-ctxproxy-csrf": app.state.csrf_token,
    }
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        yield client, app


def test_config_get_and_validated_patch(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _app):
        current = client.get("/_ctxproxy/api/config").json()["config"]
        assert current["server"]["admin_token"] == ""
        response = client.post(
            "/_ctxproxy/api/config",
            json={"mode": {"default": "active"}},
        )
        assert response.status_code == 200
        assert response.json()["config"]["mode"]["default"] == "active"
        bad = client.post("/_ctxproxy/api/config", json={"mode": {"default": "nope"}})
        assert bad.status_code == 400
        mode = client.post("/_ctxproxy/api/mode", json={"mode": "shadow"})
        assert mode.json()["mode"] == "shadow"


def test_mutating_admin_requires_csrf(tmp_path: Path) -> None:
    app = create_app(Config.model_validate({"telemetry": {"db_path": str(tmp_path / "c.db")}}))
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"x-ctxproxy-admin-token": app.state.admin_token},
    ) as client:
        response = client.post("/_ctxproxy/api/mode", json={"mode": "active"})
    assert response.status_code == 403


def test_new_pages_and_timeseries(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _app):
        for path in (
            "/_ctxproxy/doctor",
            "/_ctxproxy/sessions/unknown",
            "/_ctxproxy/api/transforms/stats",
            "/_ctxproxy/api/drift",
            "/_ctxproxy/api/timeseries?metric=cost&bucket=day",
            "/_ctxproxy/api/stale-elision/estimate?elided_tokens=8192"
            "&input_per_mtok=3&cache_read_per_mtok=0.3",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
        assert client.get("/_ctxproxy/doctor").text.count("bind host") == 1
        estimate = client.get(
            "/_ctxproxy/api/stale-elision/estimate?elided_tokens=8192"
            "&input_per_mtok=3&cache_read_per_mtok=0.3"
        ).json()
        assert estimate["label"] == "sim."


def test_live_sse_emits_a_snapshot(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _app):
        with client.stream("GET", "/_ctxproxy/api/live") as response:
            assert response.status_code == 200
            line = next(response.iter_lines())
    assert line.startswith("data: ")


def test_request_diff_uses_captured_blobs(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, app):
        before = app.state.blobs.put(b"before block")
        after = app.state.blobs.put(b"after block")
        app.state.store.record_request(
            {
                "request_id": "r-diff",
                "ts": time.time(),
                "session_id": "s",
                "provider": "anthropic",
                "endpoint": "messages",
                "mode": "active",
                "_captures": [
                    {
                        "transform_id": "stale_result_elision",
                        "location": "block-0",
                        "before_hash": before,
                        "after_hash": after,
                    }
                ],
            }
        )
        app.state.store.flush()
        page = client.get("/_ctxproxy/requests/r-diff")
        diff = client.get("/_ctxproxy/api/requests/r-diff/diff").json()
    assert page.status_code == 200
    assert "before block" in page.text and "after block" in page.text
    assert diff["blocks"][0]["before"] == "before block"
    assert diff["blocks"][0]["after"] == "after block"


def test_recommendation_dismissal_is_persisted(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, app):
        response = client.post(
            "/_ctxproxy/api/recommend/enable_cache_serve/dismiss",
            json={"days": 30},
        )
        assert response.status_code == 200
        assert "enable_cache_serve" in app.state.store.suppressed_recommendations()


def test_waste_status_memory_and_pricing_put(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, app):
        finding = WasteFinding(
            finding_id="f1",
            ts=time.time(),
            session_id="s",
            project=None,
            detector="schema_bloat",
            key_hash=b"k" * 16,
            request_id=None,
            occurrences=1,
            first_seen_ts=time.time(),
            last_seen_ts=time.time(),
            evidence={"tool": "x"},
            est_tokens_wasted=10,
            est_cost_usd=None,
        )
        app.state.analysis._findings.append(finding)
        response = client.post("/_ctxproxy/api/waste/f1/status", json={"status": "ack"})
        assert response.status_code == 200
        assert app.state.analysis.findings()[0].status == "ack"

        pricing = client.put(
            "/_ctxproxy/api/pricing",
            json={"models": [{"provider": "test", "match": "m", "input": 1, "output": 2}]},
        )
        assert pricing.status_code == 200
        models = client.get("/_ctxproxy/api/pricing").json()["models"]
        assert any(model["provider"] == "test" for model in models)
