# Environment variable checklist (deployed)

Every variable AdvisorDesk reads in production (PRD §9; `apps/api/app/config.py`'s `Settings`
class is the API's single source of truth; `.env.example` is the local-dev mirror of the same
roster), grouped by which deployed service needs it. **No secret VALUE appears in this file or
any other committed file** — secrets are named here, with a description of where their real
value comes from; the real values live in **SSM Parameter Store under `/advisordesk/`**
(written by the owner from their own terminal, read + decrypted by the EC2 instance role and
rendered into the box-local `.env` by `fetch-secrets.sh` — see `ec2-single-host.md`), never in
a file in this repo.

## API — see `ec2-single-host.md`

| Variable | Secret? | Production value / source |
|---|---|---|
| `OPENAI_API_KEY` | **Y** | Your OpenAI API key — platform.openai.com → API keys. Required for `LLM_PROVIDER=openai` (the default) — every embedding and chat call fails without it. |
| `NVIDIA_API_KEY` | N — legacy/optional | Your NVIDIA NIM API key — build.nvidia.com → API Keys. Only needed if `LLM_PROVIDER` is explicitly set to `nvidia` (back-compat/future-re-enable branch); not used in the current deployed configuration. |
| `DATABASE_URL` | **Y** | Supabase pooler connection string — Supabase dashboard → your project (`qfsknrtxibdtjyxxeykv`) → Connect → "Connection string" (pooled/session mode is recommended for a serverless-style container workload). |
| `GOOGLE_CLIENT_ID` | N (not marked secret in code — see note below) | Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 Client ID. |
| `GOOGLE_CLIENT_SECRET` | **Y** | Same Google Cloud Console credential page as `GOOGLE_CLIENT_ID`, "Client secret". |
| `SESSION_SECRET` | **Y** | Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` (README's own quickstart command — reuse it here, run it fresh for production; never reuse the local-dev value). |
| `ADMIN_EMAILS` | N (personal, not a credential) | Comma-separated allowlist — the real Google account email(s) you'll sign into the admin app with. |
| `LLM_PROVIDER` | N | `openai` (`.env.example` default — selects which credential field/`.env.example` block `llm_api_key` resolves to; set to `nvidia` only to fall back to the legacy NVIDIA NIM path). |
| `LLM_BASE_URL` | N | `https://api.openai.com/v1` (`.env.example` default — the NVIDIA equivalent, `https://integrate.api.nvidia.com/v1`, only applies when `LLM_PROVIDER=nvidia`). |
| `EMBEDDING_MODEL` | N | `text-embedding-3-small` (`.env.example` default; was `nvidia/nv-embedqa-e5-v5` before the 2026-09-06 OpenAI switch). |
| `EMBEDDING_DIMENSIONS` | N | `1024` (`.env.example` default — must match the `chunks.embedding` column width, migration `0002`; unchanged by the OpenAI switch since `text-embedding-3-small` is requested at 1024 dims). |
| `EMBEDDING_TIMEOUT_SECONDS` | N | `30.0` (`.env.example` default). |
| `EMBEDDING_MAX_RETRIES` | N | `2` (`.env.example` default). |
| `CHAT_MODEL` | N | `gpt-4o-mini` (`.env.example` default; was `meta/llama-3.1-8b-instruct` before the 2026-09-06 OpenAI switch). |
| `GOOGLE_REDIRECT_URI` | N — **pinned** | `https://api.advisordesk.tyagiakanksha.com/api/v1/auth/callback` — must ALSO be registered as an authorized redirect URI on the same Google OAuth client (Google Cloud Console → Credentials → your client → "Authorized redirect URIs"). |
| `ENVIRONMENT` | N — **pinned** | `production` (see the Secure-cookie note below — this is what turns it on). |
| `ADMIN_APP_URL` | N — **pinned** | `https://admin.advisordesk.tyagiakanksha.com` |
| `CORS_ORIGINS` | N — **pinned** | `https://advisordesk.tyagiakanksha.com,https://admin.advisordesk.tyagiakanksha.com` — no wildcard, ever, in a deployed environment (PRD §9). |
| `SIMILARITY_THRESHOLD` | N | `0.5` (`.env.example` default — PRD §7.3). |
| `RATE_LIMIT_PER_MIN` | N | `10` (`.env.example` default). |
| `RATE_LIMIT_PER_DAY` | N | `50` (`.env.example` default). |
| `SESSION_CREATE_PER_DAY` | N | `20` (`.env.example` default). |
| `MCP_HTTP_ENABLED` | N — **pinned** | `true` — owner decision 2026-08-08 supersedes the task-02 brief's original `false` pin: the MCP endpoint is exposed for Claude connectors at the deployed site, gated by bearer auth (task-04) behind the 401 checks in `VERIFY.md`. |
| `OAUTH_ISSUER_URL` | N — **pinned** | `https://api.advisordesk.tyagiakanksha.com` — set in `docker-compose.yml`'s `api` `environment:` block (mcp-oauth plan). This is the OAuth 2.1 issuer/canonical-resource root (`Settings.mcp_resource_url == f"{OAUTH_ISSUER_URL}/api/v1/mcp"`) that the `/.well-known/*` discovery documents and the MCP `WWW-Authenticate` challenge advertise. The five paired TTL/limit vars (`OAUTH_ACCESS_TOKEN_TTL_MINUTES`, `OAUTH_REFRESH_TOKEN_TTL_DAYS`, `OAUTH_AUTH_CODE_TTL_SECONDS`, `OAUTH_RATE_LIMIT_PER_MIN`, `OAUTH_MAX_CLIENTS`) keep their `.env.example` defaults (60 min / 30 days / 60 s / 30 per min / 200 clients) — not set explicitly in `docker-compose.yml`. |
| `FORWARDED_ALLOW_IPS` | N — **`*` in this topology** | Not an `app/config.py` setting; uvicorn itself reads this env var natively when `--forwarded-allow-ips` isn't on the command line (verified, uvicorn 0.51.0 `Config.__init__`). Purpose: make the rate limiter (`apps/api/app/routes/ratelimit.py`) key on the real client IP from `X-Forwarded-For` instead of the reverse proxy's address. In the deployed single-host topology `*` is safe **because of two properties together** (see `ec2-single-host.md`): the Caddyfile *overwrites* `X-Forwarded-For` with `{remote_host}` (client-supplied chains are discarded, not appended to), and the api container is not host-published (only Caddy can reach it). Verified live by `VERIFY.md` check 2b (forged XFF stays 429). If either property ever changes, re-derive the value — `apprunner-api.md` step 2's escalation ladder explains the appending-ingress hazard that makes blind `*` unsafe elsewhere. |

`GOOGLE_CLIENT_ID` note: `apps/api/app/config.py`'s `Settings` class marks `openai_api_key`,
`nvidia_api_key`, `database_url`, `google_client_secret`, and `session_secret` as `SecretStr` (so a stray
`repr(settings)`/structured log line can never leak them) but leaves `google_client_id` a plain
`str` — OAuth client IDs are routinely embedded in public URLs/HTML in normal web-OAuth flows.
Still treat it as a credential you copy carefully (same console page as the real secret) rather
than something to hand out casually.

`TEST_DATABASE_URL` is dev/test-only (`CONVENTIONS.md` §10) — do not set it on any deployed
service.

## `admin` container — wiring in `frontends.md`, runtime in `ec2-single-host.md`

| Variable | Secret? | Production value / source |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | N — **pinned**, **build-time only** | `https://api.advisordesk.tyagiakanksha.com` — baked into the image by `push_ecr.sh` (its `API_PUBLIC_URL` env var). Do **not** set this as a runtime env var on the deployed container — it has no effect once the image is built; see `frontends.md`'s wiring explanation. |

No other variables — the admin container never receives backend secrets (mirrors
`infra/docker-compose.yml`'s own "only `api` loads `env_file`" rule).

## `client` container — wiring in `frontends.md`, runtime in `ec2-single-host.md`

| Variable | Secret? | Production value / source |
|---|---|---|
| `API_URL` | N — **pinned**, **both build-time AND runtime** | `https://api.advisordesk.tyagiakanksha.com` — baked in by `push_ecr.sh` at build time AND must be set again as a plain runtime environment variable on the deployed container (the production compose file on the EC2 host sets it — see `frontends.md`'s wiring explanation for why one alone isn't enough). |
| `NEXT_PUBLIC_API_URL` | N — **pinned**, **build-time only** | `https://api.advisordesk.tyagiakanksha.com` — baked into the image by `push_ecr.sh` (its `API_PUBLIC_URL` env var), same mechanism as `admin`'s row above. Load-bearing, not unused: `apps/client/src/components/chat/useChatStream.ts` reads it at build time for the browser-side chat POST (`/api/v1/public/chat`) — the client's entire chat feature depends on it. Do **not** set this as a runtime env var on the deployed container — it has no effect once the image is built; changing the API origin requires a client image rebuild, same as `API_URL`'s build-arg half above. |

No other variables — same "no backend secrets in a frontend container" rule as `admin`.

## Secure-cookie note

`apps/api/app/auth/sessions.py`'s `issue_cookie` sets the admin session cookie's `Secure` flag
to `not settings.is_dev`, and `Settings.is_dev` is `True` for anything other than
`ENVIRONMENT=production` (case-insensitive). Setting `ENVIRONMENT=production` above is what
turns `Secure` **on** — without it, the cookie would be sent over plain HTTP too, which is never
correct once the site is on real HTTPS domains. Every deployed hostname here (`api.`, `admin.`,
the client) is HTTPS-only via Caddy's Let's Encrypt certificates (`ec2-single-host.md`), so
this is a hard requirement, not a tuning knob.

## MCP bearer-token note

**OAuth Connect (mcp-oauth) is the primary path** as of this plan: claude.ai's remote-connector
"Connect" button drives the Google-bridged `/api/v1/oauth/*` authorization flow described in
`prod/README.md`'s "MCP OAuth Connect" section — an allowlisted admin signs in and approves a
consent screen, and Claude gets a rotating `adk_`/`adkr_` token pair with no manual minting step.
The CLI mint documented below (`scripts/mint_mcp_token.py`) **remains** as the ops/CI fallback —
for scripting, a non-interactive integration, or any caller that cannot drive an OAuth redirect.

`MCP_HTTP_ENABLED=true` above exposes `/api/v1/mcp` publicly, gated by bearer-token auth
(phase-6 task-04: `app.auth.tokens`, `app.mcp.server._AdminGatedMcpApp`) — a request with no
credentials still 401s (verified in `VERIFY.md`). Actual bearer tokens are **not** an
environment variable and are never generated by any script in `infra/deploy/`: mint one
**after** the API is live, against the deployed database.

**`OAUTH_ISSUER_URL` must be set to the production value (`https://api.advisordesk.tyagiakanksha.com`)
wherever `mint_mcp_token.py --mint` runs** — `mint()` stamps the new row's `resource` from
`Settings.mcp_resource_url` (derived from `OAUTH_ISSUER_URL`), and the MCP endpoint's audience
check (`resolve_bearer_token`) rejects a CLI-minted token whose `resource` is non-`NULL` and does
not equal the canonical resource. The recommended way to mint is **inside the `api` container**,
which already has `OAUTH_ISSUER_URL` from `docker-compose.yml`:

```sh
docker compose exec api uv run python scripts/mint_mcp_token.py --mint --email <admin email> --name "claude-connector"
```

The workstation form below is kept as a fallback for when the container isn't reachable (e.g. no
SSM session handy) — it now needs `OAUTH_ISSUER_URL` added to its env prefix explicitly, or the
minted token's `resource` would default to `http://localhost:8000/api/v1/mcp` and never resolve
against the deployed MCP endpoint:

```sh
cd apps/api && DATABASE_URL=<the same Supabase pooler string set above> \
  OAUTH_ISSUER_URL=https://api.advisordesk.tyagiakanksha.com \
  uv run python scripts/mint_mcp_token.py --mint --email <your admin email> --name "claude-connector"
```

Must run **from `apps/api`**, not the repo root — there is no root `pyproject.toml`, so `uv run`
at the repo root is outside the API's project and cannot resolve the script's `from app.auth...`
imports (verified: running it as `uv run python apps/api/scripts/mint_mcp_token.py` from the
repo root fails with `ModuleNotFoundError: No module named 'app'`). The script's own docstring
pins the working form as `uv run python scripts/mint_mcp_token.py ...`, i.e. already inside
`apps/api`.

The script prints the raw token **exactly once**, with a "shown once, store it now" warning —
copy it straight into wherever the MCP client (e.g. a Claude connector config) needs it, and
never paste it into a file in this repo, a commit, or an issue/PR description.
`--list`/`--revoke <token-id>` manage tokens afterward without ever re-printing a raw value.
