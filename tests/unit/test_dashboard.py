"""Dashboard v0 and admin summary/requests API (P2-6)."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from ctxproxy.config import Config
from ctxproxy.server import create_app


def _config(tmp_path: Path) -> Config:
    return Config.model_validate({"telemetry": {"db_path": str(tmp_path / "ctxproxy.db")}})


def test_overview_page(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.get("/_ctxproxy/")
    assert response.status_code == 200
    assert "ctxproxy" in response.text
    assert "Recent requests" in response.text
    assert "No requests recorded yet" in response.text


def test_summary_api(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.get("/_ctxproxy/api/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == 1
    assert body["requests"] == 0
    assert body["cost_usd"] == 0.0


def test_requests_api_empty(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.get("/_ctxproxy/api/requests")
    assert response.status_code == 200
    assert response.json()["requests"] == []


def test_api_limit_is_clamped(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.get("/_ctxproxy/api/requests?limit=9999")
    assert response.status_code == 200


def test_waste_page_and_apis(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        page = client.get("/_ctxproxy/waste")
        findings = client.get("/_ctxproxy/api/waste")
        recommendations = client.get("/_ctxproxy/api/recommend")
    assert page.status_code == 200
    assert "Waste Opportunities" in page.text
    assert "No findings yet" in page.text
    assert findings.json()["findings"] == []
    assert recommendations.json()["recommendations"] == []
