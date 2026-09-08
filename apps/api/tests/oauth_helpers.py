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

mcp-oauth plan, task 06 (docs/plans/mcp-oauth/task-06-consent-screen.md): `continue` now renders an
HTML consent page instead of issuing a code immediately, the FIRST time a given `(user, client)`
pair authorizes — `complete_authorization` handles both shapes `continue` can now answer with. When
the response is 302 (consent already on file for this `(user, client)` pair — every call after the
first one `complete_authorization` itself drove for the same `email`), behavior is byte-identical
to before this task. When it is 200 `text/html` (the first-ever authorization for this pair), the
helper parses the consent form's `nonce` out of the page (`name="nonce" value="([^"]+)"` — the exact
hidden-input shape `app.routes.oauth_consent_html.render_consent_page` renders), then
`POST /oauth/authorize/decision` with `decision=approve` and that nonce, and reads the resulting
302's `code`/`state` instead — same downstream contract, one extra hop. Every existing caller
(`tests/test_oauth_authorize.py::test_full_bridge_issues_code`, all of `tests/test_oauth_token.py`
+ `tests/test_oauth_token_fk.py`) keeps working unmodified: this module's own signature and return
type (`AuthorizationResult`) are unchanged, and a fresh `client`/`email` pair on a fresh app/DB
always hits the first-authorization (200 HTML) branch, so every existing call site transparently
starts exercising the approve hop instead of skipping it — never a behavior IT can observe as
different, since the four fields on `AuthorizationResult` mean exactly what they always have.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from auth_helpers import login_as
from fastapi.testclient import TestClient

_REGISTER_PATH = "/api/v1/oauth/register"
_AUTHORIZE_PATH = "/api/v1/oauth/authorize"
_CONTINUE_PATH = "/api/v1/oauth/authorize/continue"
_DECISION_PATH = "/api/v1/oauth/authorize/decision"

#: `app.routes.oauth_consent_html.render_consent_page`'s hidden nonce input, e.g.
#: `<input type="hidden" name="nonce" value="AbC123...">` — task-06 brief's own pinned shape.
_NONCE_RE = re.compile(r'name="nonce" value="([^"]+)"')

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

    1. `POST /oauth/register` with `redirect_uris=[_REDIRECT_URI]` and `client_name="Claude"`
       (mcp-oauth plan, task 08: matches DESIGN.md's own end-to-end flow narrative, "Claude ->
       POST /register (DCR)" — `tests/test_oauth_revoke_admin.py::test_admin_list_shape` asserts
       the admin "Connected apps" list surfaces this real registered name) -> a fresh `client_id`.
    2. `GET /oauth/authorize` with a full valid RFC 7636 request (the well-known Appendix B
       vector, `state="xyz"`, `resource=_RESOURCE`) -> asserts 303 (the pending-authorization
       cookie lands in `client`'s jar — `TestClient` persists `Set-Cookie` across requests on the
       same client, exactly like `auth_helpers.login_as` relies on for its own state cookie).
    3. `login_as(client, email)` -> the Google bridge leg (registers a fresh fake identity,
       drives `/auth/login` + `/auth/callback`), landing a live admin session cookie alongside
       the still-pending authorization cookie.
    4. `GET /oauth/authorize/continue` -> either a 302 straight to a code (consent already on
       file for this `(user, client)` pair), or (mcp-oauth task 06: the FIRST authorization for
       this pair) a 200 HTML consent page.
    5. Task 06's consent hop, only when step 4 answered 200: parse the page's `nonce`, then
       `POST /oauth/authorize/decision` with `decision=approve` and that nonce -> asserts 302,
       and reads `code`/`state` from THIS redirect instead of step 4's.

    Args:
        client: a `TestClient` over an app built with a `FakeGoogleOAuthClient` injected as
            `oauth_client` (`login_as`'s own requirement) and with DCR/`/authorize` live
            (`oauth_router` included — every app `create_app()` builds, mcp-oauth task 04+).
        email: the identity to authenticate as; must be in the app's `admin_emails` allowlist,
            same requirement `login_as` itself has.

    Returns:
        An `AuthorizationResult` carrying the minted code plus everything needed to redeem it.

    Raises:
        AssertionError: the register/authorize/(consent-decision)/continue call sequence did not
            reach the expected 303/200/302 status at each step — surfaces exactly where the flow
            broke, the same fail-fast contract `login_as` itself gives its callers.
    """
    register_response = client.post(
        _REGISTER_PATH, json={"redirect_uris": [_REDIRECT_URI], "client_name": "Claude"}
    )
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
    assert continue_response.status_code in (200, 302), continue_response.text

    if continue_response.status_code == 200:
        assert continue_response.headers["content-type"].startswith("text/html"), (
            continue_response.headers["content-type"]
        )
        nonce_match = _NONCE_RE.search(continue_response.text)
        assert nonce_match is not None, continue_response.text
        decision_response = client.post(
            _DECISION_PATH,
            data={"decision": "approve", "nonce": nonce_match.group(1)},
            follow_redirects=False,
        )
        assert decision_response.status_code == 302, decision_response.text
        location = decision_response.headers["location"]
    else:
        location = continue_response.headers["location"]

    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)

    return AuthorizationResult(
        code=query["code"][0],
        client_id=client_id,
        redirect_uri=_REDIRECT_URI,
        code_verifier=_CODE_VERIFIER,
        state=query["state"][0],
    )
