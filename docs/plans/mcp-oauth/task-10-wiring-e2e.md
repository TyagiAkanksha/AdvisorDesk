---
id: mcp-oauth-t10
phase: mcp-oauth
depends_on: [mcp-oauth-t01, mcp-oauth-t02, mcp-oauth-t03, mcp-oauth-t04, mcp-oauth-t05, mcp-oauth-t06, mcp-oauth-t07, mcp-oauth-t08, mcp-oauth-t09]
status: built
spec: docs/plans/mcp-oauth/DESIGN.md
review: opus
---

# Task 10 — Wiring, deploy config, narrative e2e test, real-connect verification record ★

## Goal

Make the branch shippable: the prod compose sets `OAUTH_ISSUER_URL`, the deploy docs describe the
new Connect flow (and keep the CLI mint as the fallback), one narrative test walks the entire
spec flow end-to-end in-process, and a verification record captures what was proven locally vs.
what remains owner-gated (the real claude.ai Connect against the deployed API).

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` — whole document (this task verifies coverage).
- `docs/plans/mcp-oauth/00-INDEX.md` — Global Constraints (all), Status section.
- `infra/deploy/prod/docker-compose.yml` lines 14–24 (api `environment:` block).
- `infra/deploy/prod/Caddyfile` (api host block — you add a comment only).
- `infra/deploy/prod/README.md` (doc-of-record shape), `infra/deploy/env-checklist.md`
  (`MCP_HTTP_ENABLED` row + "MCP bearer-token note"), `infra/deploy/VERIFY.md` §5 (MCP exposure).
- `apps/api/tests/oauth_helpers.py`, `apps/api/tests/test_oauth_token.py` (helpers to copy),
  `apps/api/tests/test_mcp_bearer_auth.py` (`_MCP_HEADERS`, `initialize` body; a `tools/list`
  body follows the same JSON-RPC shape with `"method": "tools/list"`).
- `docs/plans/phase-7-evaluation/verification-record.md` (record format to mirror).
- `docs/plans/README.md` (phase table — the `mcp-oauth` row's status flips here).

## Files

**Create**
- `apps/api/tests/test_oauth_e2e_flow.py` (DB).
- `docs/plans/mcp-oauth/verification-record.md`.

**Modify**
- `infra/deploy/prod/docker-compose.yml` — api `environment:` add
  `OAUTH_ISSUER_URL: https://api.advisordesk.tyagiakanksha.com` directly under `MCP_HTTP_ENABLED`.
- `infra/deploy/prod/Caddyfile` — comment in the api host block (above `reverse_proxy`):
  `# MCP OAuth (docs/plans/mcp-oauth): the RFC 9728/8414 discovery documents live at the domain`
  `# root (/.well-known/oauth-protected-resource, /.well-known/oauth-authorization-server) and`
  `# are served by the API itself — this block already proxies every path, so nothing to add.`
- `infra/deploy/env-checklist.md` — add an `OAUTH_ISSUER_URL` row (`Y` — set in compose,
  `https://api.advisordesk.tyagiakanksha.com`; the five TTL/limit vars keep their defaults) and
  rewrite the "MCP bearer-token note" heading's first paragraph: OAuth Connect is the primary
  path; the CLI mint remains the ops/CI fallback (keep the existing mint instructions).
- `infra/deploy/VERIFY.md` — new §5a "MCP OAuth discovery (mcp-oauth)" between §5 and §6 with
  three curl checks: `GET $API/.well-known/oauth-protected-resource` → 200 JSON with
  `"resource":"https://api.advisordesk.tyagiakanksha.com/api/v1/mcp"`;
  `GET $API/.well-known/oauth-authorization-server` → 200 with `"issuer":"https://api.advisordesk.tyagiakanksha.com"`;
  the existing unauthenticated `POST /api/v1/mcp` now also expects header
  `WWW-Authenticate: Bearer resource_metadata="https://api.advisordesk.tyagiakanksha.com/.well-known/oauth-protected-resource"`
  (add `-i` to that curl and the expectation line). Each with a `(recorded during deployment)` block.
- `infra/deploy/prod/README.md` — append a section "MCP OAuth Connect (mcp-oauth)" describing:
  (1) claude.ai → Settings → Connectors → Add custom connector → URL
  `https://api.advisordesk.tyagiakanksha.com/api/v1/mcp` → Connect → Google sign-in (allowlisted
  admin) → Approve; (2) Admin app → **Connected apps** to inspect/revoke; (3) CLI mint fallback
  pointer to `env-checklist.md`; (4) the migration step `alembic upgrade head` is part of the
  api container start (verify by reading `infra/deploy/prod/README.md` "Change procedure" —
  if migrations are NOT automatic there, add the explicit `docker compose exec api uv run alembic upgrade head` line to the change procedure).
- `docs/plans/mcp-oauth/00-INDEX.md` — Status → `built (pending owner: merge, deploy, real claude.ai Connect)`;
  every `task-NN-*.md` frontmatter `status: built` (tasks 01–09 flip as they land; this task
  flips its own and verifies the rest).
- `docs/plans/README.md` — `mcp-oauth` row status.

## Interfaces

**Consumes:** everything from t01–t09 through HTTP only (the e2e test imports no `app.*` module
except `Settings`, `create_app`, the models for assertions, and `hash_token`).

**Produces:** no new runtime interfaces. Documentation + one test + one record.

## Steps (TDD)

- [ ] **RED — test-author** writes `tests/test_oauth_e2e_flow.py` — ONE narrative test
  `test_full_connect_lifecycle` (plus the small helpers it needs, copied not imported from other
  test modules; `complete_authorization` from `oauth_helpers` IS importable), with a numbered
  comment per step mirroring DESIGN.md §"End-to-end flow":
  1. `POST /api/v1/mcp` no auth → 401 + exact `WWW-Authenticate`.
  2. `GET /.well-known/oauth-protected-resource` → `authorization_servers == ["https://api.example"]`.
  3. `GET /.well-known/oauth-authorization-server` → read `registration_endpoint`,
     `authorization_endpoint`, `token_endpoint`, `revocation_endpoint` from the body and
     **use those URLs** (path part) for the rest of the test — proving the metadata is truthful.
  4. Register via `registration_endpoint` → `client_id`.
  5. Authorize → 303 → continue without session → 307 login → `login_as` → continue → 200 HTML
     consent → POST approve → 302 with `code` + `state`.
  6. Token exchange via `token_endpoint` → access + refresh.
  7. `POST /api/v1/mcp` `tools/list` with the access token → 200 and **9 tools** named
     `search_content, count_content, create_draft, edit_content, delete_content, tag_content, publish, archive, report_content_gaps`
     (parse the JSON or SSE body the way `test_mcp_bearer_auth` parses `initialize`).
  8. Refresh → new pair; old access → 401; new access → `tools/list` 200.
  9. Second authorize for the same client → continue → 302 directly (consent remembered).
  10. Admin `GET /api/v1/oauth/clients` (cookie) → one item, `active_access_tokens == 1`,
      `active_refresh_tokens == 1`, `last_used_at` not None.
  11. Admin `DELETE /api/v1/oauth/clients/{client_id}` → 204; access token → 401 with
      `WWW-Authenticate`; refresh at `token_endpoint` → 401 `invalid_client`.
  12. `POST /api/v1/mcp` with the CLI-style token (insert an `ApiToken(client_id=None, resource=None)`
      for the admin) → still 200 (fallback path intact).
  - Also `test_openapi_lists_every_oauth_operation` — the set
    `{oauth_protected_resource_metadata, oauth_protected_resource_metadata_mcp_path, oauth_authorization_server_metadata, oauth_register, oauth_authorize, oauth_authorize_continue, oauth_authorize_decision, oauth_token, oauth_revoke, oauth_clients_list, oauth_client_revoke}`
    ⊆ operation ids in `/openapi.json`; and `test_create_app_without_db_registers_oauth_routes`
    (`create_app()` no args → the same ids present).
  - Prove RED only if any step fails against the t01–t09 branch (expected: GREEN immediately —
    record that fact; a narrative test that passes on first run is the acceptance proof, not a
    defect. If it fails, the failure is a bug in an earlier task: ledger it, fix under a scoped
    fix round on that task, do not paper over it here).
- [ ] **Implementer:** the config/doc edits listed under Files; status flips; run the whole
  backend suite + `pnpm gates` (all three apps) from the root.
- [ ] **Verification record** `docs/plans/mcp-oauth/verification-record.md` with: gate output
  summary (ruff/format/mypy/lint-imports/pytest counts + coverage %; admin + client gates);
  the e2e test's 12 steps ticked; `alembic upgrade head` + `downgrade 0006` + `upgrade head`
  round-trip on the test DB (command + result); an "Owner-gated / deferred" section listing
  **merge**, **push**, **deploy** (compose + `.env`), and the **real claude.ai Connect** with the
  exact checklist the owner runs (VERIFY.md §5a curls, then Connect → consent → a `search_content`
  call from claude.ai → Connected apps shows the client → Revoke → claude.ai shows disconnected).
- [ ] Commit: `chore(infra,docs): oauth issuer env, deploy docs, e2e flow test, verification record (mcp-oauth t10)`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_oauth_e2e_flow.py && uv run pytest -q --cov=app --cov-fail-under=95
cd ../.. && pnpm gates
grep -n "OAUTH_ISSUER_URL" infra/deploy/prod/docker-compose.yml infra/deploy/env-checklist.md
```

## Acceptance

- The narrative test walks all 12 steps green on the final branch; discovery URLs are consumed,
  not assumed.
- Prod compose carries `OAUTH_ISSUER_URL`; docs describe Connect + Connected apps + CLI fallback;
  VERIFY.md has the three new checks.
- Coverage ≥ 95 % on `app/`; all three app gate sets green.
- Verification record is honest: local proofs listed with output, owner gates listed as not done.
- Reviewer (Opus) performs the **whole-branch final review** in the same dispatch: DESIGN.md
  conformance line-by-line (every MUST in §"Conformance target" and §"Security / threat model"
  mapped to a test), CONVENTIONS compliance, coupling (`lint-imports`), and the Minor-findings
  triage from the ledger.
