"""Admin endpoint security: Host allowlist, token and CSRF (SPEC 16.1)."""

from __future__ import annotations

import hmac
import json
import os
import secrets
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from ctxoptimizer.config import LOOPBACK_HOSTS, Config, data_dir

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_HEALTH = "/_ctxoptimizer/health"


class AdminSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        config: Config,
        admin_token: str | None = None,
        csrf_token: str | None = None,
    ) -> None:
        super().__init__(app)
        self.config = config
        self.admin_token = admin_token or config.server.admin_token or secrets.token_urlsafe(24)
        self.csrf_token = csrf_token or secrets.token_urlsafe(24)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if not path.startswith("/_ctxoptimizer") or path == _HEALTH:
            return await call_next(request)

        host = (request.url.hostname or "").lower()
        allowed = set(LOOPBACK_HOSTS)
        if self.config.server.allow_remote:
            allowed.add(self.config.server.host.lower())
        if host not in allowed:
            return JSONResponse({"error": "forbidden admin host"}, status_code=403)

        supplied = (
            request.query_params.get("token")
            or request.headers.get("x-ctxoptimizer-admin-token")
            or request.cookies.get("ctxoptimizer_admin")
        )
        if not _same(supplied, self.admin_token):
            return JSONResponse({"error": "admin token required"}, status_code=401)

        if request.method in _MUTATING:
            csrf = request.headers.get("x-ctxoptimizer-csrf") or request.query_params.get("csrf")
            if not _same(csrf, self.csrf_token):
                return JSONResponse({"error": "csrf token required"}, status_code=403)

        response = await call_next(request)
        if request.query_params.get("token"):
            response.set_cookie(
                "ctxoptimizer_admin",
                self.admin_token,
                httponly=True,
                samesite="strict",
                path="/_ctxoptimizer",
            )
            response.set_cookie(
                "ctxoptimizer_csrf",
                self.csrf_token,
                httponly=False,
                samesite="strict",
                path="/_ctxoptimizer",
            )
        # No CORS support on admin endpoints (SPEC 16.1).
        if "access-control-allow-origin" in response.headers:
            del response.headers["access-control-allow-origin"]
        return response


def admin_credentials() -> tuple[str, str]:
    """Create a fresh per-run admin token and CSRF token."""
    return secrets.token_urlsafe(24), secrets.token_urlsafe(24)


def token_file() -> Path:
    return data_dir() / "admin-token.json"


def save_tokens(admin_token: str, csrf_token: str) -> Path:
    """Persist the per-run tokens for local CLI commands (0600 on POSIX)."""
    path = token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"admin_token": admin_token, "csrf_token": csrf_token}),
        encoding="utf-8",
    )
    if os.name == "posix":
        os.chmod(path, 0o600)
    return path


def load_tokens() -> tuple[str | None, str | None]:
    try:
        payload = json.loads(token_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    admin = payload.get("admin_token")
    csrf = payload.get("csrf_token")
    return (
        admin if isinstance(admin, str) else None,
        csrf if isinstance(csrf, str) else None,
    )


def _same(left: str | None, right: str) -> bool:
    if not left:
        return False
    return hmac.compare_digest(left, right)


__all__ = [
    "AdminSecurityMiddleware",
    "admin_credentials",
    "load_tokens",
    "save_tokens",
    "token_file",
]
