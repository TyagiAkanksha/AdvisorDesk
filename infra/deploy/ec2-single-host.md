# Single-host EC2 + Caddy — the deployed topology (doc of record)

**This is how AdvisorDesk is actually deployed** (live since 2026-08-09). It supersedes the
App Runner walkthroughs (`apprunner-api.md`, `frontends.md`'s service-creation sections), which
are kept for their still-relevant reasoning but were never executed — see "Why not App Runner"
below. Everything upstream of the runtime is unchanged: the same three ECR images
(`push_ecr.sh`), the same migrated + seeded Supabase database (`database.md`), the same env-var
roster (`env-checklist.md`), the same verification checklist (`VERIFY.md`).

## Why not App Runner

AWS closed App Runner to **new** customers on 2026-04-30 (existing services keep running;
accounts without any prior App Runner service can no longer create one — verified live against
this project's account, which was created 2026-08-08). ECS Express Mode (the App
Runner-equivalent AWS points new customers at) was evaluated and works, but always-on
Fargate + ALB for three services prices at roughly 2–3× a single small instance. Owner decision
2026-08-09: cheapest path — **one EC2 t3.small runs all three containers behind Caddy**,
~$15/month all-in.

## Topology

```
Cloudflare DNS (grey-cloud A records → Elastic IP)
        │
   EC2 t3.small (Amazon Linux 2023, ports 80/443 only, no SSH — SSM only)
        │
      Caddy (auto-HTTPS via Let's Encrypt)
        ├── api.advisordesk.tyagiakanksha.com   → api container   :8000
        ├── admin.advisordesk.tyagiakanksha.com → admin container :3000
        └── advisordesk.tyagiakanksha.com       → client container:3000
        │
   Supabase Postgres (unchanged — same DATABASE_URL as database.md)
```

- **DNS:** three A records (`advisordesk`, `admin.advisordesk`, `api.advisordesk`) point at the
  instance's Elastic IP, all **DNS-only (grey cloud — never Proxied)**: Cloudflare's proxy
  buffers SSE and adds a redundant TLS hop. Re-check each record's proxy icon *after saving* —
  the record form is known to silently reflow to Proxied. The portfolio's own root/`www`
  records stay untouched.
- **TLS:** Caddy obtains and renews Let's Encrypt certificates for all three hostnames
  automatically once DNS resolves; nothing to configure in AWS.
- **AWS resources** (us-east-1): the instance, its Elastic IP, a security group allowing
  inbound 80/443 only, and an IAM instance role/profile granting `AmazonSSMManagedInstanceCore`
  (management — there is no SSH port), `AmazonEC2ContainerRegistryReadOnly` (image pulls), and
  an inline policy reading `/advisordesk/*` SSM parameters (+ `kms:Decrypt` via ssm). Concrete
  resource IDs are recorded in the execution ledger (`.superpowers/sdd/progress.md`), not here.

## Secrets: SSM Parameter Store, never in the repo or chat

The six secret-bearing/owner-specific values live as SSM parameters under `/advisordesk/`:
`DATABASE_URL`, `OPENAI_API_KEY`, `SESSION_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
(all SecureString) and `ADMIN_EMAILS` (String). **Note (2026-09-06): the app switched from NVIDIA
to OpenAI** (`text-embedding-3-small` embeddings + `gpt-4o-mini` chat, `SIMILARITY_THRESHOLD`
retuned 0.35→0.5 — see `env-checklist.md`) — `OPENAI_API_KEY` is the credential
`fetch-secrets.sh` fetches and renders into `.env` today; `NVIDIA_API_KEY` is no longer part of
the live parameter set (it remains available as a legacy/optional SSM parameter only if
`LLM_PROVIDER` is ever set back to `nvidia`). A disaster-recovery rebuild of this instance's SSM
parameters should create `OPENAI_API_KEY`, not `NVIDIA_API_KEY`. The owner writes them from
their own terminal; the instance role reads + decrypts them. On the box,
`/opt/advisordesk/fetch-secrets.sh` renders them into `/opt/advisordesk/.env` (it prints only a
count, never a value). All the **non-secret
pinned values** (`ENVIRONMENT=production`, `CORS_ORIGINS`, `GOOGLE_REDIRECT_URI`,
`ADMIN_APP_URL`, `MCP_HTTP_ENABLED=true`, model/threshold/rate-limit defaults) are exactly
`env-checklist.md`'s roster — that file remains the authority on every variable.

## On the box

Everything lives in `/opt/advisordesk/`: a production `docker-compose.yml` (three services from
the ECR images + `caddy`), the `Caddyfile`, `fetch-secrets.sh`, and the rendered `.env` (api
service only — the frontend containers get no backend secrets, same rule as
`infra/docker-compose.yml`). Deploy/redeploy cycle, via an SSM session:

1. `aws ecr get-login-password | docker login ...` (instance role authorizes the pull).
2. `./fetch-secrets.sh` (only needed when a parameter changed).
3. `docker compose pull && docker compose up -d`.

Prefer the **git-sha image tags** over `latest` when bumping versions — same reasoning as
`push_ecr.sh`: a sha tag can never silently change under a running service.

## Forwarded-IP handling (simpler and stricter than the App Runner plan)

The Caddyfile **overwrites** `X-Forwarded-For` with `{remote_host}` on every proxied request —
a client-supplied XFF chain is discarded wholesale, so the header the API sees is spoof-proof
by construction. Because the api container is not host-published (only Caddy can reach it over
the compose network), `FORWARDED_ALLOW_IPS=*` is safe **in this topology** — the "never
blind-trust `*`" escalation ladder in `apprunner-api.md` existed for an ingress that *appends*
to the client's chain, which is not what Caddy does here. `VERIFY.md` checks 2/2b still apply
verbatim and passed live: distinct real IPs get distinct rate-limit buckets, and forged-XFF
requests after bucket exhaustion stay 429.

## Logs and metrics

There is no CloudWatch integration — container stdout/stderr stays on the box. Via SSM:
`docker logs <api-container>` (or `docker compose logs api`). The `chat_latency p50/p95` summary
line (`apps/api/app/routes/metrics.py`) appears there every 100 public-chat requests; the
per-request access log is uvicorn's. `VERIFY.md` §7's CloudWatch command does not apply — grep
the container logs instead.

## Operational notes

- **Management is SSM-only.** No SSH port is open; use Session Manager (console or
  `aws ssm start-session --target <instance-id>`).
- **Restarting the api container clears all in-memory rate-limit buckets** (`VERIFY.md`'s
  escape hatch) — and also the in-memory latency tracker's counts.
- **Rotating a secret:** update the SSM parameter (owner's terminal), then on the box
  `./fetch-secrets.sh && docker compose up -d api`.
- **Changing the API's public origin** still requires rebuilding + repushing both frontend
  images (`push_ecr.sh`) — the build-time `NEXT_PUBLIC_API_URL` bake documented in
  `frontends.md`'s wiring section (that section remains authoritative; only its App
  Runner service-creation steps are superseded).

## Verification

`VERIFY.md` is unchanged and was exercised against this topology when the stack went live
(2026-08-09): healthz, 17 published articles from Supabase, incremental SSE through Caddy, MCP
401/405 gates, CORS allow/deny, rate-limit 429s, and the spoof-resistance check all passed
externally over HTTPS. The remaining owner-interactive checks (OAuth sign-in, logout
revocation, minted-bearer MCP `initialize`) record into `VERIFY.md`'s blocks as they're run.
