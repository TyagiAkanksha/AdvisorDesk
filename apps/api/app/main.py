"""Wiring only: engine, session factory, create_app — nothing imports main (CONVENTIONS.md §2).

CONVENTIONS.md §5: `app/main.py` is the only wiring point — load settings,
build the engine + session factory, call `create_app(...)`, expose `app`.
It's also the only place that requires `DATABASE_URL` to be non-empty;
`Settings`/`create_app` themselves stay DB-less so tests and the OpenAPI
baseline export don't need a database.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.factory import create_app

settings: Settings = Settings()
if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL is required to run app.main but Settings().database_url "
        "is empty. Set the DATABASE_URL environment variable (PRD §9)."
    )

engine: Engine = make_engine(settings.database_url)
session_factory: sessionmaker[Session] = make_session_factory(engine)

app: FastAPI = create_app(session_factory=session_factory, settings=settings)
