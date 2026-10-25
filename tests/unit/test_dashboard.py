"""Dashboard, admin API and admin security (P5)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from starlette.testclient import TestClient

from ctxoptimizer.config import Config
from ctxoptimizer.server import create_app


def _config(tmp_path: Path) -> Config:
    return Config.model_validate({"telemetry": {"db_path": str(tmp_path / "ctxoptimizer.db")}})


@contextmanager
def _client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(_config(tmp_path))
    headers = {
        "x-ctxoptimizer-admin-token": app.state.admin_token,
        "x-ctxoptimizer-csrf": app.state.csrf_token,
    }
    with TestClient(app, base_url="http://127.0.0.1", headers=headers) as client:
        yield client


def test_overview_page(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/_ctxoptimizer/")
    assert response.status_code == 200
    assert "ctxoptimizer" in response.text
    assert "Recent requests" in response.text
    assert "No requests recorded yet" in response.text


def test_summary_api(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/_ctxoptimizer/api/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == 1
    assert body["requests"] == 0
    assert body["cost_usd"] == 0.0


def test_requests_api_empty(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/_ctxoptimizer/api/requests")
    assert response.status_code == 200
    assert response.json()["requests"] == []


def test_api_limit_is_clamped(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/_ctxoptimizer/api/requests?limit=9999")
    assert response.status_code == 200


def test_waste_page_and_apis(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/_ctxoptimizer/waste")
        findings = client.get("/_ctxoptimizer/api/waste")
        recommendations = client.get("/_ctxoptimizer/api/recommend")
    assert page.status_code == 200
    assert "Waste Opportunities" in page.text
    assert "No findings yet" in page.text
    assert findings.json()["findings"] == []
    assert recommendations.json()["recommendations"] == []


def test_admin_pages_and_apis(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        for path in (
            "/_ctxoptimizer/live",
            "/_ctxoptimizer/sessions",
            "/_ctxoptimizer/requests",
            "/_ctxoptimizer/transforms",
            "/_ctxoptimizer/pricing",
            "/_ctxoptimizer/settings",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
        assert client.get("/_ctxoptimizer/api/sessions").json()["sessions"] == []
        assert client.get("/_ctxoptimizer/api/transforms").json()["transforms"]
        assert client.get("/_ctxoptimizer/api/pricing").json()["models"]
        assert client.get("/_ctxoptimizer/api/guard").json()["quarantined"] == []
        assert client.get("/_ctxoptimizer/requests/missing").status_code == 404
        assert client.get("/_ctxoptimizer/api/requests/missing").status_code == 404


def test_pricing_page_renders_bundled_rates(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/_ctxoptimizer/pricing")
    assert response.status_code == 200
    assert "Pricing (" in response.text
    assert "anthropic" in response.text


def test_admin_requires_token_and_host_allowlist(tmp_path: Path) -> None:
    app = create_app(_config(tmp_path))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/_ctxoptimizer/api/summary").status_code == 401
        assert client.get("/_ctxoptimizer/health").status_code == 200
    with TestClient(
        app,
        base_url="http://evil.example",
        headers={"x-ctxoptimizer-admin-token": app.state.admin_token},
    ) as client:
        assert client.get("/_ctxoptimizer/api/summary").status_code == 403


def test_token_query_sets_cookie_and_no_cors(tmp_path: Path) -> None:
    app = create_app(_config(tmp_path))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(f"/_ctxoptimizer/api/summary?token={app.state.admin_token}")
        assert response.status_code == 200
        assert "ctxoptimizer_admin" in response.cookies
        assert "access-control-allow-origin" not in response.headers
        assert client.get("/_ctxoptimizer/api/summary").status_code == 200
