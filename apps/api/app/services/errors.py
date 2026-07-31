"""Typed error family — services raise these; they never build HTTP responses.

CONVENTIONS.md §4: routes contain no `try/except`. Each exception carries a
stable `code` string; `app.routes.errors::register_error_handlers` maps
every subtype to an HTTP status and builds the PRD §9 envelope
`{"error": {"code", "message"}}` generically, from one registration loop.
"""

from __future__ import annotations


class AppError(Exception):
    """Base of AdvisorDesk's typed error family (CONVENTIONS.md §4).

    Args:
        message: human-readable text returned verbatim as the §9 envelope's
            `message` field.
    """

    code: str = "error"

    def __init__(self, message: str) -> None:
        super().__init__(message)


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
