"""Admin "Connected apps" REST routes — `GET`/`DELETE /api/v1/oauth/clients...` (mcp-oauth plan,
task 08; docs/plans/mcp-oauth/task-08-revoke-admin-api.md; docs/plans/mcp-oauth/DESIGN.md
§"Admin management UI").

Unlike every route in `app.routes.oauth_routes` (bare RFC 6749 `OAuthError` shape, per-IP rate
limiting, no admin session involved), these two are gated by the SAME `require_admin` cookie
session every other admin REST route (`app.routes.content_routes`) uses — a sibling router, not
folded into `oauth_routes.py`, precisely because the two surfaces answer errors differently (the
PRD §9 `ErrorEnvelope`, here, vs. `oauth_routes.py`'s bare `{"error", "error_description"}`).

CONVENTIONS.md §4: this router contains no `try/except` — `NotFoundError`
(`app.services.errors`) flows to its registered handler (`app.routes.errors`), which builds the
§9 envelope.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.models.schemas.common import ErrorEnvelope
from app.models.schemas.oauth import ConnectedApp, ConnectedAppsResponse
from app.routes.deps import get_session
from app.services.errors import NotFoundError
from app.services.oauth_clients import delete_client, list_connected_apps

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/oauth/clients",
    tags=["oauth-admin"],
    dependencies=[Depends(require_admin)],
    responses={401: {"model": ErrorEnvelope}},
)


@router.get(
    "",
    operation_id="oauth_clients_list",
    response_model=ConnectedAppsResponse,
)
def oauth_clients_list(session: Session = Depends(get_session)) -> ConnectedAppsResponse:
    """List every registered `OAuthClient` with its live-token summary, newest-first.

    `app.services.oauth_clients.list_connected_apps` does the actual (single-statement,
    aggregate-joined — see its own docstring) query; this route only converts each
    `ConnectedAppRow` dataclass to the wire-shape `ConnectedApp` model (`from_attributes=True`,
    so the conversion is a direct field-for-field mapping, no manual construction).
    """
    rows = list_connected_apps(session, now=datetime.now(UTC))
    return ConnectedAppsResponse(items=[ConnectedApp.model_validate(row) for row in rows])


@router.delete(
    "/{client_id}",
    operation_id="oauth_client_revoke",
    status_code=204,
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def oauth_client_revoke(client_id: str, session: Session = Depends(get_session)) -> Response:
    """Delete one `OAuthClient` outright — the admin "Disconnect" action.

    `app.services.oauth_clients.delete_client` issues a real DB-level `DELETE`; every dependent
    row (authorization codes, refresh tokens, consents, api tokens) is removed along with it via
    `ondelete="CASCADE"` FKs (that function's own docstring), so every token this client ever
    held stops working immediately.

    Raises:
        NotFoundError: `client_id` names no registered `OAuthClient` — 404 §9 envelope, "Client
            not found."
    """
    deleted = delete_client(session, client_id)
    if not deleted:
        raise NotFoundError("Client not found.")
    logger.info("oauth client deleted: client_id=%s", client_id)
    return Response(status_code=204)
