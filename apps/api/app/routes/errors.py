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
    RateLimitedError,
)

# PRD §9 envelope status mapping, per task-03 brief: NotFoundError->404,
# ConflictError->409, AuthRequiredError->401, RateLimitedError->429,
# EmbeddingFailedError->502. ForbiddenError->403 added by phase-2 task-01
# (Google OAuth callback rejecting a non-allowlisted email).
_STATUS_BY_ERROR: dict[type[AppError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    AuthRequiredError: 401,
    ForbiddenError: 403,
    RateLimitedError: 429,
    EmbeddingFailedError: 502,
}


def _make_handler(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
    """Build a handler closing over `status_code` that renders the §9 envelope.

    The exception is typed as the base `Exception` (not `AppError`) because
    Starlette's `ExceptionHandler` type requires it — but only `AppError`
    subclasses are ever registered against this handler, so `.code` is
    always present at runtime.
    """

    def _handler(request: Request, exc: Exception) -> JSONResponse:
        code = getattr(exc, "code", "error")
        envelope = {"error": {"code": code, "message": str(exc)}}
        return JSONResponse(status_code=status_code, content=envelope)

    return _handler


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
    """
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc))
    envelope = {"error": {"code": f"http_{status_code}", "message": str(detail)}}
    return JSONResponse(status_code=status_code, content=envelope)


def register_error_handlers(app: FastAPI) -> None:
    """Register the PRD §9 `{"error": {"code", "message"}}` envelope for every error source.

    Iterates `_STATUS_BY_ERROR` once for the typed `AppError` family, so
    that envelope shape is produced by a single generic code path rather
    than one handler per exception type; then registers the two
    framework-native handlers (module docstring) that close the
    envelope-completion gap.

    Args:
        app: the FastAPI application to attach handlers to.
    """
    for error_type, status_code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error_type, _make_handler(status_code))

    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
