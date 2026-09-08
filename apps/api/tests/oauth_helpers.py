"""Shared OAuth-authorize-flow test seam: drive DCR -> `/authorize` -> Google bridge -> `/authorize
/continue` end to end, the way `auth_helpers.py::login_as` drives plain admin login.

mcp-oauth plan, task 05 (docs/plans/mcp-oauth/task-05-authorize-pkce-google-bridge.md): every
later task in this plan that needs a live authorization code (task 06's consent-approval flow,
task 07's `/token` code-exchange tests, task 08's refresh-token tests, task 10's revocation tests)
starts from the same "an admin has just authorized a registered client" state — this module is
that one shared starting point, kept as a NON-test module (no `test_` prefix, mirroring
`auth_helpers.py`'s own precedent) so pytest never collects it directly and every importer gets
byte-identical setup.

`complete_authorization` is deliberately narrow: it drives the HTTP surface exactly the way a real
MCP client (or a browser mid-flow) would — `POST /oauth/register`, `GET /oauth/authorize` with a
real RFC 7636 PKCE pair, `login_as` for the Google bridge leg, `GET /oauth/authorize/continue` —
and returns only the four values (`code`, `client_id`, `redirect_uri`, `code_verifier`, `state`) a
later `/token` exchange test needs to keep driving the flow forward. It does NOT expose the raw
HTTP responses it drove through, on purpose: every caller of this helper is asserting on the
FLOW'S OUTCOME (a minted code, redeemable against a known client/redirect/verifier), not on the
authorize/continue endpoints' own request/response shape — those are
`tests/test_oauth_authorize.py`'s job alone. task 05's own `test_full_bridge_issues_code` mirrors
this: it authenticates the returned `code`/`state`/DB row through this helper, and separately
confirms the pending-cookie
deletion by reading `client.cookies` post-call (Starlette's `delete_cookie` emits a
Max-Age=0/epoch-`expires` Set-Cookie that `TestClient`'s own cookie jar evicts on receipt — the
same observable effect a real browser gives it) rather than by threading a raw response back out
of this helper.

Task 06 (consent screen) is the ONE task allowed to extend this module — to click "Approve" on the
consent screen `complete_authorization` will need to drive through once it exists (task 05's own
brief: "No consent screen yet ... this task's `continue` goes straight to the code"). Every other
later task imports `complete_authorization`/`AuthorizationResult` unchanged.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from auth_helpers import login_as
from fastapi.testclient import TestClient

_REGISTER_PATH = "/api/v1/oauth/register"
_AUTHORIZE_PATH = "/api/v1/oauth/authorize"
_CONTINUE_PATH = "/api/v1/oauth/authorize/continue"

#: The redirect URI every `complete_authorization` caller's client is registered with — a
#: realistic claude.ai-shaped callback, matching `tests/test_oauth_register.py`'s own examples.
_REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"

#: RFC 7636 Appendix B's worked example: `S256(_CODE_VERIFIER) == _CODE_CHALLENGE`. Reusing the
#: well-known vector (rather than generating a fresh random pair per call) keeps every caller's
#: authorization request byte-reproducible and needs no extra crypto import here.
_CODE_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
_CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

#: The MCP resource indicator every test app in this plan is built with
#: (`oauth_issuer_url="https://api.example"` -> `Settings.mcp_resource_url`, mcp-oauth task 01).
_RESOURCE = "https://api.example/api/v1/mcp"

_STATE = "xyz"


@dataclass(frozen=True)
class AuthorizationResult:
    """The outcome of one `complete_authorization` run: everything a later `/token` exchange (or
    an assertion against the minted `OAuthAuthorizationCode` row) needs.

    Attributes:
        code: the raw authorization code from the `continue` redirect's `code` query param
            (`"adkac_..."`, mcp-oauth task 05's `issue_authorization_code`).
        client_id: the `client_id` `complete_authorization` registered via DCR.
        redirect_uri: the redirect URI the client was registered with, and the one the
            authorization request/code are bound to.
        code_verifier: the RFC 7636 verifier matching the `code_challenge` the authorize request
            carried — a later `/token` exchange test passes this straight through.
        state: the `state` echoed back on the `continue` redirect — equal to the `state` the
            authorize request sent, per RFC 6749 §4.1.2.
    """

    code: str
    client_id: str
    redirect_uri: str
    code_verifier: str
    state: str


def complete_authorization(
    client: TestClient, *, email: str = "admin@example.com"
) -> AuthorizationResult:
    """Register a client, authorize it via the Google bridge, and return the minted code.

    Drives, on `client`, exactly the sequence a real MCP client + admin browser would:

    1. `POST /oauth/register` with `redirect_uris=[_REDIRECT_URI]` -> a fresh `client_id`.
    2. `GET /oauth/authorize` with a full valid RFC 7636 request (the well-known Appendix B
       vector, `state="xyz"`, `resource=_RESOURCE`) -> asserts 303 (the pending-authorization
       cookie lands in `client`'s jar — `TestClient` persists `Set-Cookie` across requests on the
       same client, exactly like `auth_helpers.login_as` relies on for its own state cookie).
    3. `login_as(client, email)` -> the Google bridge leg (registers a fresh fake identity,
       drives `/auth/login` + `/auth/callback`), landing a live admin session cookie alongside
       the still-pending authorization cookie.
    4. `GET /oauth/authorize/continue` -> asserts 302, and parses the redirect `Location`'s
       `code`/`state` query params.

    Args:
        client: a `TestClient` over an app built with a `FakeGoogleOAuthClient` injected as
            `oauth_client` (`login_as`'s own requirement) and with DCR/`/authorize` live
            (`oauth_router` included — every app `create_app()` builds, mcp-oauth task 04+).
        email: the identity to authenticate as; must be in the app's `admin_emails` allowlist,
            same requirement `login_as` itself has.

    Returns:
        An `AuthorizationResult` carrying the minted code plus everything needed to redeem it.

    Raises:
        AssertionError: the register/authorize/continue call sequence did not reach the expected
            303/302 status at each step — surfaces exactly where the flow broke, the same
            fail-fast contract `login_as` itself gives its callers.
    """
    register_response = client.post(_REGISTER_PATH, json={"redirect_uris": [_REDIRECT_URI]})
    assert register_response.status_code == 201, register_response.text
    client_id: str = register_response.json()["client_id"]

    authorize_response = client.get(
        _AUTHORIZE_PATH,
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": _REDIRECT_URI,
            "code_challenge": _CODE_CHALLENGE,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "resource": _RESOURCE,
            "state": _STATE,
        },
        follow_redirects=False,
    )
    assert authorize_response.status_code == 303, authorize_response.text

    login_as(client, email)

    continue_response = client.get(_CONTINUE_PATH, follow_redirects=False)
    assert continue_response.status_code == 302, continue_response.text

    location = continue_response.headers["location"]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)

    return AuthorizationResult(
        code=query["code"][0],
        client_id=client_id,
        redirect_uri=_REDIRECT_URI,
        code_verifier=_CODE_VERIFIER,
        state=query["state"][0],
    )
