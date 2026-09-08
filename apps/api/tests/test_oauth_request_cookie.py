"""Pure unit tests for `app.auth.oauth_request.read_pending_authorization` (mcp-oauth plan, task
06 — controller carry-over, t05 review finding M-5).

docs/plans/mcp-oauth/task-06-consent-screen.md: t05's own test suite
(`tests/test_oauth_authorize.py`) only ever exercises this cookie's signing/verification indirectly,
through a full HTTP round trip (`test_valid_request_303_sets_httponly_cookie`,
`test_tampered_cookie_is_ignored`) — no test drives `read_pending_authorization` directly with a
value crafted to hit each of its own internal branches (expiry, shape mismatch, wrong secret). This
module is that direct, whitebox coverage: no DB, no FastAPI `TestClient`, no HTTP at all — just
`Settings` + `app.auth.oauth_request`'s own functions, plus `itsdangerous` directly (the same
library `_serializer` wraps) to mint values `mint_pending_authorization` itself can't produce
(a stale timestamp, a malformed payload).

`app.auth.oauth_request` (task 05) already implements every behavior this file pins — nothing here
is new production code's RED coverage. Every test below is expected to ALREADY PASS at RED; see the
test-author report for the reasoning per case (this file exists to lock the *current*, already-
correct behavior in place, per the controller's carry-over, not to drive new implementation work).

Stale-timestamp minting (no `freezegun`; `pyproject.toml`'s dev dependency group has no such
package): `read_pending_authorization` calls `_serializer(settings).loads(value,
max_age=AUTHORIZE_MAX_AGE_SECONDS)` — itsdangerous's own `TimestampSigner.sign` embeds
`self.get_timestamp()` (default `int(time.time())`) into the signed payload. Passing
`signer=_StaleTimestampSigner` to a throwaway `URLSafeTimedSerializer` (same secret, same
`_SALT` `app.auth.oauth_request` itself uses — imported directly, since this file is deliberately
whitebox) overrides just that one method to report a timestamp already older than
`AUTHORIZE_MAX_AGE_SECONDS`, so the value is expired the instant it's minted — no sleep, no faked
wall clock, no dependency on wall-clock time at all when the test runs.
"""

from __future__ import annotations

import dataclasses
import time

from itsdangerous import TimestampSigner, URLSafeTimedSerializer

from app.auth.oauth_request import (
    _SALT,
    AUTHORIZE_MAX_AGE_SECONDS,
    PendingAuthorization,
    mint_pending_authorization,
    read_pending_authorization,
)
from app.config import Settings

_PENDING = PendingAuthorization(
    client_id="adkc_unit-test-client",
    redirect_uri="https://claude.ai/api/mcp/auth_callback",
    #: RFC 7636 Appendix B's worked example — same literal `tests/oauth_helpers.py`/
    #: `tests/test_oauth_authorize.py` use; its actual value is irrelevant to this file (nothing
    #: here verifies PKCE), reused only so this fixture looks like a real pending request.
    code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    resource="https://api.example/api/v1/mcp",
    scope="mcp",
    state="xyz",
    nonce="unit-test-nonce",
)


class _StaleTimestampSigner(TimestampSigner):
    """A `TimestampSigner` whose `get_timestamp()` always reports a moment already older than
    `AUTHORIZE_MAX_AGE_SECONDS` — see module docstring for why this replaces `freezegun`/sleeping.
    """

    def get_timestamp(self) -> int:
        return int(time.time()) - AUTHORIZE_MAX_AGE_SECONDS - 60


def _settings(*, session_secret: str = "test-secret") -> Settings:
    """Build a `Settings` explicitly for this file — never read the real `.env` (CONVENTIONS §10).

    Only `session_secret` matters to `read_pending_authorization`/`mint_pending_authorization`.
    """
    return Settings(session_secret=session_secret)


def _sign_raw_payload(payload: dict[str, object], settings: Settings) -> str:
    """Sign an arbitrary dict as `app.auth.oauth_request._serializer` would, bypassing
    `mint_pending_authorization` (which requires a well-formed `PendingAuthorization`) — the only
    way to construct a validly-SIGNED but shape-invalid cookie value for the missing/wrong-typed
    field cases below.
    """
    return URLSafeTimedSerializer(settings.session_secret.get_secret_value(), salt=_SALT).dumps(
        payload
    )


def test_fresh_value_round_trips() -> None:
    """A value minted right now, read back immediately, recovers the exact same
    `PendingAuthorization` — the ordinary case every other test in this plan relies on implicitly.
    """
    settings = _settings()
    value = mint_pending_authorization(_PENDING, settings)

    result = read_pending_authorization(value, settings)

    assert result == _PENDING


def test_wrong_secret_returns_none() -> None:
    """A value minted under one `session_secret`, read back under a DIFFERENT one, fails
    signature verification -> `None` (never a raised `BadData`)."""
    value = mint_pending_authorization(_PENDING, _settings(session_secret="secret-a"))

    result = read_pending_authorization(value, _settings(session_secret="secret-b"))

    assert result is None


def test_expired_value_returns_none() -> None:
    """A value whose embedded timestamp is already older than `AUTHORIZE_MAX_AGE_SECONDS` at the
    moment it's minted -> `None` (itsdangerous's `SignatureExpired`, a `BadData` subclass, is
    caught the same way a tampered signature is)."""
    settings = _settings()
    stale_serializer = URLSafeTimedSerializer(
        settings.session_secret.get_secret_value(), salt=_SALT, signer=_StaleTimestampSigner
    )
    value = stale_serializer.dumps(dataclasses.asdict(_PENDING))

    result = read_pending_authorization(value, settings)

    assert result is None


def test_missing_field_returns_none() -> None:
    """A validly-SIGNED payload missing one of `PendingAuthorization`'s fields (`nonce`) -> `None`
    — the `set(raw) != expected_fields` shape check, not a `TypeError` from the dataclass
    constructor rejecting an unexpected keyword set."""
    settings = _settings()
    payload = dataclasses.asdict(_PENDING)
    del payload["nonce"]
    value = _sign_raw_payload(payload, settings)

    result = read_pending_authorization(value, settings)

    assert result is None


def test_wrong_typed_field_returns_none() -> None:
    """A validly-SIGNED payload with the right field NAMES but a wrong-typed value (`client_id` as
    an int, not a `str`) -> `None` — the per-field `isinstance` check, not a downstream crash the
    first time calling code treats `pending.client_id` as a string."""
    settings = _settings()
    payload = dataclasses.asdict(_PENDING)
    payload["client_id"] = 12345
    value = _sign_raw_payload(payload, settings)

    result = read_pending_authorization(value, settings)

    assert result is None


def test_none_value_returns_none() -> None:
    """No cookie at all (`value is None`, e.g. the header was never sent) -> `None`."""
    assert read_pending_authorization(None, _settings()) is None


def test_empty_string_returns_none() -> None:
    """An empty cookie value -> `None` (fails signature verification, same as any other garbage)."""
    assert read_pending_authorization("", _settings()) is None


def test_garbage_string_returns_none() -> None:
    """An arbitrary, never-signed-by-this-app string -> `None`, never a raised `BadData`."""
    assert read_pending_authorization("garbage", _settings()) is None
