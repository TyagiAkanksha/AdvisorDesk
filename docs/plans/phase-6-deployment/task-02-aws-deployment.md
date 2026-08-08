---
id: task-02
phase: phase-6-deployment
depends_on: [task-01, task-04, task-05]
status: planned
spec: advisordesk-prd.md §9 (deployment, auth security, CORS), §10 Phase 6, §11 row 5
---

# task-02 — AWS deployment

## Goal

The full stack runs on AWS: API image on App Runner (ECS Fargate as the documented alternative),
both frontends as containers, Supabase as the deployed database (§9 default), production env
wired safely (no wildcard CORS, Secure cookies, OAuth redirect URIs, `MCP_HTTP_ENABLED=true`
behind task-04's bearer auth — **owner decision 2026-08-08 supersedes this brief's original
`false` pin**: the MCP endpoint is a deliverable, exposed for Claude connectors at the site's
MCP slug), all three services on the owner's custom domain (below), and the §10 Phase 6
requirement met: rate limiting verified in the deployed environment against DISTINCT client IPs.

**Custom domain (owner D4):** `advisordesk.tyagiakanksha.com` → client,
`admin.advisordesk.tyagiakanksha.com` → admin, `api.advisordesk.tyagiakanksha.com` → API + MCP.
DNS is on Cloudflare; every record App Runner's custom-domain flow asks for (the CNAME/ALIAS
target plus the certificate-validation records) MUST be created **DNS-only (grey cloud — never
the orange proxy)**: Cloudflare's proxy buffers SSE and stacks a redundant TLS hop. The
portfolio at the root/`www` is untouched.

## Context (read ONLY these)

- `advisordesk-prd.md` §9 (Auth security, CORS, Config, Deployment) + §10 Phase 6 + §11 row 5.
- `infra/Dockerfile.api`, `infra/Dockerfile.web`, `infra/docker-compose.yml` (p1-t05) — the
  images to ship unchanged.
- `CONVENTIONS.md` §11.

## Files

- Create: `infra/deploy/{push_ecr.sh,apprunner-api.md,frontends.md,env-checklist.md,VERIFY.md}`
- Modify: `README.md` (deploy section pointer)

*(Notes/scripts, no application code — the §3.1 `infra/deploy/` slot.)*

## Interfaces

- **Consumes:** the three images; the `.env.example` roster; seeded Supabase DB.
- **Produces (later tasks rely on — produce exactly):**
  - `push_ecr.sh` — builds + tags + pushes the three images (`api`, `web:admin`, `web:client`)
    to ECR; idempotent; region/account via env.
  - `apprunner-api.md` — App Runner service creation (image, port 8000, health check
    `/api/v1/healthz`, env var list BY NAME ONLY, instance role for ECR) + the ECS Fargate
    alternative in one paragraph (§11 row 5).
  - `frontends.md` — the two web containers (App Runner too — implementation note),
    `NEXT_PUBLIC_API_URL` build-arg wiring, domains.
  - `env-checklist.md` — every §9 var with its production value-SOURCE, names only for secrets
    (secret VALUES never appear in any committed file — the owner pastes them into the AWS
    console). Concrete non-secret values are pinned here:
    `GOOGLE_REDIRECT_URI=https://api.advisordesk.tyagiakanksha.com/api/v1/auth/callback` (also
    registered in the Google console);
    `CORS_ORIGINS=https://advisordesk.tyagiakanksha.com,https://admin.advisordesk.tyagiakanksha.com`;
    `MCP_HTTP_ENABLED=true`; `FORWARDED_ALLOW_IPS=*` (uvicorn already runs `--proxy-headers` in
    the image; this env var makes it trust App Runner's `X-Forwarded-For`, so the rate limiter
    keys on real client IPs, not the proxy address — safe because the container is reachable
    only through App Runner's ingress); `DATABASE_URL` = the Supabase pooler string (owner
    supplies, project ref `qfsknrtxibdtjyxxeykv`); generated `SESSION_SECRET`; `ADMIN_EMAILS`;
    `NVIDIA_API_KEY`; `ADMIN_APP_URL=https://admin.advisordesk.tyagiakanksha.com`.
    Secure-cookie note (deployed = HTTPS ⇒ `Secure` flag on). MCP bearer tokens are minted with
    task-04's `scripts/mint_mcp_token.py` against the deployed DB — the token value is shown
    once to the owner and never written anywhere.
  - `VERIFY.md` — the deployed checklist phase-7 task-03 re-runs (below).

## Steps (TDD)

*(Ops task — each step's "test" is an observable check recorded in VERIFY.md with real output.)*

- [ ] **Step 1: ECR push** — run `push_ecr.sh`; check: three repos show the new tags.
- [ ] **Step 2: Supabase** — apply migrations (`alembic upgrade head` against the Supabase URL);
  run the seed; check: `/api/v1/public/content` will list seeded articles once the API is up.
- [ ] **Step 3: API on App Runner** — create per `apprunner-api.md`; check: healthz 200 over
  HTTPS; OAuth round-trip works with the production redirect URI; `auth_me` sets/reads the
  Secure HttpOnly cookie.
- [ ] **Step 4: Frontends** — deploy both; check: admin sign-in → dashboard with seeded stats;
  client list/detail/chat all live.
- [ ] **Step 5: Custom domains** — link the three subdomains to their App Runner services
  (App Runner "Custom domains" flow); create every requested record in Cloudflare **DNS-only
  (grey cloud)**; wait for certificate validation; check: all three HTTPS hostnames serve their
  service, and `https://api.advisordesk.tyagiakanksha.com/api/v1/healthz` returns 200.
- [ ] **Step 6: Deployed verification (VERIFY.md, §10 Phase 6):**
  - rate limiting: 11 rapid chat POSTs → 429 with the envelope (**the PRD's explicit deployed
    check**); PLUS the forwarded-IP check: requests from two DISTINCT real client IPs (e.g.
    laptop vs phone hotspot) get independent per-IP buckets — one IP hitting 429 does not 429
    the other (proves `FORWARDED_ALLOW_IPS` works and the limiter is not keying on App
    Runner's proxy address, which would rate-limit ALL visitors as one);
  - SSE streams unbuffered through the custom domain (tokens arrive incrementally — watch with
    `curl -N`);
  - CORS: request from an unlisted origin lacks ACAO; the two real origins pass;
  - MCP exposure (task-04 behavior, deployed): unauthenticated `POST /api/v1/mcp` → 401
    envelope; `POST` with a real minted bearer token and an `initialize` JSON-RPC body → 2xx;
    `GET /api/v1/mcp` → 405 (bearer token value redacted from VERIFY.md — record the command
    shape with `$MCP_TOKEN`);
  - auth hardening (task-05, deployed): after `/auth/logout`, the previous session cookie no
    longer passes `/auth/me` (401);
  - `chat_latency` lines visible in service logs (task-01).
- [ ] **Step 7: Commit** the deploy docs/scripts:
  `chore(infra): aws deployment scripts + verified checklist (phase-6 task-02)`

## Verify

```bash
API=https://api.advisordesk.tyagiakanksha.com
curl -s $API/api/v1/healthz                            # {"status":"ok"}
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done                          # 200s then 429s
curl -N -s -X POST $API/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"What is a Roth IRA conversion?"}' | head   # incremental token events
curl -s -o /dev/null -w "%{http_code}\n" -X POST $API/api/v1/mcp \
  -H 'content-type: application/json'                  # 401 (no credentials)
curl -s -o /dev/null -w "%{http_code}\n" $API/api/v1/mcp     # 405 (GET)
```

## Acceptance

- All three services live on AWS against Supabase, each on its custom subdomain; §10 Phase 6's
  "rate limiting verified in deployed env" is recorded with real output in `VERIFY.md`,
  including the distinct-IP bucket check.
- No wildcard CORS; Secure cookies; MCP HTTP ON and 401-gated (bearer verified live); no secret
  value appears in any committed file.
