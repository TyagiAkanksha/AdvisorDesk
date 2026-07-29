"""Health endpoint — no auth, no DB (CONVENTIONS.md §5).

PRD §9 / CONVENTIONS.md §5: `GET /api/v1/healthz` lets container
healthchecks probe the bare process without touching Postgres.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", operation_id="healthz")
def healthz() -> dict[str, str]:
    """Liveness probe: `{"status": "ok"}`, always — no auth, no DB touch (PRD §9)."""
    return {"status": "ok"}
