"""Wiring only: engine, session factory, create_app — nothing imports main (CONVENTIONS.md §2).

CONVENTIONS.md §5: `app/main.py` is the only wiring point — load settings,
build the engine + session factory, call `create_app(...)`, expose `app`.
It's also the only place that requires `DATABASE_URL` and `SESSION_SECRET`
to be non-empty, unconditionally, and `GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI`/`ADMIN_EMAILS` to be non-empty
outside dev (phase-2 task-01 review round 1, finding I1; narrowed in review
round 2 — see below; `ADMIN_EMAILS` added by the phase-2 final review,
finding C-6). A real deployment booted without one of these would otherwise
sign every session with an empty secret / talk to Google with an empty
client id / lock every admin out of `/auth/callback` silently, which is far
worse than a boot-time crash.
`Settings`/`create_app` themselves stay DB-less and secret-less so tests and
the OpenAPI baseline export don't need either a database or real OAuth
credentials.

Review round 2: round 1 made all five guards unconditional, which broke the
documented offline dev path (README: `cp .env.example .env`, set
`DATABASE_URL`, `docker compose --profile local-db up`) — `.env.example`
ships the three `GOOGLE_*` vars empty, and Google credentials are
unobtainable offline by definition, so the api container crash-looped on
every fresh clone. `database_url`/`session_secret` stay unconditional (an
empty/known session-signing key is fail-open and never allowed, in any
environment); the three `GOOGLE_*` guards now fire only when
`not settings.is_dev` — in development the app boots without Google
credentials and admin login simply won't work until they're set, exactly as
`.env.example`'s comments now say.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.oauth import GoogleOAuthClient, HttpxGoogleOAuthClient
from app.config import Settings
from app.db import make_engine, make_session_factory
from app.factory import create_app

logger = logging.getLogger(__name__)


def _require_nonempty(value: str, env_var: str, settings_attr: str) -> None:
    """Raise `RuntimeError` naming `env_var` if `value` (read from `settings_attr`) is empty.

    The one guard idiom `app.main` applies to every required-at-boot secret
    (finding I1) — `Settings()` itself never enforces this so it stays
    zero-env-var constructible (CONVENTIONS.md §5) for DB-less tests/the
    OpenAPI export.

    Args:
        value: the resolved setting's plaintext value.
        env_var: the environment variable name to name in the error.
        settings_attr: the `Settings` attribute `value` came from, named in
            the error so the message points at both the env var to set and
            the field that read it back empty.

    Raises:
        RuntimeError: `value` is empty.
    """
    if not value:
        raise RuntimeError(
            f"{env_var} is required to run app.main but Settings().{settings_attr} "
            f"is empty. Set the {env_var} environment variable (PRD §9)."
        )


settings: Settings = Settings()
_require_nonempty(settings.database_url.get_secret_value(), "DATABASE_URL", "database_url")
_require_nonempty(settings.session_secret.get_secret_value(), "SESSION_SECRET", "session_secret")
if not settings.is_dev:
    # Google credentials are unobtainable offline by definition, so these
    # three guards are dev-exempt (review round 2) — an offline
    # `cp .env.example .env` + local-db boot must succeed with them empty;
    # admin login just won't work until real credentials are set. Every
    # other environment (anything where `is_dev` is False, i.e.
    # `ENVIRONMENT=production`) still fails fast on any of the three being
    # empty, same as before.
    _require_nonempty(settings.google_client_id, "GOOGLE_CLIENT_ID", "google_client_id")
    _require_nonempty(
        settings.google_client_secret.get_secret_value(),
        "GOOGLE_CLIENT_SECRET",
        "google_client_secret",
    )
    _require_nonempty(settings.google_redirect_uri, "GOOGLE_REDIRECT_URI", "google_redirect_uri")
    # Final review, finding C-6: an empty ADMIN_EMAILS in production boots
    # cleanly but locks EVERY Google identity out of `/auth/callback`
    # (`ForbiddenError` on every login attempt, PRD §5.1) — no admin could
    # ever sign in, and nothing at boot said so. Dev-exempt for the same
    # reason as the three GOOGLE_* guards above: the offline dev path must
    # still boot with it empty; admin login just won't work until it's set.
    _require_nonempty(settings.admin_emails, "ADMIN_EMAILS", "admin_emails")

if not settings.cors_origin_list:
    # Final review, finding C-1: an empty CORS_ORIGINS silently killed every
    # cross-origin request from apps/admin/apps/client in dev (no
    # Access-Control-Allow-Origin header on any preflight, so the browser
    # blocked the response before the admin app's sign-in flow ever saw it —
    # DOA at the user checkpoint). This stays a WARNING, not a boot-time
    # failure: a same-origin deployment (frontend served from the same
    # origin as the API, or a reverse proxy that makes them look same-origin
    # to the browser) legitimately needs no CORS allowlist at all, so
    # crash-failing here would be wrong for that case.
    logger.warning(
        "CORS_ORIGINS is empty — every cross-origin request (e.g. from apps/admin or "
        "apps/client on a different origin) will be rejected by the browser. Set "
        "CORS_ORIGINS in .env, or ignore this if the API is deployed same-origin with "
        "its frontend(s)."
    )

engine: Engine = make_engine(settings.database_url.get_secret_value())
session_factory: sessionmaker[Session] = make_session_factory(engine)
oauth_client: GoogleOAuthClient = HttpxGoogleOAuthClient.from_settings(settings)

app: FastAPI = create_app(
    session_factory=session_factory,
    settings=settings,
    oauth_client=oauth_client,
    # NoopChunkPipeline default (phase-3 task-02 wires the real embedding
    # pipeline here — see app.factory.create_app's chunk_pipeline docstring).
    chunk_pipeline=None,
)
