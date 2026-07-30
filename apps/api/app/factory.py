"""`create_app()` — the single FastAPI application constructor (CONVENTIONS.md §5).

Must succeed with no database and no env vars, so DB-less tests and the
`openapi.json` baseline export (CONVENTIONS.md §8) can both build a real
app. Every later route task includes its router here.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.auth.oauth import GoogleOAuthClient
from app.config import Settings
from app.routes.auth_routes import router as auth_router
from app.routes.errors import register_error_handlers
from app.routes.health_routes import router as health_router

_API_PREFIX = "/api/v1"


def create_app(
    session_factory: sessionmaker[Session] | None = None,
    settings: Settings | None = None,
    oauth_client: GoogleOAuthClient | None = None,
) -> FastAPI:
    """Build the AdvisorDesk FastAPI application.

    CONVENTIONS.md §5: no module-level engine/session/settings globals —
    everything request-scoped is stashed on `app.state` and read back
    through `app.routes.deps` (`get_session`, `get_settings`,
    `get_oauth_client`). The `/api/v1` prefix (PRD §5) is applied exactly
    here, once, so route modules declare bare paths.

    Args:
        session_factory: an optional SQLAlchemy session factory (from
            `app.db.make_session_factory`). `None` means DB-less: routes
            that depend on `get_session` raise `RuntimeError` at request
            time rather than silently working. `app/main.py` is the only
            caller that wires a real one.
        settings: an optional `Settings` instance. `None` builds
            `Settings()` from the environment, which itself succeeds with
            zero env vars set (PRD §9 defaults).
        oauth_client: an optional `GoogleOAuthClient` (real
            `HttpxGoogleOAuthClient` or a test fake). `None` means no auth
            route that dereferences it may be exercised — mirrors
            `session_factory`'s DB-less mode; `app/main.py` is the only
            caller that wires a real one.

    Returns:
        A configured `FastAPI` app instance.
    """
    resolved_settings = settings if settings is not None else Settings()

    app = FastAPI(title="AdvisorDesk API")
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.oauth_client = oauth_client

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(health_router, prefix=_API_PREFIX)
    app.include_router(auth_router, prefix=_API_PREFIX)

    return app
