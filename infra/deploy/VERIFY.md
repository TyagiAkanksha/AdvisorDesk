# Deployed verification checklist (phase-6 task-02 Step 6 / PRD §10 Phase 6)

**This is a template.** Every check below is the exact command to run against the live,
deployed stack — run it for real during the deployment session, and paste the actual output
into the matching ```text``` block in place of the `(recorded during deployment)` placeholder.
Nothing in this file has been run yet; no output here is fabricated. Phase-7 task-03 re-runs
this same checklist later, so keep the commands byte-for-byte reusable.

Set these once, then reuse them in every command below:

```sh
API=https://api.advisordesk.tyagiakanksha.com
CLIENT=https://advisordesk.tyagiakanksha.com
ADMIN=https://admin.advisordesk.tyagiakanksha.com
```

## 0. Health check

```sh
curl -s $API/api/v1/healthz
```

Expected: `{"status":"ok"}`

```text
(recorded during deployment)
```

## 1. Rate limiting — the PRD's explicit deployed check (§10 Phase 6)

11+ rapid chat POSTs from one IP must start returning `429` with the standard error envelope
(`{"error":{"code":"rate_limited","message":"..."}}`) once `RATE_LIMIT_PER_MIN` (default 10) is
exceeded:

```sh
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done
```

Expected: the first ~10 responses `200`, the rest `429`.

```text
(recorded during deployment)
```

## 2. Distinct-IP bucket check (proves `FORWARDED_ALLOW_IPS` is actually working)

The check above only proves rate limiting exists — it doesn't prove it's keying on the *real*
client IP rather than App Runner's single proxy address (which would rate-limit every visitor
as one). Run the SAME loop from **two genuinely distinct real client IPs** — e.g. your laptop on
home wifi, then your phone on cellular data (not the same wifi/NAT) — one right after the other:

**Device A** (drive it into its own 429s first):

```sh
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code} " -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done; echo
```

```text
(recorded during deployment — device A, e.g. laptop on home wifi)
```

**Device B**, immediately after, from a genuinely different network path:

```sh
for i in $(seq 1 3); do curl -s -o /dev/null -w "%{http_code} " -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done; echo
```

Expected: device B gets its own fresh run of `200`s — device A hitting `429` must NOT make
device B 429 too. If device B also 429s immediately, `FORWARDED_ALLOW_IPS`/the Start command
override in `apprunner-api.md` isn't taking effect and every visitor is sharing one bucket.

```text
(recorded during deployment — device B, e.g. phone on cellular data)
```

## 3. SSE streams unbuffered through the custom domain

Tokens must arrive incrementally, not all at once at the end (which would indicate Cloudflare or
some other hop buffered the response — the reason the custom-domain DNS records must be
DNS-only/grey-cloud, per `apprunner-api.md` step 4):

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

App Runner ships each service's stdout/stderr to CloudWatch Logs automatically, under
`/aws/apprunner/<service-name>/<service-id>/application`. Find the API service's exact log group
name in the App Runner console (service → "Logs" tab shows it directly), then:

```sh
aws logs tail /aws/apprunner/advisordesk-api/<service-id>/application \
  --since 1h --filter-pattern "chat_latency" --region us-east-1
```

Expected: at least one line matching `chat_latency p50=<ms> p95=<ms> count=<n>` once
`/api/v1/public/chat` has been hit ~100+ times total (the log line's own cadence — see
`apps/api/app/routes/metrics.py`'s docstring; running the rate-limit checks above several times
each, plus the SSE check, contributes toward that count).

**t01 nuance — verify against the ACTUAL deployed log config, don't assume:**
`apps/api/app/main.py`'s `_configure_logging()` calls `logging.basicConfig(level=logging.INFO)`
at import time, but that call is a documented no-op whenever the root logger already has a
handler attached (Python's own `logging.basicConfig` behavior, not passing `force=True`). This
deployment's App Runner Start command (`apprunner-api.md` step 2) only *adds*
`--forwarded-allow-ips`, so it should not introduce a competing log configuration — but if the
Start command is ever changed further (e.g. a future `uvicorn --log-config <file>` addition),
that could pre-configure the root logger with a level/handler that silently swallows this
module's `logger.info(...)` calls, and `_configure_logging()`'s own guard would then leave it
that way rather than fixing it. If this check ever comes back empty despite real chat traffic,
check the actual Start command in use before assuming the metrics code itself regressed.

```text
(recorded during deployment)
```
