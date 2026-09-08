"""Server-rendered consent page (mcp-oauth plan, task 06;
docs/plans/mcp-oauth/task-06-consent-screen.md; docs/plans/mcp-oauth/DESIGN.md §"Google bridge +
consent" — "server-rendered consent on the API").

Pure rendering only: `render_consent_page` takes plain strings in and returns an HTML string out —
no FastAPI import, no request/response handling, no DB access. `app.routes.oauth_routes` is the
only caller, wrapping the returned string in an `HTMLResponse` with its own headers (`Cache-
Control`/`Pragma`/`Content-Security-Policy`). Keeping this module import-linter-clean of
`app.services`/`app.auth` (stdlib `html` only) is what lets it stay a leaf: nothing here can ever
import something that imports back to routes.

This page is the confused-deputy guard's user-facing half: a hostile DCR registration controls
`client_name` (RFC 7591 `/oauth/register` is open, unauthenticated — mcp-oauth task 04), so EVERY
interpolated value is `html.escape(..., quote=True)`d before landing in the markup, and the page
carries no `<script>` tag and loads no external asset — `CONSENT_CSP` below is a second,
belt-and-suspenders layer against exactly that, not the only one.
"""

from __future__ import annotations

import html

CONSENT_CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"
"""Locks the rendered page down to inline styles and same-origin form submission only — no
script, no image, no fetch, no external stylesheet/font can load even if an escaping bug ever let
markup slip through. Task-06 brief's own pinned literal."""

_SCOPE_LINE = "mcp — use the AdvisorDesk MCP tools (admin-level access)"
"""The one scope this authorization server ever grants (`PendingAuthorization.scope` is always
`"mcp"`, mcp-oauth task 05) — a fixed, non-interpolated string, so it needs no escaping."""


def render_consent_page(*, client_name: str, user_email: str, action_path: str, nonce: str) -> str:
    """Render the Approve/Deny consent page for one pending authorization request.

    Every interpolated value is `html.escape(..., quote=True)`d — `client_name` comes from an
    open, unauthenticated DCR registration (mcp-oauth task 04) and must never be trusted as safe
    markup; `user_email`/`action_path`/`nonce` are escaped for the same defense-in-depth reason,
    even though today's callers only ever pass already-trusted values for those three.

    Args:
        client_name: the registered `OAuthClient.client_name` requesting access.
        user_email: the signed-in admin's email (`AdminPrincipal.email`).
        action_path: the relative path the form POSTs its decision to
            (`/api/v1/oauth/authorize/decision` — the caller's own route path, not this module's
            concern to know as a constant).
        nonce: the pending request's own `PendingAuthorization.nonce` — round-tripped as a hidden
            form field so `POST /authorize/decision` can bind the decision back to this exact
            pending request (a CSRF-style guard, `hmac.compare_digest`-checked by the route).

    Returns:
        A complete, self-contained HTML document: inline `<style>` only, no `<script>` tag, no
        external asset reference of any kind.
    """
    escaped_client_name = html.escape(client_name, quote=True)
    escaped_user_email = html.escape(user_email, quote=True)
    escaped_action_path = html.escape(action_path, quote=True)
    escaped_nonce = html.escape(nonce, quote=True)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Authorize AdvisorDesk MCP access</title>
<style>
  body {{ font-family: sans-serif; max-width: 32rem; margin: 3rem auto; color: #1a1a1a; }}
  .scope {{ background: #f2f2f2; border-radius: 0.5rem; padding: 0.75rem 1rem; margin: 1.5rem 0; }}
  .actions {{ display: flex; gap: 0.75rem; margin-top: 1.5rem; }}
  button {{ font-size: 1rem; padding: 0.5rem 1.25rem; border-radius: 0.375rem;
    border: 1px solid #ccc; cursor: pointer; }}
  button[value="approve"] {{ background: #1a1a1a; color: #fff; border-color: #1a1a1a; }}
</style>
</head>
<body>
  <h1>{escaped_client_name} wants MCP access to AdvisorDesk</h1>
  <p>Signed in as {escaped_user_email}</p>
  <div class="scope">
    <p>This will allow {escaped_client_name} to:</p>
    <ul>
      <li>{_SCOPE_LINE}</li>
    </ul>
  </div>
  <form method="post" action="{escaped_action_path}">
    <input type="hidden" name="nonce" value="{escaped_nonce}">
    <div class="actions">
      <button type="submit" name="decision" value="approve">Approve</button>
      <button type="submit" name="decision" value="deny">Deny</button>
    </div>
  </form>
</body>
</html>
"""
