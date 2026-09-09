"""Failing (RED) tests for the server-rendered consent screen and per-client consent record
(mcp-oauth plan, task 06): `GET /api/v1/oauth/authorize/continue` renders an HTML Approve/Deny page
the FIRST time an admin authorizes a given `client_id`; `POST /api/v1/oauth/authorize/decision`
records an `OAuthConsent` row on approve (or redirects `access_denied` on deny) and, on approve,
issues the code exactly like `_issue_code_and_redirect` always has; a later authorization for the
same `(user, client)` pair skips the page.

Task brief: docs/plans/mcp-oauth/task-06-consent-screen.md. Spec: docs/plans/mcp-oauth/DESIGN.md
§"Google bridge + consent", §"End-to-end flow" step 5-6, §"Decisions pinned" (server-rendered
consent on the API).

Today `oauth_authorize_continue` (task 05) goes straight from a resolved, allowlisted admin to a
minted code — no consent gate, no `OAuthConsent` row ever consulted or written — and
`POST /api/v1/oauth/authorize/decision` does not exist at all (a plain 404, the generic §9
`http_404` envelope from `app.routes.errors._http_exception_handler`, not this task's own OAuth
error shapes). No not-yet-existing name is imported at module level (`app.routes.oauth_consent_html`
and `app.services.oauth_consents` both land this task's GREEN step) — `_CONSENT_CSP` below is
defined locally as the brief's own pinned literal, mirroring `tests/test_oauth_authorize.py`'s own
`_AUTHORIZE_COOKIE_NAME` precedent ("brief-pinned literal, not assumed to be a module export, so
defined locally") — so this file collects cleanly and every test fails at ASSERTION time (a 302/404
where a 200/302/400/401/429 was expected), never at collection; see the test-author report for the
literal per-test failure observed.

CONVENTIONS.md §10: every test here requests `tmp_engine`/`db_session` (skipped by fixture name
when `TEST_DATABASE_URL` is unset). `_build_app`/`_build_settings`/`_register`/`_authorize_params`/
`_redirect_query` mirror `tests/test_oauth_authorize.py`'s own shapes exactly (same
`_ISSUER`/`_RESOURCE`/`_REDIRECT_URI`/RFC 7636 Appendix B vector/rate-limit-override pattern);
`_register` here additionally accepts an optional `client_name`, since the consent page displays it.
`follow_redirects=False` on every request in this file, same rationale as that file: several
redirect targets (the client's own `redirect_uri`) are deliberately off-app and unreachable from the
test process.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import UTC, datetime

import pytest
from auth_helpers import FakeGoogleOAuthClient, login_as
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAME
from app.config import Settings
from app.db import make_session_factory
from app.factory import create_app
from app.models import User
from app.models.oauth import OAuthAuthorizationCode, OAuthClient, OAuthConsent
from app.services.oauth_clients import delete_client

_ISSUER = "https://api.example"
_ADMIN_APP_URL = "https://admin.example"

_REGISTER_PATH = "/api/v1/oauth/register"
_AUTHORIZE_PATH = "/api/v1/oauth/authorize"
_CONTINUE_PATH = "/api/v1/oauth/authorize/continue"
_DECISION_PATH = "/api/v1/oauth/authorize/decision"

#: Not yet exported by any existing module (`app.routes.oauth_consent_html` lands this task's
#: GREEN step) — defined locally per this file's own module docstring.
_AUTHORIZE_COOKIE_NAME = "advisordesk_oauth_authz"
#: The header the consent page for `_REDIRECT_URI` is expected to carry once
#: `hotfix-csp-brief.md` lands: `consent_csp(_REDIRECT_URI)`'s own `CONSENT_CSP` base
#: (`form-action 'self'`) with `_REDIRECT_URI`'s origin (`https://claude.ai`) appended — the fix
#: for Chrome/Edge enforcing `form-action` against the 302 that FOLLOWS the consent form's POST
#: (the client's own redirect target), not just the form's own same-origin POST target. Was the
#: bare `"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"` before this hotfix;
#: still not assumed to be a module export, so defined locally per this file's own module
#: docstring.
_CONSENT_CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://claude.ai"

_REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
#: RFC 7636 Appendix B's worked example: `S256(_CODE_VERIFIER) == _CODE_CHALLENGE`.
_CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
#: The MCP resource indicator for `_ISSUER` (`Settings.mcp_resource_url`, mcp-oauth task 01).
_RESOURCE = f"{_ISSUER}/api/v1/mcp"
_STATE = "xyz"

#: `app.routes.oauth_consent_html.render_consent_page`'s hidden nonce input — task-06 brief's own
#: pinned shape (`<input type="hidden" name="nonce" value="...">`).
_NONCE_RE = re.compile(r'name="nonce" value="([^"]+)"')


def _build_settings(
    *,
    admin_emails: str = "admin@example.com",
    oauth_rate_limit_per_min: int = 30,
) -> Settings:
    """Build a `Settings` explicitly for tests — never read the real `.env` (CONVENTIONS §10)."""
    return Settings(
        session_secret="test-secret",
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        admin_emails=admin_emails,
        mcp_http_enabled=True,
        oauth_issuer_url=_ISSUER,
        admin_app_url=_ADMIN_APP_URL,
        oauth_rate_limit_per_min=oauth_rate_limit_per_min,
    )


def _build_app(tmp_engine: Engine, *, settings: Settings | None = None) -> FastAPI:
    """Build a real, DB-backed app with a fake Google OAuth seam injected.

    `settings` defaults to `_build_settings()`'s own defaults.
    """
    return create_app(
        session_factory=make_session_factory(tmp_engine),
        settings=settings if settings is not None else _build_settings(),
        oauth_client=FakeGoogleOAuthClient(),
    )


def _register(client: TestClient, *, client_name: str | None = None) -> str:
    """Register a fresh OAuth client (`POST /oauth/register`, task 04); return its `client_id`.

    `client_name` is sent only when given — the consent page (this task) is what actually
    displays it; DCR itself already tolerates its absence (defaults to "Unnamed client").
    """
    body: dict[str, object] = {"redirect_uris": [_REDIRECT_URI]}
    if client_name is not None:
        body["client_name"] = client_name
    response = client.post(_REGISTER_PATH, json=body)
    assert response.status_code == 201, response.text
    client_id: str = response.json()["client_id"]
    return client_id


def _authorize_params(client_id: str, **overrides: str | None) -> dict[str, str]:
    """A full, valid `/authorize` query dict for `client_id` — RFC 7636 Appendix B's vector,
    `state="xyz"`, `resource=_RESOURCE`. A keyword override set to `None` OMITS that key entirely.
    """
    params: dict[str, str | None] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _REDIRECT_URI,
        "code_challenge": _CODE_CHALLENGE,
        "code_challenge_method": "S256",
        "scope": "mcp",
        "resource": _RESOURCE,
        "state": _STATE,
    }
    params.update(overrides)
    return {key: value for key, value in params.items() if value is not None}


def _redirect_query(location: str) -> dict[str, list[str]]:
    """Parse a redirect `Location`'s query string into `{name: [values]}`."""
    return urllib.parse.parse_qs(urllib.parse.urlparse(location).query)


def _reach_consent(
    client: TestClient, *, client_name: str = "Claude", email: str = "admin@example.com"
) -> tuple[str, str]:
    """Register a client, authorize it, log in, and GET `/authorize/continue` — asserting it
    stops at the consent page. Returns `(html_body, nonce)`.

    Shared by tests that only care about the page's rendered content (escaping, no-`<script>`),
    not about the surrounding request/response plumbing — tests that also need `client_id` or
    header assertions drive the sequence by hand instead, same as `test_oauth_authorize.py`'s own
    per-test style.
    """
    client_id = _register(client, client_name=client_name)
    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text

    login_as(client, email)

    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    html = continue_response.text
    nonce_match = _NONCE_RE.search(html)
    assert nonce_match is not None, html
    return html, nonce_match.group(1)


# ---------------------------------------------------------------------------
# consent_csp: appends the client's redirect_uri origin onto form-action (hotfix-csp brief).
# `app.routes.oauth_consent_html.consent_csp` does not exist yet — imported inside each test
# function (not at module level) so the rest of this file keeps collecting even before the
# hotfix's GREEN step lands (mirrors this file's own established "not yet exported" pattern for
# module-level constants like `_AUTHORIZE_COOKIE_NAME` above).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("redirect_uri", "expected"),
    [
        (
            "https://claude.ai/api/mcp/auth_callback",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://claude.ai",
        ),
        (
            "https://example.com:8443/cb?x=1",
            "default-src 'none'; style-src 'unsafe-inline'; "
            "form-action 'self' https://example.com:8443",
        ),
        (
            "http://127.0.0.1:33418/callback",
            "default-src 'none'; style-src 'unsafe-inline'; "
            "form-action 'self' http://127.0.0.1:33418",
        ),
    ],
)
def test_consent_csp_appends_redirect_origin(redirect_uri: str, expected: str) -> None:
    """`consent_csp(redirect_uri)` appends `" {scheme}://{netloc}"` onto `CONSENT_CSP`'s own
    `form-action 'self'` directive when `redirect_uri` parses to a non-empty scheme AND netloc —
    the hotfix for Chrome/Edge enforcing `form-action` against the redirect that FOLLOWS the
    consent form's POST (the client's own callback origin), not just the form's own same-origin
    POST target (hotfix-csp brief, "Expected values", verbatim)."""
    from app.routes.oauth_consent_html import consent_csp

    assert consent_csp(redirect_uri) == expected


@pytest.mark.parametrize("redirect_uri", ["not a uri", ""])
def test_consent_csp_falls_back_on_unparseable_redirect_uri(redirect_uri: str) -> None:
    """A `redirect_uri` that does not yield both a non-empty scheme AND a non-empty netloc (an
    empty string, or a string with neither) falls back to the bare `CONSENT_CSP` unchanged
    (hotfix-csp brief, "Expected values": `consent_csp("not a uri") == CONSENT_CSP`,
    `consent_csp("") == CONSENT_CSP`)."""
    from app.routes.oauth_consent_html import CONSENT_CSP, consent_csp

    assert consent_csp(redirect_uri) == CONSENT_CSP


def test_consent_csp_falls_back_when_origin_contains_semicolon() -> None:
    """Fix round 1, hotfix-csp review finding I-1 (belt-and-suspenders): `consent_csp` no longer
    trusts `validate_redirect_uri` alone to keep a `;` out of the derived origin — it re-checks
    the origin it just built and falls back to `CONSENT_CSP` unchanged if it contains a `;` or any
    whitespace. `urlsplit("https://evil.com;x/cb").netloc == "evil.com;x"`, so a `redirect_uri`
    that (were it not now also rejected by `validate_redirect_uri`, see
    `tests/test_oauth_register.py::test_register_rejects_semicolon_redirect_uri`) would otherwise
    inject a second, attacker-named CSP directive token onto `form-action`."""
    from app.routes.oauth_consent_html import CONSENT_CSP, consent_csp

    assert consent_csp("https://evil.com;x/cb") == CONSENT_CSP


def test_consent_csp_falls_back_on_urlsplit_value_error() -> None:
    """Fix round 1, hotfix-csp review finding M-1: the implementer report previously claimed the
    `except ValueError` branch was exercised by the two `["not a uri", ""]` fallback cases above —
    it was not (neither raises; both just parse to an empty scheme/netloc and hit the *next* `if`
    instead). Verified empirically in this environment that `urlsplit` DOES raise `ValueError` for
    a bracket-mismatched IPv6-looking authority: `urllib.parse.urlsplit("http://[invalid")` raises
    `ValueError: Invalid IPv6 URL` (the same input shape `validate_redirect_uri`'s own I-1 fix
    round 1 guards against, `tests/test_oauth_register.py::
    test_register_rejects_malformed_bracket_authority`). This test genuinely exercises the
    `except ValueError: return CONSENT_CSP` branch, not just the sibling empty-scheme/netloc one.
    """
    with pytest.raises(ValueError):
        urllib.parse.urlsplit("http://[invalid")

    from app.routes.oauth_consent_html import CONSENT_CSP, consent_csp

    assert consent_csp("http://[invalid") == CONSENT_CSP


# ---------------------------------------------------------------------------
# The consent page itself: renders, escapes, no script tags.
# ---------------------------------------------------------------------------


def test_first_authorization_renders_consent_page(tmp_engine: Engine) -> None:
    """The FIRST authorization for a `(user, client)` pair renders the consent page — 200
    `text/html`, `no-store`/`no-cache`, `_CONSENT_CSP` exactly, and the client name, the signed-in
    admin's email, both decision buttons, the nonce field, and the scope line all present in the
    body (task-06 brief's `render_consent_page` interface block).

    docs/plans/mcp-oauth/task-06-consent-screen.md.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")

    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")

    response = client.get(_CONTINUE_PATH, follow_redirects=False)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("pragma") == "no-cache"
    assert response.headers.get("content-security-policy") == _CONSENT_CSP
    body = response.text
    assert "Claude" in body
    assert "admin@example.com" in body
    assert 'name="decision" value="approve"' in body
    assert 'value="deny"' in body
    assert 'name="nonce"' in body
    assert "mcp — use the AdvisorDesk MCP tools (admin-level access)" in body


def test_consent_page_escapes_client_name(tmp_engine: Engine) -> None:
    """A `client_name` containing HTML is `html.escape()`d in the rendered page — the confused-
    deputy consent screen must never let a hostile DCR registration inject markup/script into an
    admin-facing page (task-06 brief: "html.escape() every interpolated value")."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    html, _nonce = _reach_consent(client, client_name="<b>Evil</b>")

    assert "&lt;b&gt;Evil&lt;/b&gt;" in html
    assert "<b>Evil</b>" not in html


def test_consent_page_has_no_script(tmp_engine: Engine) -> None:
    """The rendered consent page contains no `<script` tag at all (task-06 brief: "No script
    tags, no external assets")."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    html, _nonce = _reach_consent(client)

    assert "<script" not in html


def test_continue_unknown_client_invalid_client(tmp_engine: Engine, db_session: Session) -> None:
    """A pending request whose `client_id` no longer names a registered client (deleted mid-flow,
    between `/authorize` and `/continue` — e.g. via `prune_stale_clients` on a later `/register`
    call) -> 400 `invalid_client`, exact description "Unknown client.", `Cache-Control: no-store`.

    Fix round 1, review finding M-3: pins `oauth_authorize_continue`'s `get_client(session,
    pending.client_id) is None` branch, previously unpinned by any test — the pending cookie
    carries `client_id` by value, so deleting the `OAuthClient` row directly (rather than through
    any route) is what makes `get_client` return `None` while the pending cookie is still valid.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")

    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")

    client_row = db_session.get(OAuthClient, client_id)
    assert client_row is not None
    db_session.delete(client_row)
    db_session.commit()

    response = client.get(_CONTINUE_PATH, follow_redirects=False)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_client"
    assert response.json()["error_description"] == "Unknown client."
    assert response.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# Approve: records consent, issues a real code, clears the pending cookie.
# ---------------------------------------------------------------------------


def test_approve_records_consent_and_issues_code(tmp_engine: Engine, db_session: Session) -> None:
    """Approving the consent form records an `OAuthConsent` row (`revoked_at is None`,
    `scope == "mcp"`) and issues a code exactly like `_issue_code_and_redirect` always has — the
    same DB-row assertions `test_oauth_authorize.py::test_full_bridge_issues_code` makes, so the
    consent hop provably issues the same kind of code, not a different, unbound one.

    docs/plans/mcp-oauth/task-06-consent-screen.md.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")

    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(_REDIRECT_URI)
    query = _redirect_query(location)
    assert "code" in query
    assert query["state"] == [_STATE]

    owner = db_session.execute(select(User).where(User.email == "admin@example.com")).scalar_one()
    consent = db_session.execute(
        select(OAuthConsent).where(
            OAuthConsent.user_id == owner.id, OAuthConsent.client_id == client_id
        )
    ).scalar_one()
    assert consent.revoked_at is None
    assert consent.scope == "mcp"

    code_row = db_session.execute(select(OAuthAuthorizationCode)).scalar_one()
    assert code_row.client_id == client_id
    assert code_row.redirect_uri == _REDIRECT_URI
    assert code_row.code_challenge == _CODE_CHALLENGE
    assert code_row.resource == _RESOURCE
    assert code_row.scope == "mcp"
    assert code_row.consumed_at is None

    assert _AUTHORIZE_COOKIE_NAME not in client.cookies


def test_approve_deleted_client_400_not_500(tmp_engine: Engine, db_session: Session) -> None:
    """Final fix round 1, F-12: if the client is deleted between rendering the consent page and
    the browser POSTing the approve decision back, the approve branch now re-checks the client
    still exists — the same `get_client(...) is None` guard `oauth_authorize_continue` already
    has (pinned above by `test_continue_unknown_client_invalid_client`) — and answers this route's
    documented 400 `invalid_client`, `Cache-Control: no-store`, instead of letting `record_consent`
    raise an uncaught `IntegrityError` (a 500) on the FK insert.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")

    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    deleted = delete_client(db_session, client_id)
    assert deleted is True
    db_session.commit()

    response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "invalid_client"
    assert body["error_description"] == "Unknown client."
    assert response.headers.get("cache-control") == "no-store"


def test_repeat_authorization_skips_consent(tmp_engine: Engine, db_session: Session) -> None:
    """A second authorization for the SAME `(user, client)` pair — after an earlier approve —
    never shows the consent page again: `continue` goes straight to a 302 with a fresh code, and
    no second `OAuthConsent` row is created (the unique `(user_id, client_id)` constraint holds).

    docs/plans/mcp-oauth/task-06-consent-screen.md.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")

    first_authorize = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert first_authorize.status_code == 303, first_authorize.text
    login_as(client, "admin@example.com")
    first_continue = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert first_continue.status_code == 200, first_continue.text
    nonce_match = _NONCE_RE.search(first_continue.text)
    assert nonce_match is not None, first_continue.text
    approve_response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )
    assert approve_response.status_code == 302, approve_response.text

    second_authorize = client.get(
        _AUTHORIZE_PATH,
        params=_authorize_params(client_id, state="second-state"),
        follow_redirects=False,
    )
    assert second_authorize.status_code == 303, second_authorize.text

    second_continue = client.get(_CONTINUE_PATH, follow_redirects=False)

    assert second_continue.status_code == 302, second_continue.text
    query = _redirect_query(second_continue.headers["location"])
    assert "code" in query
    assert query["state"] == ["second-state"]

    consent_rows = (
        db_session.execute(select(OAuthConsent).where(OAuthConsent.client_id == client_id))
        .scalars()
        .all()
    )
    assert len(consent_rows) == 1


def test_revoked_consent_reprompts(tmp_engine: Engine, db_session: Session) -> None:
    """Revoking an existing consent row (`revoked_at` set) makes `continue` show the page again;
    approving again REVIVES the same row (`revoked_at` cleared back to `None`, same row `id`) —
    `record_consent`'s "existing row (any revoked_at) -> set scope, revoked_at=None; else insert"
    contract, not a second, duplicate row.

    docs/plans/mcp-oauth/task-06-consent-screen.md.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")

    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    first_continue = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert first_continue.status_code == 200, first_continue.text
    nonce_match = _NONCE_RE.search(first_continue.text)
    assert nonce_match is not None, first_continue.text
    approve_response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )
    assert approve_response.status_code == 302, approve_response.text

    owner = db_session.execute(select(User).where(User.email == "admin@example.com")).scalar_one()
    consent = db_session.execute(
        select(OAuthConsent).where(
            OAuthConsent.user_id == owner.id, OAuthConsent.client_id == client_id
        )
    ).scalar_one()
    original_id = consent.id
    consent.revoked_at = datetime.now(UTC)
    db_session.commit()

    second_authorize = client.get(
        _AUTHORIZE_PATH,
        params=_authorize_params(client_id, state="second-state"),
        follow_redirects=False,
    )
    assert second_authorize.status_code == 303, second_authorize.text
    second_continue = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert second_continue.status_code == 200, second_continue.text
    nonce2_match = _NONCE_RE.search(second_continue.text)
    assert nonce2_match is not None, second_continue.text

    reapprove_response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce2_match.group(1)},
        follow_redirects=False,
    )

    assert reapprove_response.status_code == 302, reapprove_response.text
    db_session.expire_all()
    revived = db_session.get(OAuthConsent, original_id)
    assert revived is not None
    assert revived.revoked_at is None
    assert revived.id == original_id


# ---------------------------------------------------------------------------
# Deny: access_denied redirect, nothing recorded, the pending request is not resumable after.
# ---------------------------------------------------------------------------


def test_deny_redirects_access_denied(tmp_engine: Engine, db_session: Session) -> None:
    """Denying the consent form redirects `error=access_denied` with `state` preserved, records
    NO `OAuthConsent` row and issues NO code, and clears the pending cookie — same "single-use
    parked request" contract `_issue_code_and_redirect` already has for the approve path.

    t05 review M-7 carry-over: since the pending cookie is cleared on deny, a SECOND
    `GET /authorize/continue` right after is NOT resumable — 400 `invalid_request`, never a
    stale re-render of the (now gone) consent page.

    docs/plans/mcp-oauth/task-06-consent-screen.md.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")

    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    response = client.post(
        _DECISION_PATH,
        data={"decision": "deny", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(_REDIRECT_URI)
    query = _redirect_query(location)
    assert query["error"] == ["access_denied"]
    assert query["state"] == [_STATE]

    assert db_session.execute(select(OAuthConsent)).first() is None
    assert db_session.execute(select(OAuthAuthorizationCode)).first() is None
    assert _AUTHORIZE_COOKIE_NAME not in client.cookies

    second_continue = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert second_continue.status_code == 400, second_continue.text
    assert second_continue.json()["error"] == "invalid_request"


# ---------------------------------------------------------------------------
# The nonce is the cross-site guard: wrong, missing, and a plain missing-cookie/session/bad-value.
# ---------------------------------------------------------------------------


def test_wrong_nonce_400(tmp_engine: Engine, db_session: Session) -> None:
    """A decision POST with a nonce that does NOT match the pending request's own -> 400
    `invalid_request`, exact description "Consent form token mismatch." — the nonce is what stops
    a cross-site POST from a page that never actually saw this pending request's real nonce; no
    code is issued.

    t05 review I-1 carry-over: asserts the EXACT description, so a future change that keeps the
    error code but drops/rewords this message is caught.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")
    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text

    response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": "not-the-real-nonce"},
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"
    assert response.json()["error_description"] == "Consent form token mismatch."
    assert db_session.execute(select(OAuthAuthorizationCode)).first() is None


def test_decision_post_without_nonce_400(tmp_engine: Engine, db_session: Session) -> None:
    """A decision POST with `decision=approve` but NO `nonce` field at all -> 400
    `invalid_request`, no code row, no consent row.

    t05 review I-1 carry-over: the cross-site guard must reject an ABSENT nonce, not just a wrong
    one — a form (or a bare cross-site POST) that never carries `nonce` at all must not slip past
    a naive "only checks the value when present" comparison.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")
    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text

    response = client.post(_DECISION_PATH, data={"decision": "approve"}, follow_redirects=False)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"
    assert db_session.execute(select(OAuthAuthorizationCode)).first() is None
    assert db_session.execute(select(OAuthConsent)).first() is None


def test_non_ascii_nonce_400(tmp_engine: Engine, db_session: Session) -> None:
    """A decision POST whose `nonce` contains a non-ASCII character -> 400 `invalid_request`,
    exact description "Consent form token mismatch." — never a 500.

    Fix round 1, review finding I-1: `hmac.compare_digest` on `str` operands raises `TypeError`
    when either side is non-ASCII (`pending.nonce` is always ASCII — `secrets.token_urlsafe` — but
    the submitted `nonce` comes straight off the form with no charset guard). Before the fix, this
    exact request 500'd instead of answering the documented 400; the route must reject a non-ASCII
    `nonce` the same way it already rejects an absent one, before ever calling `compare_digest`.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")
    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text

    response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": "é" * 8},
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"
    assert response.json()["error_description"] == "Consent form token mismatch."
    assert db_session.execute(select(OAuthAuthorizationCode)).first() is None
    assert db_session.execute(select(OAuthConsent)).first() is None


def test_decision_without_cookie_400(tmp_engine: Engine) -> None:
    """A decision POST with no pending-authorization cookie at all -> 400 `invalid_request` — the
    checked-first branch, before any session/nonce concern even applies."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.post(
        _DECISION_PATH, data={"decision": "approve", "nonce": "whatever"}, follow_redirects=False
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"


def test_decision_without_session_401(tmp_engine: Engine) -> None:
    """A pending request that DID reach the consent page, whose admin session has since vanished
    (logged out elsewhere, cookie expired, ...) -> 401 `auth_required` §9 envelope — the decision
    POST is guarded by `require_admin` (raise-on-failure), NOT `resolve_admin` (which `continue`
    uses to bridge to a 307 login redirect); a lost session here must never turn into a redirect
    loop back through Google login.

    docs/plans/mcp-oauth/task-06-consent-screen.md.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")
    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    client.cookies.delete(COOKIE_NAME)

    response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "auth_required"


def test_decision_deallowlisted_user_access_denied(tmp_engine: Engine, db_session: Session) -> None:
    """An admin whose email has fallen off the allowlist BETWEEN reaching the consent page and
    submitting the decision -> `access_denied`, redirected with `state` preserved; no code, no
    consent row — the decision route's own allowlist re-check (mirrors `oauth_authorize_continue`'s
    identical guard for the "allowlist edited after the session was minted" window).

    Fix round 1, review finding M-2: pins `oauth_authorize_decision`'s allowlist check, previously
    unpinned by any test.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")
    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    client.app.state.settings.admin_emails = "someone-else@example.com"  # type: ignore[attr-defined]

    response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith(_REDIRECT_URI)
    query = _redirect_query(location)
    assert query["error"] == ["access_denied"]
    assert query["state"] == [_STATE]

    assert db_session.execute(select(OAuthAuthorizationCode)).first() is None
    assert db_session.execute(select(OAuthConsent)).first() is None


def test_bad_decision_value_400(tmp_engine: Engine) -> None:
    """A `decision` value that is neither `approve` nor `deny` -> 400 `invalid_request`."""
    app = _build_app(tmp_engine)
    client = TestClient(app)
    client_id = _register(client, client_name="Claude")
    authorize_response = client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    response = client.post(
        _DECISION_PATH,
        data={"decision": "maybe", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_request"


# ---------------------------------------------------------------------------
# Rate limiting, OpenAPI, and the M-4 carry-over (unpinned `&` separator).
# ---------------------------------------------------------------------------


def test_decision_rate_limited(tmp_engine: Engine) -> None:
    """`oauth_rate_limit_per_min=1` on the app under test: a SECOND `/authorize/decision` call
    from the same IP 429s.

    Isolation mirrors `test_oauth_authorize.py::test_authorize_rate_limited`: the register/
    authorize/login/continue setup traffic runs against a SEPARATE app instance (default rate
    limit) sharing the same `tmp_engine`/database, then the resulting session + pending-
    authorization cookies are transplanted onto a client built against the tight-limit app —
    `client.cookies.set(name, value)` is the established injection idiom this suite already uses
    elsewhere (`test_oauth_authorize.py::test_tampered_cookie_is_ignored`); both cookies are
    plain signed strings valid under any app sharing the same `session_secret` (`_build_settings`'s
    own fixed literal), so this works with no DB/session sharing between the two app instances.
    `check_oauth_request` runs before the pending-cookie read (task brief's own route pseudocode),
    so the SECOND decision POST 429s before it would otherwise 400 for its now-cleared cookie.
    """
    setup_app = _build_app(tmp_engine)
    setup_client = TestClient(setup_app)
    client_id = _register(setup_client, client_name="Claude")
    authorize_response = setup_client.get(
        _AUTHORIZE_PATH, params=_authorize_params(client_id), follow_redirects=False
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(setup_client, "admin@example.com")
    continue_response = setup_client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    pending_cookie_value = setup_client.cookies.get(_AUTHORIZE_COOKIE_NAME)
    session_cookie_value = setup_client.cookies.get(COOKIE_NAME)
    assert pending_cookie_value is not None
    assert session_cookie_value is not None

    tight_app = _build_app(tmp_engine, settings=_build_settings(oauth_rate_limit_per_min=1))
    tight_client = TestClient(tight_app)
    tight_client.cookies.set(_AUTHORIZE_COOKIE_NAME, pending_cookie_value)
    tight_client.cookies.set(COOKIE_NAME, session_cookie_value)

    first = tight_client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )
    assert first.status_code == 302, first.text

    second = tight_client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert second.status_code == 429, second.text


def test_openapi_has_decision_operation(tmp_engine: Engine) -> None:
    """`/openapi.json` lists `oauth_authorize_decision` — CONVENTIONS.md §5's "every route has a
    stable unique operation_id", codegen-visible for both frontend apps."""
    app = _build_app(tmp_engine)
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    operation_ids = {
        operation.get("operationId")
        for methods in response.json()["paths"].values()
        for operation in methods.values()
    }
    assert "oauth_authorize_decision" in operation_ids


def test_redirect_uri_with_query_uses_ampersand(tmp_engine: Engine) -> None:
    """A registered `redirect_uri` that already carries its own query string (`?tenant=x`) gets
    its code/error params appended with `&`, never a second `?` — t05 review M-4 carry-over.

    The redirect-shaped ERROR case (an `OAuthRedirectError`, e.g. `code_challenge_method=plain`)
    already passes today: `app.routes.errors._oauth_redirect_error_handler`'s own separator logic
    predates this task. The SUCCESS case (via approve) fails at RED: `continue` issues the code
    immediately with no consent gate today, so there is no `/authorize/decision` to drive through
    yet; once GREEN, the approved code's own redirect must use the identical `&`-aware logic
    (the brief's own `_redirect_with_params` factoring instruction).

    docs/plans/mcp-oauth/task-06-consent-screen.md.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    redirect_uri = "https://claude.ai/api/mcp/auth_callback?tenant=x"
    register_response = client.post(
        _REGISTER_PATH,
        json={"redirect_uris": [redirect_uri], "client_name": "Claude"},
    )
    assert register_response.status_code == 201, register_response.text
    client_id = register_response.json()["client_id"]

    # Redirect-shaped ERROR case: already passes today.
    error_response = client.get(
        _AUTHORIZE_PATH,
        params=_authorize_params(
            client_id, redirect_uri=redirect_uri, code_challenge_method="plain"
        ),
        follow_redirects=False,
    )
    assert error_response.status_code == 302, error_response.text
    error_location = error_response.headers["location"]
    assert error_location.startswith(f"{redirect_uri}&"), error_location
    assert "error=invalid_request" in error_location

    # SUCCESS case (via approve): fails at RED.
    authorize_response = client.get(
        _AUTHORIZE_PATH,
        params=_authorize_params(client_id, redirect_uri=redirect_uri),
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    approve_response = client.post(
        _DECISION_PATH,
        data={"decision": "approve", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert approve_response.status_code == 302, approve_response.text
    success_location = approve_response.headers["location"]
    assert success_location.startswith(f"{redirect_uri}&"), success_location
    assert "code=" in success_location
    assert "state=xyz" in success_location


def test_redirect_uri_with_query_uses_ampersand_on_deny(tmp_engine: Engine) -> None:
    """The DENY redirect also `&`-joins onto a `redirect_uri` that already carries its own query
    string, never a second `?` — the other half of `_redirect_with_params`'s two call sites
    (`test_redirect_uri_with_query_uses_ampersand` above only drives the approve/success half).

    Fix round 1, review finding M-1: `_redirect_with_params` is used at both
    `_issue_code_and_redirect` (success) and `oauth_authorize_decision`'s deny branch — reverting
    just the deny call site to a bare `?` would previously have left the suite green.
    """
    app = _build_app(tmp_engine)
    client = TestClient(app)
    redirect_uri = "https://claude.ai/api/mcp/auth_callback?tenant=x"
    register_response = client.post(
        _REGISTER_PATH,
        json={"redirect_uris": [redirect_uri], "client_name": "Claude"},
    )
    assert register_response.status_code == 201, register_response.text
    client_id = register_response.json()["client_id"]

    authorize_response = client.get(
        _AUTHORIZE_PATH,
        params=_authorize_params(client_id, redirect_uri=redirect_uri),
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text
    login_as(client, "admin@example.com")
    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 200, continue_response.text
    nonce_match = _NONCE_RE.search(continue_response.text)
    assert nonce_match is not None, continue_response.text

    deny_response = client.post(
        _DECISION_PATH,
        data={"decision": "deny", "nonce": nonce_match.group(1)},
        follow_redirects=False,
    )

    assert deny_response.status_code == 302, deny_response.text
    deny_location = deny_response.headers["location"]
    assert deny_location.startswith(f"{redirect_uri}&"), deny_location
    assert "error=access_denied" in deny_location
    assert "state=xyz" in deny_location
