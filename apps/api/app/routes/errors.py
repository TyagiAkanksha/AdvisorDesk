"""Maps the typed error family (`app.services.errors`) to the PRD §9 envelope, exactly once.

CONVENTIONS.md §4: `register_error_handlers(app)` is the single place an
HTTP response gets built from a typed exception — routes never contain
`try/except`; rollback happens in the `get_session` dependency instead.

Envelope-completion amendment (phase-1 final-review decision, task-03
brief): FastAPI/Starlette raise their own native exceptions for cases the
typed `AppError` family never covers — a 422 body-validation failure
(`RequestValidationError`) and a framework-native 404/405/etc.
(`HTTPException`, e.g. an unmatched route). Left unregistered, those would
answer with FastAPI's own `{"detail": ...}` shape instead of the PRD §9
envelope. `_validation_error_handler`/`_http_exception_handler` close that
gap with codes `validation_error` and `http_<status>` respectively.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.errors import (
    AppError,
    AuthRequiredError,
    ConflictError,
    EmbeddingFailedError,
    ForbiddenError,
    NotFoundError,
    OAuthError,
    OAuthExchangeError,
    RateLimitedError,
    ToolInputError,
    ToolNotFoundError,
)

# PRD §9 envelope status mapping, per task-03 brief: NotFoundError->404,
# ConflictError->409, AuthRequiredError->401, RateLimitedError->429,
# EmbeddingFailedError->502. ForbiddenError->403 added by phase-2 task-01
# (Google OAuth callback rejecting a non-allowlisted email).
# OAuthExchangeError->502 added by the phase-2 final review (finding C-3 /
# t01 M14): a Google-side OAuth exchange failure, same "upstream dependency
# failed" status as EmbeddingFailedError.
# ToolNotFoundError->404 / ToolInputError->422 added by phase-5 task-01: the same statuses
# NotFoundError/`RequestValidationError` already use for the equivalent REST-side failures
# (unknown resource; caller-supplied structured input that doesn't validate) — an MCP tool
# call reuses both statuses rather than inventing new ones, per the task-01 brief's "choose
# sensible ones" instruction.
_STATUS_BY_ERROR: dict[type[AppError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    AuthRequiredError: 401,
    ForbiddenError: 403,
    RateLimitedError: 429,
    EmbeddingFailedError: 502,
    OAuthExchangeError: 502,
    ToolNotFoundError: 404,
    ToolInputError: 422,
}


def _make_handler(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
    """Build a handler closing over `status_code` that renders the §9 envelope.

    The exception is typed as the base `Exception` (not `AppError`) because
    Starlette's `ExceptionHandler` type requires it — but only `AppError`
    subclasses are ever registered against this handler, so `.code` is
    always present at runtime.

    mcp-oauth plan, task 03: also forwards `exc.headers` (the `AppError.headers` mapping added
    this task, `None` for every subclass that doesn't set it) onto the rebuilt `JSONResponse` —
    mirrors `_http_exception_handler`'s existing `headers=getattr(exc, "headers", None)` forward
    for `StarletteHTTPException`. `getattr` (not `exc.headers`) because this handler's `exc`
    parameter is typed as the base `Exception`, same reasoning as `.code` above; `JSONResponse`
    accepts `headers=None` (its default) with no special-casing needed here.
    """

    def _handler(request: Request, exc: Exception) -> JSONResponse:
        code = getattr(exc, "code", "error")
        envelope = {"error": {"code": code, "message": str(exc)}}
        headers = getattr(exc, "headers", None)
        return JSONResponse(status_code=status_code, content=envelope, headers=headers)

    return _handler


def _oauth_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Render an `OAuthError` as RFC 6749 §5.2's bare `{"error", "error_description"}` shape.

    mcp-oauth plan, task 04 (docs/plans/mcp-oauth/DESIGN.md §"Error handling"): every
    `/api/v1/oauth/*` endpoint answers a 4xx with this bare two-field body — never the rest of
    the app's nested PRD §9 `{"error": {"code", "message"}}` envelope — plus `Cache-Control:
    no-store` / `Pragma: no-cache` so an intermediary never caches a response body that can carry
    sensitive authorization-flow detail.

    Registered against `OAuthError` specifically (`register_error_handlers` below), not folded
    into the generic `_STATUS_BY_ERROR` loop above: Starlette resolves a registered exception
    handler by walking `type(exc).__mro__` and picking the first match, most-specific type
    first — so this handler wins over the generic `AppError` handler (`OAuthError`'s own base
    class) for any `OAuthError` instance, regardless of which order the two get registered in.

    The exception is typed as the base `Exception` (not `OAuthError`) for the same
    `Starlette.ExceptionHandler`-signature reason `_make_handler` above documents — only
    `OAuthError` itself is ever registered against this handler, so the `isinstance` assertion
    below always holds at runtime; it exists to narrow the type for mypy.
    """
    assert isinstance(exc, OAuthError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "error_description": exc.description},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render a body/query/path validation failure as the §9 envelope (code `validation_error`).

    Replaces FastAPI's default `{"detail": [...]}` shape for
    `RequestValidationError` (raised before any route body runs, e.g. a
    missing required field) with `{"error": {"code", "message"}}` — a 422,
    same as FastAPI's default status.

    Review round 1, finding F1: `str(exc)` renders FastAPI 0.140's
    *developer* form of a `RequestValidationError` — an absolute source
    path, the endpoint's stack frame, and (worst of all) the raw
    `'input': ...` value the caller submitted, verbatim, unauthenticated.
    `POST /content` with `{"body_md": {"secret": "s3cr3t-value"}}` echoed
    that literal secret back in the 422 body. The message is rebuilt here
    from `exc.errors()` using ONLY `loc`/`msg` — never `input`/`ctx`/`url`
    or any frame — so it can describe *which* field failed and *why*
    without ever repeating what the caller sent.
    """
    parts: list[str] = []
    if isinstance(exc, RequestValidationError):
        for error in exc.errors():
            loc = ".".join(str(segment) for segment in error["loc"])
            parts.append(f"{loc}: {error['msg']}" if loc else error["msg"])
    message = "; ".join(parts) if parts else "Validation error."
    envelope = {"error": {"code": "validation_error", "message": message}}
    return JSONResponse(status_code=422, content=envelope)


def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render a framework-native `HTTPException` as the §9 envelope (code `http_<status>`).

    Covers cases no typed `AppError` is ever raised for — most notably an
    unmatched route under `/api/v1` (Starlette's router 404s before any
    handler runs) — so those also answer with the §9 envelope instead of
    Starlette's default `{"detail": "Not Found"}`.

    Phase-6 task-04: forwards `exc.headers` onto the rebuilt `JSONResponse`. Surfaced by adding
    `methods=["POST"]` to the MCP bare-path `Route` (`app.mcp.server.mount_mcp_http`) — Starlette
    itself raises `HTTPException(status_code=405, headers={"Allow": "POST"})` for a
    method-mismatched route (`starlette.routing.Route.handle`), and this handler was silently
    dropping `exc.headers` when rebuilding the envelope response, which would have discarded that
    very `Allow` header (PRD §9's task-04 acceptance: `GET /api/v1/mcp` → 405 WITH `Allow: POST`).
    No prior route ever raised a header-bearing `HTTPException`, so this had no observable effect
    before now; forwarding is strictly more correct for any future one too.
    """
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc))
    headers = getattr(exc, "headers", None)
    envelope = {"error": {"code": f"http_{status_code}", "message": str(detail)}}
    return JSONResponse(status_code=status_code, content=envelope, headers=headers)


_INTERNAL_ERROR_ENVELOPE = {
    "error": {"code": "internal_error", "message": "Internal server error."}
}


def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render ANY exception not covered by a more specific handler above as the §9 envelope.

    Final review, finding F3 (t03 carried minor: "unhandled 500s bypass the
    §9 envelope"): a bug that raises a plain `Exception` (or any type not in
    `_STATUS_BY_ERROR`/`RequestValidationError`/`StarletteHTTPException`)
    previously fell through to Starlette's `ServerErrorMiddleware` default —
    a plain-text 500 body that, outside `debug=True`, is just `"Internal
    Server Error"` but is NOT the PRD §9 `{"error": {...}}` shape any
    frontend consumer of this API expects on every response, success or
    failure. The message is a fixed, generic string — never `str(exc)` —
    so no internal detail (a stack frame, a DB error string, anything)
    leaks through this path; the real exception still propagates to the
    server's own logs via Starlette's normal logging before this handler's
    response is built (FastAPI/Starlette re-raise-then-handle the exception
    through `ServerErrorMiddleware`, which logs it, then this handler
    supplies the response body).

    Registering a plain `Exception` handler via `add_exception_handler`
    still intercepts exceptions routed through `ServerErrorMiddleware` in
    the Starlette version this app pins (verified empirically —
    `tests/test_routes_errors.py`'s catch-all test uses
    `TestClient(raise_server_exceptions=False)` against a raising route and
    asserts this exact envelope) — `ServerErrorMiddleware` looks up a
    registered handler for the raised exception's type (falling back to
    `Exception` itself) before falling back to its own plain-text default,
    it does not bypass `add_exception_handler` registrations the way one
    might assume from "middleware runs outside the exception-handling
    layer".
    """
    return JSONResponse(status_code=500, content=_INTERNAL_ERROR_ENVELOPE)


def register_error_handlers(app: FastAPI) -> None:
    """Register the PRD §9 `{"error": {"code", "message"}}` envelope for every error source.

    Iterates `_STATUS_BY_ERROR` once for the typed `AppError` family, so
    that envelope shape is produced by a single generic code path rather
    than one handler per exception type; then registers the two
    framework-native handlers (module docstring) that close the
    envelope-completion gap, and finally the catch-all `Exception` handler
    (`_unhandled_exception_handler`) so literally nothing this app can raise
    ever answers outside the §9 envelope.

    Args:
        app: the FastAPI application to attach handlers to.
    """
    for error_type, status_code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error_type, _make_handler(status_code))

    # mcp-oauth plan, task 04: registered separately from the generic `AppError` family above,
    # even though `OAuthError` IS an `AppError` subclass — Starlette resolves handlers by walking
    # `type(exc).__mro__` and picking the first match, most-specific type first, so this handler
    # wins over the generic one for any `OAuthError` regardless of registration order.
    app.add_exception_handler(OAuthError, _oauth_error_handler)

    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
