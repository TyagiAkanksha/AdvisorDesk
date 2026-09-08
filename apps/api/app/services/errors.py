"""Typed error family — services raise these; they never build HTTP responses.

CONVENTIONS.md §4: routes contain no `try/except`. Each exception carries a
stable `code` string; `app.routes.errors::register_error_handlers` maps
every subtype to an HTTP status and builds the PRD §9 envelope
`{"error": {"code", "message"}}` generically, from one registration loop.
"""

from __future__ import annotations

from collections.abc import Mapping


class AppError(Exception):
    """Base of AdvisorDesk's typed error family (CONVENTIONS.md §4).

    Args:
        message: human-readable text returned verbatim as the §9 envelope's
            `message` field.
        headers: optional extra HTTP response headers to forward verbatim onto the rendered
            §9 envelope response (`app.routes.errors._make_handler`). `None` (the default) for
            every pre-existing raise site — additive, keyword-only, backward compatible.
            mcp-oauth plan, task 03: `app.mcp.server` raises `AuthRequiredError` with
            `headers={"WWW-Authenticate": ...}` (RFC 9728 §5.1) so a claude.ai connector can
            discover the protected-resource metadata document from a bare 401, without this
            base class (or any other `AppError` subclass) needing to know that concept exists.
    """

    code: str = "error"

    def __init__(self, message: str, *, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(message)
        self.headers: Mapping[str, str] | None = headers


class NotFoundError(AppError):
    """A requested resource does not exist, or is soft-deleted (PRD §4.1) — maps to 404."""

    code = "not_found"


class ConflictError(AppError):
    """A uniqueness or state-transition conflict (e.g. duplicate slug) — maps to 409."""

    code = "conflict"


class AuthRequiredError(AppError):
    """An admin route was hit without a valid session (PRD §9 auth security) — maps to 401."""

    code = "auth_required"


class ForbiddenError(AppError):
    """A valid identity is not authorized for the requested action — maps to 403.

    PRD §5.1/§9: a Google login outside `ADMIN_EMAILS` is a real Google
    identity (authentication succeeded) but is forbidden from AdvisorDesk
    admin access — distinct from `AuthRequiredError`'s "no/invalid session"
    (401).
    """

    code = "forbidden"


class RateLimitedError(AppError):
    """A public-chat request exceeded a §9 rate limit — maps to 429."""

    code = "rate_limited"


class EmbeddingFailedError(AppError):
    """The embedding provider call failed during publish/re-embed (PRD §4) — maps to 502."""

    code = "embedding_failed"


class OAuthExchangeError(AppError):
    """Google's OAuth token/userinfo exchange failed (PRD §5.1) — maps to 502.

    Final review, finding C-3 / t01 M14: `app.auth.oauth.HttpxGoogleOAuthClient.exchange_code`
    previously let a non-2xx Google response (`httpx.Response.raise_for_status()`) or a
    userinfo payload missing `"email"` (`payload["email"]` `KeyError`) escape as an unhandled
    500 with a plain-text/traceback body — reachable from `/auth/callback` on a reused or
    expired authorization `code`, or any transient Google-side failure. Grouped with
    `EmbeddingFailedError` under 502 (Bad Gateway): both are "an external dependency this
    request needed failed", the closest existing fit in this family rather than inventing a
    dedicated status for one more upstream-failure case.
    """

    code = "oauth_exchange_failed"


class ToolNotFoundError(AppError):
    """An MCP tool name has no registered `ToolSpec` (phase-5 task-01, PRD §6) — maps to 404.

    Raised by `app.mcp.runtime.call_tool` when `name` isn't in the tool registry — the same
    "addressing something that doesn't exist" shape `NotFoundError` covers for a `content_id`,
    kept as a distinct type/code (`tool_not_found` vs `not_found`) since the two are addressing
    different kinds of things (a tool name vs. a `Content`/`Tag`/`User` row) and a caller (the
    agent loop, task-03) may want to branch on which one it hit.
    """

    code = "tool_not_found"


class OAuthError(AppError):
    """RFC 6749 §5.2-shaped error for /api/v1/oauth/* endpoints (rendered by app.routes.errors).

    Unlike every other `AppError` subclass — which renders through the generic PRD §9
    `{"error": {"code", "message"}}` envelope built by `app.routes.errors._make_handler` — this
    one renders as RFC 6749 §5.2's own bare `{"error": "<code>", "error_description":
    "<description>"}` shape (mcp-oauth plan, task 04; docs/plans/mcp-oauth/DESIGN.md §"Error
    handling"). `app.routes.errors._oauth_error_handler` is registered specifically for this
    type, via `app.add_exception_handler(OAuthError, _oauth_error_handler)` — Starlette resolves
    a registered handler by walking `type(exc).__mro__` and picking the first match, most
    specific first, so this handler wins over the generic `AppError` one (this class's own base)
    regardless of which order `register_error_handlers` adds them in.

    Args:
        error: the RFC 6749 §5.2 / RFC 7591 §3 machine-readable error code (e.g.
            `"invalid_client_metadata"`, `"invalid_redirect_uri"`, `"invalid_scope"`).
        description: a human-readable explanation, returned verbatim as `error_description`.
        status_code: the HTTP status this error renders as. Defaults to 400 (RFC 6749 §5.2's
            default for a malformed/invalid registration request); e.g. an `"invalid_client"`
            error uses 401 instead.
    """

    code = "oauth_error"

    def __init__(self, error: str, description: str, *, status_code: int = 400) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code


class ToolInputError(AppError):
    """An MCP tool call's `arguments` failed its Pydantic args-model validation — maps to 422.

    Raised by `app.mcp.runtime.call_tool`; the message names the offending field(s) (mirrors
    `app.routes.errors._validation_error_handler`'s `loc: msg` shape for FastAPI's own
    `RequestValidationError`, the closest existing precedent for "a caller sent bad structured
    input" in this codebase) so both a human operator and the agent loop's self-correction pass
    (PRD §6: "surface the error to the model once for self-correction") can see which argument
    was wrong.
    """

    code = "tool_input_error"
