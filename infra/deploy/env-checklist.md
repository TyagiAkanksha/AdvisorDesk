# Environment variable checklist (deployed)

Every variable AdvisorDesk reads in production (PRD §9; `apps/api/app/config.py`'s `Settings`
class is the API's single source of truth; `.env.example` is the local-dev mirror of the same
roster), grouped by which deployed service needs it. **No secret VALUE appears in this file or
any other committed file** — secrets are named here, with a description of where their real
value comes from; you paste the actual value into the AWS console (or wherever each service's
env vars are configured) during deployment, never into a file in this repo.

## API (App Runner) — see `apprunner-api.md`

| Variable | Secret? | Production value / source |
|---|---|---|
| `NVIDIA_API_KEY` | **Y** | Your NVIDIA NIM API key — build.nvidia.com → API Keys. |
| `DATABASE_URL` | **Y** | Supabase pooler connection string — Supabase dashboard → your project (`qfsknrtxibdtjyxxeykv`) → Connect → "Connection string" (pooled/session mode is recommended for a serverless-style container workload). |
| `GOOGLE_CLIENT_ID` | N (not marked secret in code — see note below) | Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 Client ID. |
| `GOOGLE_CLIENT_SECRET` | **Y** | Same Google Cloud Console credential page as `GOOGLE_CLIENT_ID`, "Client secret". |
| `SESSION_SECRET` | **Y** | Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` (README's own quickstart command — reuse it here, run it fresh for production; never reuse the local-dev value). |
| `ADMIN_EMAILS` | N (personal, not a credential) | Comma-separated allowlist — the real Google account email(s) you'll sign into the admin app with. |
| `LLM_BASE_URL` | N | `https://integrate.api.nvidia.com/v1` (`.env.example` default — keep as-is unless swapping providers). |
| `EMBEDDING_MODEL` | N | `nvidia/nv-embedqa-e5-v5` (`.env.example` default). |
| `EMBEDDING_DIMENSIONS` | N | `1024` (`.env.example` default — must match the `chunks.embedding` column width, migration `0002`). |
| `EMBEDDING_TIMEOUT_SECONDS` | N | `30.0` (`.env.example` default). |
| `EMBEDDING_MAX_RETRIES` | N | `2` (`.env.example` default). |
| `CHAT_MODEL` | N | `meta/llama-3.1-8b-instruct` (`.env.example` default). |
| `GOOGLE_REDIRECT_URI` | N — **pinned** | `https://api.advisordesk.tyagiakanksha.com/api/v1/auth/callback` — must ALSO be registered as an authorized redirect URI on the same Google OAuth client (Google Cloud Console → Credentials → your client → "Authorized redirect URIs"). |
| `ENVIRONMENT` | N — **pinned** | `production` (see the Secure-cookie note below — this is what turns it on). |
| `ADMIN_APP_URL` | N — **pinned** | `https://admin.advisordesk.tyagiakanksha.com` |
| `CORS_ORIGINS` | N — **pinned** | `https://advisordesk.tyagiakanksha.com,https://admin.advisordesk.tyagiakanksha.com` — no wildcard, ever, in a deployed environment (PRD §9). |
| `SIMILARITY_THRESHOLD` | N | `0.35` (`.env.example` default — PRD §7.3). |
| `RATE_LIMIT_PER_MIN` | N | `10` (`.env.example` default). |
| `RATE_LIMIT_PER_DAY` | N | `50` (`.env.example` default). |
| `SESSION_CREATE_PER_DAY` | N | `20` (`.env.example` default). |
| `MCP_HTTP_ENABLED` | N — **pinned** | `true` — owner decision 2026-08-08 supersedes the task-02 brief's original `false` pin: the MCP endpoint is exposed for Claude connectors at the deployed site, gated by bearer auth (task-04) behind the 401 checks in `VERIFY.md`. |
| `FORWARDED_ALLOW_IPS` | N — **pinned** | `*` — **not** an `app/config.py` setting; only takes effect through the App Runner service's Start command override documented in `apprunner-api.md` step 2 (uvicorn's own `--forwarded-allow-ips` flag). Safe as `*` specifically because the container is reachable only through App Runner's own ingress, never directly from the public internet — this makes the rate limiter (`apps/api/app/routes/ratelimit.py`) key on the real client IP from `X-Forwarded-For` instead of App Runner's single proxy address (which would otherwise bucket every visitor together). |

`GOOGLE_CLIENT_ID` note: `apps/api/app/config.py`'s `Settings` class marks `nvidia_api_key`,
`database_url`, `google_client_secret`, and `session_secret` as `SecretStr` (so a stray
`repr(settings)`/structured log line can never leak them) but leaves `google_client_id` a plain
`str` — OAuth client IDs are routinely embedded in public URLs/HTML in normal web-OAuth flows.
Still treat it as a credential you copy carefully (same console page as the real secret) rather
than something to hand out casually.

`TEST_DATABASE_URL` is dev/test-only (`CONVENTIONS.md` §10) — do not set it on any deployed
service.

## `admin` (App Runner) — see `frontends.md`

| Variable | Secret? | Production value / source |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | N — **pinned**, **build-time only** | `https://api.advisordesk.tyagiakanksha.com` — baked into the image by `push_ecr.sh` (its `API_PUBLIC_URL` env var). Do **not** set this as a runtime App Runner env var — it has no effect once the image is built; see `frontends.md`'s wiring explanation. |

No other variables — the admin container never receives backend secrets (mirrors
`infra/docker-compose.yml`'s own "only `api` loads `env_file`" rule).

## `client` (App Runner) — see `frontends.md`

| Variable | Secret? | Production value / source |
|---|---|---|
| `API_URL` | N — **pinned**, **both build-time AND runtime** | `https://api.advisordesk.tyagiakanksha.com` — baked in by `push_ecr.sh` at build time AND must be set again as a plain runtime environment variable on the deployed service (see `frontends.md`'s wiring explanation for why one alone isn't enough). |
| `NEXT_PUBLIC_API_URL` | N, build-time, unused | Harmless — `push_ecr.sh` bakes it in for consistency with the admin build; nothing in `apps/client` reads it today. |

No other variables — same "no backend secrets in a frontend container" rule as `admin`.

## Secure-cookie note

`apps/api/app/auth/sessions.py`'s `issue_cookie` sets the admin session cookie's `Secure` flag
to `not settings.is_dev`, and `Settings.is_dev` is `True` for anything other than
`ENVIRONMENT=production` (case-insensitive). Setting `ENVIRONMENT=production` above is what
turns `Secure` **on** — without it, the cookie would be sent over plain HTTP too, which is never
correct once the site is on real HTTPS domains. Every deployed hostname here (`api.`, `admin.`,
the client) is HTTPS-only via App Runner's managed certificate, so this is a hard requirement,
not a tuning knob.

## MCP bearer-token note

`MCP_HTTP_ENABLED=true` above exposes `/api/v1/mcp` publicly, gated by bearer-token auth
(phase-6 task-04: `app.auth.tokens`, `app.mcp.server._AdminGatedMcpApp`) — a request with no
credentials still 401s (verified in `VERIFY.md`). Actual bearer tokens are **not** an
environment variable and are never generated by any script in `infra/deploy/`: mint one
**after** the API is live, against the deployed database, with:

```sh
DATABASE_URL=<the same Supabase pooler string set above> \
  uv run python apps/api/scripts/mint_mcp_token.py --mint --email <your admin email> --name "claude-connector"
```

The script prints the raw token **exactly once**, with a "shown once, store it now" warning —
copy it straight into wherever the MCP client (e.g. a Claude connector config) needs it, and
never paste it into a file in this repo, a commit, or an issue/PR description.
`--list`/`--revoke <token-id>` manage tokens afterward without ever re-printing a raw value.
