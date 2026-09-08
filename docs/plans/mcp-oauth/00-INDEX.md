# MCP OAuth 2.1 Authorization Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Every task runs as a **three-agent SDD task**
> (test-author → implementer → reviewer; reviewer ≠ implementer — `CLAUDE.md`). Tasks marked ★
> get an **Opus** reviewer; the whole-branch final review is Opus.

**Spec:** [`docs/plans/mcp-oauth/DESIGN.md`](DESIGN.md) — authoritative on any conflict with this
plan. Product spec: [`advisordesk-prd.md`](../../../advisordesk-prd.md) (§3 MCP, §9 security).
Conventions: [`CONVENTIONS.md`](../../../CONVENTIONS.md) (apps/api),
[`docs/FRONTEND-CONVENTIONS.md`](../../FRONTEND-CONVENTIONS.md) (apps/admin).

**Goal:** make claude.ai's remote-connector **Connect** button work end-to-end against
`https://api.advisordesk.tyagiakanksha.com/api/v1/mcp` — an allowlisted admin clicks Connect, signs
in with Google, approves a consent screen, and Claude receives a rotating OAuth token — replacing
the manual "mint a CLI token + paste an `Authorization` header" flow.

**Architecture:** the API plays both OAuth roles, co-hosted. The MCP endpoint (resource server)
advertises RFC 9728 metadata and challenges with `WWW-Authenticate`; the authorization server lives
under `/api/v1/oauth/*` (RFC 8414 metadata at the domain root) and implements OAuth 2.1
authorization-code + PKCE S256, RFC 7591 dynamic client registration, RFC 8707 resource binding,
rotating refresh tokens with reuse detection, and RFC 7009 revocation. `/authorize` bridges to the
existing Google login and a server-rendered consent page; access tokens reuse the existing `adk_`
`api_tokens` row so `resolve_bearer_token` keeps enforcing allowlist + epoch + expiry (plus a new
audience check). An admin "Connected apps" page lists and revokes clients.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + itsdangerous (already present);
`python-multipart` (new, form parsing for `/token`, `/revoke`, consent POST); Next.js 16 / MUI 9 /
RTK Query for the admin page. **No new top-level Python package** — import-linter's last contract
enumerates packages by name, so all new code lives inside `app/models`, `app/services`, `app/auth`,
`app/routes`.

## Global Constraints

Every task's requirements implicitly include this section. Exact values are copied from the spec.

- **Canonical resource / audience:** `https://api.advisordesk.tyagiakanksha.com/api/v1/mcp` in prod.
  Derived, never hard-coded: `Settings.mcp_resource_url == f"{Settings.oauth_issuer_url}/api/v1/mcp"`;
  `OAUTH_ISSUER_URL` defaults to `http://localhost:8000` (dev), prod sets
  `https://api.advisordesk.tyagiakanksha.com`. Issuer never has a trailing slash.
- **Lifetimes:** access token **60 min** (`oauth_access_token_ttl_minutes=60`); refresh token
  **30 days** (`oauth_refresh_token_ttl_days=30`), rotated on every use, a rotated token
  **inherits the remaining window** (new `expires_at` = old `expires_at`); authorization code
  **60 s** (`oauth_auth_code_ttl_seconds=60`), **single-use**.
- **PKCE:** `code_challenge_method=S256` is the only accepted method (`plain`/absent → error).
  `code_challenge`/`code_verifier` are 43–128 chars of `[A-Za-z0-9._~-]`.
- **Redirect URIs:** exact string match against the registered client; registration accepts
  only `https://…` or `http://localhost`, `http://127.0.0.1`, `http://[::1]` (any port/path),
  never a fragment. Errors are never redirected to an unverified `redirect_uri`.
- **Scope:** exactly one scope, `mcp`. Absent scope defaults to `mcp`; anything else → `invalid_scope`.
- **Token formats (opaque, sha256-hex at rest, raw value never logged/stored):** access
  `adk_` + `token_urlsafe(32)` (unchanged); refresh `adkr_` + `token_urlsafe(32)`; auth code
  `adkac_` + `token_urlsafe(32)`; client id `adkc_` + `token_urlsafe(24)`.
- **Audience rule** (`resolve_bearer_token`): a token with `client_id IS NOT NULL` (OAuth-issued)
  must have `resource == settings.mcp_resource_url`; a token with `client_id IS NULL` (CLI-minted)
  must have `resource IS NULL OR resource == settings.mcp_resource_url`. Anything else → 401.
- **OAuth error shape** (all `/api/v1/oauth/*` endpoints): JSON `{"error": "<rfc code>",
  "error_description": "<text>"}`, status 400 (401 for `invalid_client`), headers
  `Cache-Control: no-store` + `Pragma: no-cache`. Redirectable authorize errors are a 302 to the
  verified `redirect_uri` with `error`, `error_description`, and `state` (when given) as query params.
- **MCP 401** carries `WWW-Authenticate: Bearer resource_metadata="<issuer>/.well-known/oauth-protected-resource"`
  on all three unauthenticated paths (no/malformed header, unresolved bearer, failed cookie).
  The spec's "insufficient scope → 403" case is unreachable with a single `mcp` scope (a token
  either resolves to an allowlisted admin or it doesn't) — no 403 path is implemented; a
  malformed `Authorization` header stays 401 (existing behaviour, `reason=malformed`).
- **Root-path exception:** `/.well-known/oauth-protected-resource` (+ `/.well-known/oauth-protected-resource/api/v1/mcp`)
  and `/.well-known/oauth-authorization-server` are registered WITHOUT `/api/v1` — RFC 9728/8414
  mandate the root. Everything else stays under `/api/v1`.
- **OAuth routes are always registered** (not gated on `mcp_http_enabled`) so a DB-less
  `create_app()` includes them in `openapi.json` and the admin codegen sees the DTOs.
- **Rate limiting:** `/register`, `/authorize`, `/authorize/continue`, `/authorize/decision`,
  `/token`, `/revoke` call `RateLimiter.check_oauth_request(ip)` — sliding per-IP minute window,
  cap `oauth_rate_limit_per_min=30`. DCR cap `oauth_max_clients=200`; clients older than 24 h with
  no consent/tokens are pruned on every `/register`.
- **Python house rules (CONVENTIONS.md):** `from __future__ import annotations` first line of
  every file; docstrings cite PRD/RFC; services are session-first and `flush()` — never
  `commit()`; typed errors in `app/services/errors.py`, rendered only by
  `app.routes.errors.register_error_handlers`; routes contain no `try/except`; `create_app()`
  must succeed with no DB and no env; every route has a stable unique `operation_id`; Alembic is
  the only DDL path; mypy strict over `app/`.
- **Wire gates (same commit as any route/DTO change):** `uv run python scripts/export_openapi.py`
  regenerates `apps/api/openapi.json`; then `pnpm -C apps/admin codegen` and
  `pnpm -C apps/client codegen` regenerate both `src/types/generated/schema.d.ts`. CI diffs all three.
- **Backend gates before every commit** (run from `apps/api`): `uv run ruff check --no-cache .`,
  `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run pytest -q`
  (needs `TEST_DATABASE_URL` from root `.env`; container `advisordesk-test-db` on :5433).
  Frontend gate: `pnpm gates:admin` (lint, type-check, format:check, test).
- **Tests:** `TestClient` over real HTTP; mock only external seams (`FakeGoogleOAuthClient` from
  `tests/auth_helpers.py`, clocks); DB tests use `tmp_engine`/`db_session` from `tests/conftest.py`;
  **every test-file basename is unique repo-wide** (no `__init__.py` under tests); CI coverage
  `--cov-fail-under=95` on `app/`.
- **SDD discipline:** the test-author writes the RED tests named in each task and proves they
  fail; the implementer may add tests but never weakens/edits authored tests without controller
  approval (task 6 names the one authored test it is allowed to extend).
- **Commits:** Conventional, scoped, path-scoped `git add`, message suffix `(mcp-oauth t<NN>)`,
  e.g. `feat(api): oauth data model + migration 0007 (mcp-oauth t01)`.
- **Branch:** `feat/mcp-oauth`, one PR. Merge, push, deploy, and any handling of decrypted
  production secrets are **owner gates** — never done autonomously.

## Tasks

| # | Task | Depends on | Review | Deliverable |
|---|---|---|---|---|
| 01 | [Data model + migration 0007 + settings](task-01-data-model-migration.md) ★ | — | Opus | 4 new tables, `api_tokens` columns, `token_hashing`, 6 settings, mint stamps `resource` |
| 02 | [Discovery documents (RFC 9728 + 8414)](task-02-discovery-docs.md) | 01 | Sonnet | `app/auth/oauth_discovery.py`, root `.well-known` routes, `.env.example` docs |
| 03 | [MCP `WWW-Authenticate` challenge + audience check](task-03-mcp-challenge-audience.md) ★ | 02 | Opus | header on every MCP 401; `resolve_bearer_token` audience rule + `last_used_at` |
| 04 | [DCR `POST /oauth/register` (RFC 7591)](task-04-dcr-register.md) ★ | 02 | Opus | `OAuthError` family + handler, `check_oauth_request`, client service, route |
| 05 | [`/authorize` + PKCE + Google bridge + code issuance](task-05-authorize-pkce-google-bridge.md) ★ | 04 | Opus | pending-authorization cookie, `resolve_admin`, PKCE helpers, code service, 3 routes |
| 07 | [`/token`: code grant + refresh rotation + reuse detection](task-07-token-refresh-rotation.md) ★ | 05 | Opus | `python-multipart`, `oauth_tokens` service, `/token` route, MCP round-trip proof |
| 06 | [Consent screen + per-client consent record](task-06-consent-screen.md) ★ | 05, 07 | Opus | HTML consent page, `/authorize/decision`, consent gating in `/authorize/continue` |
| 08 | [`/revoke` (RFC 7009) + admin list/revoke API](task-08-revoke-admin-api.md) ★ | 07 | Opus | `revoke_token`, `GET/DELETE /oauth/clients`, DTOs in baseline |
| 09 | [Admin "Connected apps" page](task-09-admin-connected-apps-ui.md) | 08 | Sonnet | RTK slice, screen + VM hook, nav item, vitest coverage |
| 10 | [Wiring, deploy config, narrative e2e, real-connect record](task-10-wiring-e2e.md) ★ | 01–09 | Opus | prod env, Caddy note, README, `test_oauth_e2e_flow.py`, verification record |

**Execution order:** 01 → 02 → 03 → 04 → 05 → **07** → 06 → 08 → 09 → 10 (core-first, per the
spec's phasing: a working Connect exists after 07; 06/08/09 are the "Full polish" the owner chose;
the branch ships only when 10 is green).

### Ordering rationale

- 01 is the foundation every other task imports (models, settings, hashing helper).
- 02 before 03/04: the challenge header and the DCR response both embed discovery URLs.
- 04 before 05: `/authorize` validates against registered clients and needs the `OAuthError`
  family + rate-limit method 04 introduces.
- 07 before 06: with the token endpoint in place the core flow is provable end-to-end (test in 07
  drives authorize → token → MCP `initialize`); 06 then inserts the consent hop and is the one
  task allowed to extend 05's bridge test.
- 08 before 09: the UI codegens against DTOs 08 puts in `openapi.json`.
- 10 last: deploy config + narrative e2e + the owner-gated real claude.ai connect.

## Status

**built (pending owner: merge, deploy, real claude.ai Connect)** — all ten tasks landed on
`feat/mcp-oauth`; the narrative e2e test (`apps/api/tests/test_oauth_e2e_flow.py`) walks the whole
spec flow green, and `docs/plans/mcp-oauth/verification-record.md` records the local gate/alembic
proof. Per-task `status:` fields in each task file are `built`. Merge, deploy, and the real
claude.ai Connect against the deployed API remain owner-gated (never performed autonomously).
