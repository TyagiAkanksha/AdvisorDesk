---
id: mcp-oauth-t02
phase: mcp-oauth
depends_on: [mcp-oauth-t01]
status: planned
spec: docs/plans/mcp-oauth/DESIGN.md
review: sonnet
---

# Task 02 — Discovery documents: RFC 9728 protected-resource + RFC 8414 AS metadata

## Goal

Serve the two discovery documents at the domain root, built from `Settings`, and provide the
one helper (`www_authenticate_challenge`) task 03 embeds in every MCP 401. Document the new env
vars in `.env.example`.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"Conformance target", §"End-to-end flow" steps 1–3, §"Endpoints".
- `CONVENTIONS.md` §2 (`app.auth` may import services/models/config only), §5 (routes, `operation_id`), §8 (openapi baseline).
- `apps/api/app/factory.py` (where routers are included; `_API_PREFIX`).
- `apps/api/app/routes/health_routes.py` (smallest router example).
- `apps/api/app/config.py` — task 01's `oauth_issuer_url`, `mcp_resource_url`.
- `apps/api/tests/test_app_factory.py` (DB-less `create_app()` test shape).
- `.env.example` lines 100–120 (the `MCP_HTTP_ENABLED` block — add the OAuth block after it).

## Files

**Create**
- `apps/api/app/auth/oauth_discovery.py`
- `apps/api/app/routes/discovery_routes.py`
- `apps/api/tests/test_oauth_discovery.py` (DB-less)

**Modify**
- `apps/api/app/factory.py` — `app.include_router(discovery_router)` with **no prefix**, placed
  right after `register_error_handlers(app)`; unconditional (not gated on `mcp_http_enabled`).
- `.env.example` — `OAUTH_ISSUER_URL`, `OAUTH_ACCESS_TOKEN_TTL_MINUTES`,
  `OAUTH_REFRESH_TOKEN_TTL_DAYS`, `OAUTH_AUTH_CODE_TTL_SECONDS`, `OAUTH_RATE_LIMIT_PER_MIN`,
  `OAUTH_MAX_CLIENTS` with one-line comments and the dev defaults.
- `apps/api/openapi.json`, `apps/admin/src/types/generated/schema.d.ts`,
  `apps/client/src/types/generated/schema.d.ts` — regenerated (wire gate).

## Interfaces

**Consumes:** `Settings.oauth_issuer_url`, `Settings.mcp_resource_url` (task 01).

**Produces exactly:**

```python
# app/auth/oauth_discovery.py
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server"

def protected_resource_metadata(settings: Settings) -> dict[str, object]:
    # {"resource": settings.mcp_resource_url,
    #  "authorization_servers": [settings.oauth_issuer_url],
    #  "scopes_supported": ["mcp"],
    #  "bearer_methods_supported": ["header"],
    #  "resource_name": "AdvisorDesk MCP"}

def authorization_server_metadata(settings: Settings) -> dict[str, object]:
    # issuer = settings.oauth_issuer_url
    # {"issuer": issuer,
    #  "authorization_endpoint": f"{issuer}/api/v1/oauth/authorize",
    #  "token_endpoint": f"{issuer}/api/v1/oauth/token",
    #  "registration_endpoint": f"{issuer}/api/v1/oauth/register",
    #  "revocation_endpoint": f"{issuer}/api/v1/oauth/revoke",
    #  "response_types_supported": ["code"],
    #  "grant_types_supported": ["authorization_code", "refresh_token"],
    #  "code_challenge_methods_supported": ["S256"],
    #  "token_endpoint_auth_methods_supported": ["none"],
    #  "revocation_endpoint_auth_methods_supported": ["none"],
    #  "scopes_supported": ["mcp"]}

def www_authenticate_challenge(settings: Settings) -> str:
    # f'Bearer resource_metadata="{settings.oauth_issuer_url}{PROTECTED_RESOURCE_PATH}"'
```

```python
# app/routes/discovery_routes.py  — router = APIRouter()
GET  /.well-known/oauth-protected-resource               operation_id="oauth_protected_resource_metadata"
GET  /.well-known/oauth-protected-resource/api/v1/mcp    operation_id="oauth_protected_resource_metadata_mcp_path"
GET  /.well-known/oauth-authorization-server             operation_id="oauth_authorization_server_metadata"
```
All three return `JSONResponse` (`dict[str, object]`), status 200, header `Cache-Control: public, max-age=3600`.
The second path is the RFC 9728 §3.1 path-suffixed form MCP clients probe first for a resource with
a path component; it returns the identical document.

## Steps (TDD)

- [ ] **RED — test-author** writes `tests/test_oauth_discovery.py` using
  `create_app(settings=Settings(session_secret="test-secret", oauth_issuer_url="https://api.example"))`
  (no DB) and `TestClient`:
  - `test_protected_resource_metadata_exact_shape` — GET root path → 200; body equals the dict
    above with `resource == "https://api.example/api/v1/mcp"` and
    `authorization_servers == ["https://api.example"]`.
  - `test_protected_resource_metadata_path_suffixed_form_identical` — the `/api/v1/mcp`-suffixed
    path returns the byte-identical body.
  - `test_authorization_server_metadata_exact_shape` — every key above present with the exact
    values; `issuer == "https://api.example"`; `code_challenge_methods_supported == ["S256"]`.
  - `test_discovery_cache_control_header` — `Cache-Control: public, max-age=3600`.
  - `test_discovery_available_without_mcp_enabled` — default `Settings()` (mcp disabled) still
    serves both docs with `http://localhost:8000` values.
  - `test_www_authenticate_challenge_format` — pure unit:
    `www_authenticate_challenge(settings) == 'Bearer resource_metadata="https://api.example/.well-known/oauth-protected-resource"'`.
  - `test_openapi_contains_discovery_operation_ids` — `/openapi.json` lists the three `operation_id`s.
  - Prove RED: `uv run pytest -q tests/test_oauth_discovery.py` → all fail (404 / ImportError).
- [ ] **GREEN — implementer:** write the helper module + router, include it in `factory.py`
  (no prefix, unconditional), update `.env.example`, regenerate the openapi baseline + both codegens.
- [ ] Run `tests/test_oauth_discovery.py` + `tests/test_app_factory.py` → PASS.
- [ ] Full backend gates; `git diff --stat apps/api/openapi.json apps/*/src/types/generated/schema.d.ts` shows the regenerated files.
- [ ] Commit: `feat(api): RFC 9728/8414 discovery documents at domain root (mcp-oauth t02)`
  including `openapi.json` + both `schema.d.ts`.

## Verify

```bash
cd apps/api && uv run pytest -q tests/test_oauth_discovery.py tests/test_app_factory.py
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json   # after regen: clean
```

## Acceptance

- Both documents are served at the root (not under `/api/v1`) — the plan-level exception is noted
  in the router module docstring with the RFC citation.
- `create_app()` with no args serves them; no DB touched.
- `openapi.json` and both `schema.d.ts` regenerated in the same commit.
