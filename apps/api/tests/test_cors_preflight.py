"""Fixer-owned test for final-review finding C-1 / F1: CORS was dead in dev.

`.env.example` shipped `CORS_ORIGINS=` (empty) and `.env` never set it either
(controller's phase-1/2 preflight notes never flagged it — it wasn't part of
the phase-1 §9 roster's non-empty defaults), so `app.factory.create_app`'s
`CORSMiddleware` was wired up correctly all along but always got an empty
`allow_origins=[]` — no cross-origin request from `apps/admin`/`apps/client`
(different origins, PRD §9/docs/FRONTEND-CONVENTIONS.md §1 pinned ports)
ever got an `Access-Control-Allow-Origin` header, so the browser blocked
every response before the admin sign-in flow could even see it.

This module proves the middleware itself has always worked correctly given a
non-empty `CORS_ORIGINS` (the fix is the `.env.example` default + `app.main`
boot warning, not `app.factory.create_app`, which took no code change here)
— DB-less (`CONVENTIONS.md §5`), since a CORS preflight never touches a
route handler.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app

_ALLOWED_ORIGIN = "http://localhost:3001"


def test_options_preflight_from_an_allowed_origin_gets_cors_headers() -> None:
    """A CORS preflight (`OPTIONS` + `Origin`/`Access-Control-Request-Method`) from an allowed
    origin gets `Access-Control-Allow-Origin` + `Access-Control-Allow-Credentials` back.

    Mirrors the exact browser preflight a real `fetch(..., {credentials:
    'include'})` from `apps/admin` sends before its first cross-origin
    request — the failure mode C-1 repro'd (a preflight with no
    `Access-Control-Allow-Origin` header, which the browser then blocks
    before the actual request is ever sent).
    """
    settings = Settings(cors_origins=f"{_ALLOWED_ORIGIN},http://localhost:3000")
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.options(
        "/api/v1/healthz",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_options_preflight_from_a_disallowed_origin_gets_no_cors_headers() -> None:
    """A preflight from an origin NOT in `CORS_ORIGINS` gets no allow-origin header — the
    allowlist actually restricts, it isn't a de facto wildcard.
    """
    settings = Settings(cors_origins=_ALLOWED_ORIGIN)
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.options(
        "/api/v1/healthz",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
