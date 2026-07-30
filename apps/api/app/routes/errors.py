"""Maps the typed error family (`app.services.errors`) to the PRD §9 envelope, exactly once.

CONVENTIONS.md §4: `register_error_handlers(app)` is the single place an
HTTP response gets built from a typed exception — routes never contain
`try/except`; rollback happens in the `get_session` dependency instead.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import (
    AppError,
    AuthRequiredError,
    ConflictError,
    EmbeddingFailedError,
    NotFoundError,
    RateLimitedError,
)

# PRD §9 envelope status mapping, per task-03 brief: NotFoundError->404,
# ConflictError->409, AuthRequiredError->401, RateLimitedError->429,
# EmbeddingFailedError->502.
_STATUS_BY_ERROR: dict[type[AppError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    AuthRequiredError: 401,
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


def register_error_handlers(app: FastAPI) -> None:
    """Register the PRD §9 `{"error": {"code", "message"}}` envelope for the typed error family.

    Iterates `_STATUS_BY_ERROR` once, so the envelope shape is produced by a
    single generic code path rather than one handler per exception type.

    Args:
        app: the FastAPI application to attach handlers to.
    """
    for error_type, status_code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error_type, _make_handler(status_code))
