---
id: task-02
phase: phase-6-deployment
depends_on: [task-01]
status: planned
spec: advisordesk-prd.md §9 (deployment, auth security, CORS), §10 Phase 6, §11 row 5
---

# task-02 — AWS deployment

## Goal

The full stack runs on AWS: API image on App Runner (ECS Fargate as the documented alternative),
both frontends as containers, Supabase as the deployed database (§9 default), production env
wired safely (no wildcard CORS, Secure cookies, OAuth redirect URIs, `MCP_HTTP_ENABLED=false`),
and the §10 Phase 6 requirement met: rate limiting verified in the deployed environment.

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
  - `env-checklist.md` — every §9 var with its production value-SOURCE (Supabase URL, Google
    console redirect URI `https://<api-domain>/api/v1/auth/callback`, generated
    `SESSION_SECRET`, exact two-origin `CORS_ORIGINS`, `MCP_HTTP_ENABLED=false`); Secure-cookie
    note (deployed = HTTPS ⇒ `Secure` flag on).
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
- [ ] **Step 5: Deployed verification (VERIFY.md, §10 Phase 6):**
  - rate limiting: 11 rapid chat POSTs → 429 with the envelope (**the PRD's explicit deployed
    check**);
  - SSE streams unbuffered through App Runner (tokens arrive incrementally — watch with
    `curl -N`);
  - CORS: request from an unlisted origin lacks ACAO; the two real origins pass;
  - `MCP_HTTP_ENABLED` off: MCP route 404s;
  - `chat_latency` lines visible in service logs (task-01).
- [ ] **Step 6: Commit** the deploy docs/scripts:
  `chore(infra): aws deployment scripts + verified checklist (phase-6 task-02)`

## Verify

```bash
curl -s https://<api-domain>/api/v1/healthz            # {"status":"ok"}
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://<api-domain>/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done                          # 200s then 429s
curl -N -s -X POST https://<api-domain>/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"What is a Roth IRA conversion?"}' | head   # incremental token events
```

## Acceptance

- All three services live on AWS against Supabase; §10 Phase 6's "rate limiting verified in
  deployed env" is recorded with real output in `VERIFY.md`.
- No wildcard CORS; Secure cookies; MCP HTTP off; no secret value appears in any committed file.
