"""Ingress: health, admin 404 and forwarding hand-off."""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from ctxproxy.config import Config
from ctxproxy.routing import Route
from ctxproxy.server import create_app


async def _echo_forward(request: Request, route: Route, config: Config) -> JSONResponse:
    return JSONResponse(
        {
            "provider": route.provider.value,
            "endpoint": route.endpoint.value,
            "upstream": route.upstream_name,
            "path": route.path,
            "query": route.query,
            "project": route.project,
            "mode": route.mode.value,
        }
    )


def _config(tmp_path: Path) -> Config:
    return Config.model_validate(
        {
            "upstreams": {
                "anthropic": "https://api.anthropic.com",
                "openai": "https://api.openai.com",
                "gemini": "https://generativelanguage.googleapis.com",
                "ollama": "http://127.0.0.1:11434",
                "deepseek": "https://api.deepseek.com",
            },
            "telemetry": {"db_path": str(tmp_path / "ctxproxy.db")},
        }
    )


def test_health_endpoint(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.get("/_ctxproxy/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["mode"] == "shadow"
    assert "openai" in body["upstreams"]


def test_unknown_admin_path_is_404(tmp_path: Path) -> None:
    app = create_app(_config(tmp_path))
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"x-ctxproxy-admin-token": app.state.admin_token},
    ) as client:
        response = client.get("/_ctxproxy/api/nope")
    assert response.status_code == 404


def test_default_route_is_forwarded(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path), forwarder=_echo_forward)) as client:
        response = client.post("/v1/chat/completions")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert body["endpoint"] == "chat"
    assert body["upstream"] == "openai"


def test_named_upstream_is_forwarded_with_query(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path), forwarder=_echo_forward)) as client:
        response = client.post("/u/deepseek/chat/completions?beta=true")
    body = response.json()
    assert response.status_code == 200
    assert body["upstream"] == "deepseek"
    assert body["path"] == "/chat/completions"
    assert body["query"] == "beta=true"


def test_project_prefix_reaches_forwarder(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path), forwarder=_echo_forward)) as client:
        response = client.post("/p/myrepo/v1/messages")
    body = response.json()
    assert body["project"] == "myrepo"
    assert body["provider"] == "anthropic"


def test_unknown_upstream_is_404(tmp_path: Path) -> None:
    with TestClient(create_app(_config(tmp_path), forwarder=_echo_forward)) as client:
        response = client.post("/u/missing/chat/completions")
    assert response.status_code == 404
