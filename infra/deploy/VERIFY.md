# Deployed verification checklist (phase-6 task-02 Step 6 / PRD §10 Phase 6)

**This is a template.** Every check below is the exact command to run against the live,
deployed stack — run it for real during the deployment session, and paste the actual output
into the matching ```text``` block in place of the `(recorded during deployment)` placeholder.
No output here is fabricated: as of 2026-09-11 §5a (mcp-oauth deploy, main @ `8f9cab3`) and §2b
(spoof-resistance, recorded 2026-09-11) carry recorded output; every other block is still unrun.
Phase-7 task-03 re-runs this same checklist later, so keep the commands byte-for-byte reusable.

Set these once, then reuse them in every command below:

```sh
API=https://api.advisordesk.tyagiakanksha.com
CLIENT=https://advisordesk.tyagiakanksha.com
ADMIN=https://admin.advisordesk.tyagiakanksha.com
```

## Before you start: the three §9 caps, and a recommended run order

Sections 1, 2, and 2b below are deliberately designed to trip rate limits — read this first so a
correctly-working deploy doesn't get misread as broken.

- **`RATE_LIMIT_PER_MIN`** — default **10**, a SLIDING **60-second** window, keyed per IP
  (`apps/api/app/routes/ratelimit.py`). Section 1's 12-POST loop is what trips this: the first
  ~10 requests admit, the rest 429. The window is sliding, not fixed — if the 12 requests are
  spread out (e.g. `-o /dev/null` on a slow connection lets a full SSE stream drain before the
  next `curl` starts), the loop can take long enough that early requests fall out of the trailing
  60s and the cap never trips on an otherwise-healthy deploy. Every command below adds
  `--max-time 3` for exactly this reason — it bounds each request so 12 sequential POSTs stay
  comfortably inside one 60-second window.
- **`SESSION_CREATE_PER_DAY`** — default **20**, a fixed UTC-midnight-bucketed window, keyed per
  IP. Every POST below omits `session_id`, so **every admitted request also charges one
  session-create slot** (`apps/api/app/routes/public_routes.py`'s `will_mint` →
  `rate_limiter.reserve_session_create(client_ip)`), regardless of whether it also tripped the
  per-minute cap. Section 1 (~10 admitted) plus device A in section 2 (up to 10 more) can exhaust
  this cap for your laptop's IP for the rest of the UTC day — after that, **every** request from
  that IP 429s with the session-create message, not the per-minute message, for an unrelated
  reason.
- **Run section 3 (SSE) before sections 1, 2, and 2b.** Those three sections intentionally
  exhaust both caps above; running SSE afterward risks a 429 that looks like broken streaming
  rather than a healthy rate limiter. Doing SSE first costs only one admitted request.
- **Escape hatch:** both caps are pure in-memory, per-process state
  (`ratelimit.py`'s own docstring) — restarting the api container (`docker compose restart api`
  on the EC2 host, via SSM — see `ec2-single-host.md`) clears every bucket if you need a clean
  slate to re-run these checks. Otherwise, space re-runs across
  UTC days (session-create budget) or at least 60 seconds apart (per-minute window).

## 0. Health check

```sh
curl -s $API/api/v1/healthz
```

Expected: `{"status":"ok"}`

```text
(recorded during deployment)
```

## 1. Rate limiting — the PRD's explicit deployed check (§10 Phase 6)

**Run section 3 (SSE) first if you haven't already** — see "Before you start" above.

11+ rapid chat POSTs from one IP must start returning `429` with the standard error envelope
(`{"error":{"code":"rate_limited","message":"..."}}`) once `RATE_LIMIT_PER_MIN` (default **10**,
sliding 60s window) is exceeded. `--max-time 3` bounds each request so the loop stays inside one
window — the 429 slot itself is charged at admission, so a fast-failing request still counts
correctly:

```sh
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" --max-time 3 -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done
```

Expected: the first ~10 responses `200`, the rest `429`. **This loop also spends up to ~10 of
your IP's `SESSION_CREATE_PER_DAY` (default 20) budget** — see "Before you start" above.

```text
(recorded during deployment)
```

## 2. Distinct-IP bucket check (proves `FORWARDED_ALLOW_IPS` is actually working)

> **Recorded 2026-09-11 (single-IP form, after `FORWARDED_ALLOW_IPS` went from `*` to
> `172.16.0.0/12` and the api was recreated at `c3fca19`):** the api access log shows the REAL
> client IP for requests arriving through Caddy — `INFO: 208.104.31.154:0 - "GET
> /api/v1/healthz HTTP/1.1" 200 OK` while Caddy's container address was `172.18.0.5` and the
> container env read `FORWARDED_ALLOW_IPS=172.16.0.0/12` (`docker compose exec api`). That is
> exactly the property this section tests (uvicorn trusts Caddy's `X-Forwarded-For`, so the rate
> limiter keys on the visitor, not on Caddy). The two-device loop below remains unrun — it needs a
> second real IP (a phone on cellular) and burns per-day chat budget; run it when convenient.


The check above only proves rate limiting exists — it doesn't prove it's keying on the *real*
client IP rather than the reverse proxy's single address (which would rate-limit every visitor
as one). Run the SAME loop from **two genuinely distinct real client IPs** — e.g. your laptop on
home wifi, then your phone on cellular data (not the same wifi/NAT) — one right after the other:

**Device A** (drive it into its own 429s first — this burns up to ~10 more of device A's
`SESSION_CREATE_PER_DAY` budget, on top of section 1's if device A is the same laptop/IP as
above; see "Before you start"):

```sh
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code} " --max-time 3 -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done; echo
```

```text
(recorded during deployment — device A, e.g. laptop on home wifi)
```

**Device B**, immediately after, from a genuinely different network path:

```sh
for i in $(seq 1 3); do curl -s -o /dev/null -w "%{http_code} " --max-time 3 -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done; echo
```

Expected: device B gets its own fresh run of `200`s — device A hitting `429` must NOT make
device B 429 too. If device B also 429s immediately, the forwarded-IP handling isn't taking
effect (see `ec2-single-host.md`'s forwarded-IP section — Caddy must be overwriting
`X-Forwarded-For` with `{remote_host}`) and every visitor is sharing one bucket. (On
a re-run later the same UTC day, a `429` on device B's very first request can also mean device
B's own IP already exhausted its `SESSION_CREATE_PER_DAY` budget from earlier testing — that's
the session-create message, not the per-minute one; check the response body if you need to tell
the two apart, or just wait for UTC midnight / redeploy to clear it.)

```text
(recorded during deployment — device B, e.g. phone on cellular data)
```

## 2b. Spoof-resistance check (MANDATORY if `FORWARDED_ALLOW_IPS` was set to `*`)

The inverse property of check 2: a caller must NOT be able to escape its bucket by forging
`X-Forwarded-For`. From ONE device, first exhaust the bucket (the 12-POST loop from check 1),
then immediately retry with forged headers. Like the loops above, this also spends a few more of
this IP's `SESSION_CREATE_PER_DAY` budget — see "Before you start":

```sh
for i in $(seq 1 3); do curl -s -o /dev/null -w "%{http_code} " --max-time 3 -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -H "X-Forwarded-For: 198.51.100.$i" \
  -d '{"message":"hi"}'; done; echo
```

Expected: still `429 429 429` — the forged header must be ignored (Caddy overwrites
`X-Forwarded-For` with the real peer address). If any of these return `200`, the forged chain
is being honored: an attacker can mint a fresh rate-limit bucket per request, which defeats
§9's rate limiting entirely. STOP and check the Caddyfile's `header_up X-Forwarded-For
{remote_host}` overwrite (and that the api container isn't reachable except through Caddy — see
`ec2-single-host.md`), then re-run checks 2 and 2b.

```text
(recorded 2026-09-11: PASSED — api logged 208.104.31.154 for a request carrying
X-Forwarded-For: 1.2.3.4)
```

## 3. SSE streams unbuffered through the custom domain

**Run this section before sections 1, 2, and 2b above** if you haven't already — see "Before you
start" at the top of this file. Those sections deliberately exhaust both the per-minute and (over
a session) the daily session-create caps; running this check afterward risks a `429` here that
looks like broken streaming rather than a healthy rate limiter doing its job. This check itself
only spends one admitted request either way.

Tokens must arrive incrementally, not all at once at the end (which would indicate Cloudflare or
some other hop buffered the response — the reason the custom-domain DNS records must be
DNS-only/grey-cloud, per `ec2-single-host.md`'s DNS notes):

```sh
curl -N -s -X POST $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"What is a Roth IRA conversion?"}' | head
```

Expected: `token` SSE events appear one at a time as you watch (not a long pause followed by
everything at once).

```text
(recorded during deployment)
```

## 4. CORS: unlisted origin lacks ACAO, the two real origins pass

```sh
# Unlisted origin — expect NO Access-Control-Allow-Origin header (grep produces no output)
curl -s -D - -o /dev/null $API/api/v1/healthz -H 'Origin: https://evil.example.com' \
  | grep -i 'access-control-allow-origin'
```

```text
(recorded during deployment — expect empty/no match)
```

```sh
# Client origin — expect the header echoing this exact origin
curl -s -D - -o /dev/null $API/api/v1/healthz -H "Origin: $CLIENT" \
  | grep -i 'access-control-allow-origin'
```

```text
(recorded during deployment)
```

```sh
# Admin origin — expect the header echoing this exact origin
curl -s -D - -o /dev/null $API/api/v1/healthz -H "Origin: $ADMIN" \
  | grep -i 'access-control-allow-origin'
```

```text
(recorded during deployment)
```

## 5. MCP exposure (task-04, deployed)

`/api/v1/mcp` requires the streamable-HTTP `Accept` header regardless of auth outcome (see
`apps/api/tests/test_mcp_bearer_auth.py`'s own `_MCP_HEADERS` constant) — include it on every
call below.

**Unauthenticated `POST` → 401 envelope:**

```sh
curl -s -X POST $API/api/v1/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"0.1"}}}'
```

Expected: HTTP 401, body `{"error":{"code":"auth_required","message":"..."}}`.

```text
(recorded during deployment)
```

**Bearer token → `initialize` 2xx.** Mint a token first per `env-checklist.md`'s MCP bearer-token
note; **never paste the raw token into this file** — record only the command shape with
`$MCP_TOKEN` as shown:

```sh
export MCP_TOKEN=<paste the freshly minted token here, in your shell only — never in this file>
curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/api/v1/mcp \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"0.1"}}}'
```

Expected: `2xx`.

```text
(recorded during deployment — status code only, never the token value)
```

**`GET /api/v1/mcp` → 405:**

```sh
curl -s -o /dev/null -w "%{http_code}\n" $API/api/v1/mcp
```

Expected: `405`.

```text
(recorded during deployment)
```

## 5a. MCP OAuth discovery (mcp-oauth)

RFC 9728/8414 discovery documents live at the domain root (`docs/plans/mcp-oauth/DESIGN.md`), not
under `/api/v1` — these three checks prove they're live and truthful on the deployed API.

**RFC 9728 protected-resource metadata:**

```sh
curl -s $API/.well-known/oauth-protected-resource
```

Expected: `200` JSON containing `"resource":"https://api.advisordesk.tyagiakanksha.com/api/v1/mcp"`.

```text
# recorded 2026-09-08, main @ 8f9cab3 (mcp-oauth deploy), from a workstation
{"resource":"https://api.advisordesk.tyagiakanksha.com/api/v1/mcp","authorization_servers":["https://api.advisordesk.tyagiakanksha.com"],"scopes_supported":["mcp"],"bearer_methods_supported":["header"],"resource_name":"AdvisorDesk MCP"}
```

**RFC 8414 authorization-server metadata:**

```sh
curl -s $API/.well-known/oauth-authorization-server
```

Expected: `200` JSON containing `"issuer":"https://api.advisordesk.tyagiakanksha.com"`.

```text
# recorded 2026-09-08, main @ 8f9cab3 (mcp-oauth deploy), from a workstation
{"issuer":"https://api.advisordesk.tyagiakanksha.com","authorization_endpoint":"https://api.advisordesk.tyagiakanksha.com/api/v1/oauth/authorize","token_endpoint":"https://api.advisordesk.tyagiakanksha.com/api/v1/oauth/token","registration_endpoint":"https://api.advisordesk.tyagiakanksha.com/api/v1/oauth/register","revocation_endpoint":"https://api.advisordesk.tyagiakanksha.com/api/v1/oauth/revoke","response_types_supported":["code"],"grant_types_supported":["authorization_code","refresh_token"],"code_challenge_methods_supported":["S256"],"token_endpoint_auth_methods_supported":["none"],"revocation_endpoint_auth_methods_supported":["none"],"scopes_supported":["mcp"]}
```

**Unauthenticated `POST /api/v1/mcp` now also carries the RFC 9728 challenge:**

```sh
curl -i -s -X POST $API/api/v1/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"0.1"}}}'
```

Expected: HTTP 401, body `{"error":{"code":"auth_required","message":"..."}}`, and a
`WWW-Authenticate: Bearer resource_metadata="https://api.advisordesk.tyagiakanksha.com/.well-known/oauth-protected-resource"`
header.

```text
# recorded 2026-09-08, main @ 8f9cab3 (mcp-oauth deploy), from a workstation — status line,
# challenge header and body only (other response headers omitted)
HTTP/2 401
www-authenticate: Bearer resource_metadata="https://api.advisordesk.tyagiakanksha.com/.well-known/oauth-protected-resource"
{"error":{"code":"auth_required","message":"Sign in required."}}
```

Deploy-session note (2026-09-08): the migration step of this release
(`docker compose run --rm api uv run alembic upgrade head`, from the new `8f9cab3` image) walked
`0004 -> 0005 -> 0006 -> 0007` — the prod schema had still been at `0004`, i.e. migrations `0005`
(`api_tokens.session_epoch`) and `0006` (`api_tokens.expires_at`) had never been applied by the
earlier `28a8473`/`1dd8e38` deploys. The live api container now reports `0007 (head)`. Future
deploys: run `docker compose exec -T api uv run alembic current` before AND after the release and
record both here.

## 6. Auth hardening: logout revocation is live (task-05, deployed)

This one needs a real browser login (Google OAuth can't be scripted with curl) — sign in at
`$ADMIN` in a browser, then copy the `advisordesk_session` cookie's value from DevTools →
Application/Storage → Cookies. **Do not paste the cookie value into this file** — hold it in a
shell variable only:

```sh
export SESSION_COOKIE=<paste the copied advisordesk_session cookie value here, in your shell only>

# Before logout — expect 200
curl -s -o /dev/null -w "%{http_code}\n" $API/api/v1/auth/me \
  --cookie "advisordesk_session=$SESSION_COOKIE"
```

```text
(recorded during deployment — expect 200)
```

```sh
# Log out with that same cookie
curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/api/v1/auth/logout \
  --cookie "advisordesk_session=$SESSION_COOKIE"
```

```text
(recorded during deployment)
```

```sh
# Same (now-revoked) cookie, after logout — expect 401
curl -s -o /dev/null -w "%{http_code}\n" $API/api/v1/auth/me \
  --cookie "advisordesk_session=$SESSION_COOKIE"
```

Expected: `401` — `app/services/users.bump_session_epoch` (phase-6 task-05) revokes every
outstanding cookie for that user the instant `/auth/logout` runs, not just the one the browser
that called it clears locally.

```text
(recorded during deployment — expect 401)
```

## 7. `chat_latency` visible in service logs (task-01)

Container stdout/stderr stays on the EC2 host — there is no CloudWatch integration
(`ec2-single-host.md`'s logging section). From an SSM session on the box:

```sh
docker compose -f /opt/advisordesk/docker-compose.yml logs api --since 1h 2>&1 \
  | grep chat_latency
```

Expected: at least one line matching `chat_latency p50=<ms> p95=<ms> count=<n>` once
`/api/v1/public/chat` has been hit ~100+ times total (the log line's own cadence — see
`apps/api/app/routes/metrics.py`'s docstring; running the rate-limit checks above several times
each, plus the SSE check, contributes toward that count).

**t01 nuance — verify against the ACTUAL deployed log config, don't assume:**
`apps/api/app/main.py`'s `_configure_logging()` calls `logging.basicConfig(level=logging.INFO)`
at import time, but that call is a documented no-op whenever the root logger already has a
handler attached (Python's own `logging.basicConfig` behavior, not passing `force=True`). This
deployment uses the image's own `CMD` unmodified (the production compose file on the EC2 host
sets no `command:` override — `ec2-single-host.md`), so nothing introduces a competing log
configuration — but if a command override is ever added later (e.g. a future
`uvicorn --log-config <file>` addition),
that could pre-configure the root logger with a level/handler that silently swallows this
module's `logger.info(...)` calls, and `_configure_logging()`'s own guard would then leave it
that way rather than fixing it. If this check ever comes back empty despite real chat traffic,
check the actual container command in use before assuming the metrics code itself regressed.

```text
(recorded during deployment)
```

## 8. Phase 9 loop on prod (publish wave 1 → replay → weak queries)

The deployed steps for phase 9's evaluated/self-improving loop — publish the 16 wave-1 articles
via MCP, verify the published count, run the traffic replay, and read `report_weak_queries` back
— are an owner-gated checklist kept with the phase plan, not duplicated here:
**see `docs/plans/phase-9-eval-data-loop/rehearsal.md` §4.**

**Model config, since this fix wave (p9 fix-wave A1):** `docker-compose.yml`'s `environment:`
block no longer pins `CHAT_MODEL`/`JUDGE_MODEL`/`EMBEDDING_MODEL` — Compose gives `environment:`
precedence over `env_file:`, so a value hard-coded there would silently override
`/opt/advisordesk/.env` and the code default alike. After this merge, the box's `.env` needs **no**
`CHAT_MODEL` line for the code default (`gpt-5.4-mini`) to take effect — remove one if present so
it cannot shadow the default. `JUDGE_MODEL` is not needed on the box (the judge only runs locally,
never on prod).

**Deploy record 2026-09-13 (`ca4e634`, PR #50):** images `ca4e634` pushed via `push_ecr.sh`; SSM
rollout backed up the box compose (`docker-compose.yml.bak-c3fca19`), bumped the three tags,
deleted the `EMBEDDING_MODEL`/`CHAT_MODEL` pins, ran `alembic upgrade head` from the NEW image
FIRST (`0008 -> 0009`, additive), then `up -d`. Verified: all three containers healthy on
`ca4e634`, `alembic current` = `0009 (head)`, effective settings in the api container
`gpt-5.4-mini gpt-5.4 text-embedding-3-small 1024`, `/api/v1/healthz` 200, all three public
origins 200, 0 error lines in the api log, the box's `.env` has no `CHAT_MODEL` line. Wave 1 is
NOT yet published on prod (28 published items) — that is §8's owner checklist above.
