# API on AWS App Runner

Deployment guide for the `advisordesk/api` image (phase-6 task-02). This is a walkthrough for
the **owner to run interactively** in the AWS console (or the equivalent `aws apprunner` CLI
calls) — nothing in this repo runs it for you. Push the image first:

```sh
AWS_ACCOUNT_ID=<your account id> ./infra/deploy/push_ecr.sh
```

**Before creating the service: apply migrations and seed the database — see
`infra/deploy/database.md`.** Do that first, against the same Supabase pooler string you'll
paste into step 3 below. The health check in step 2 has no database dependency at all, so the
service will come up "healthy" against an un-migrated, unseeded database and only then fail on
every real content/chat/auth request — `database.md` explains why and gives the exact commands.

Then follow the steps below. See `infra/deploy/env-checklist.md` for the full env var roster
(names, which are secrets, and where each value comes from) — this doc only repeats the
non-secret values the task-02 brief pins verbatim.

## 1. Create the service

AWS Console → App Runner → **Create service**.

- **Source**: "Container registry" → "Amazon ECR" → browse to
  `advisordesk/api` → pick the tag you just pushed (prefer the **git-sha tag**, e.g. `a1b2c3d`,
  over `latest` — a sha tag can never silently change under a running service; see
  `push_ecr.sh`'s own comment on why it pushes both).
- **Deployment trigger**: **Manual** — `push_ecr.sh` isn't wired to any CI/CD trigger yet, so
  "Automatic" would just sit there watching a repo nothing pushes to automatically.
- **ECR access role** (the role App Runner itself uses to *pull* the private image — this is
  the "instance role for ECR pull" the task brief refers to; note it is a *different* role from
  the "instance role" described in step 4 below, which is about what the *running container*
  can do, not what App Runner needs to fetch it): choose **"Create new service role"** unless
  you already have an `AppRunnerECRAccessRole`-style role from a previous service. The console
  creates one scoped to pulling from ECR and trusting `build.apprunner.amazonaws.com` — accept
  the default.

## 2. Configure the service — build & runtime settings

Since you're deploying a pre-built image (not building from source in App Runner), most of this
section is "Image configuration":

- **Port**: `8000` — matches `infra/Dockerfile.api`'s `EXPOSE 8000` and its `CMD`'s
  `uvicorn ... --port 8000`.
- **Start command**: leave EMPTY — the image's own `CMD` is correct as shipped. No override is
  needed for forwarded-IP handling: when `--forwarded-allow-ips` is not passed on the command
  line (and the image's `CMD` does not pass it), uvicorn's `Config.__init__` reads the
  `FORWARDED_ALLOW_IPS` **environment variable** natively, falling back to `127.0.0.1`
  (verified against the pinned uvicorn 0.51.0:
  `os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")`). Setting the env var in step 3 is
  sufficient; the image keeps its `DATABASE_URL_SHELL_OVERRIDE` shim (harmless here — the
  variable is simply unset in App Runner).

  **What value to give `FORWARDED_ALLOW_IPS` — decided empirically at deploy time, not here.**
  `infra/Dockerfile.api`'s `CMD` comment records a real earlier finding: trusting `"*"` lets a
  caller forge `X-Forwarded-For` and mint a fresh rate-limit bucket per request **if the proxy
  in front APPENDS to a client-supplied chain** (uvicorn walks the chain right-to-left and,
  when every hop is trusted, returns the leftmost — i.e. attacker-controlled — entry). Whether
  that bites depends on how App Runner's ingress connects to the container and how it treats
  inbound `X-Forwarded-For`, which we verify live rather than assume:

  1. **First deploy with `FORWARDED_ALLOW_IPS` unset** (uvicorn trusts only `127.0.0.1`). If
     App Runner's request path reaches the app from localhost, the rate limiter already sees
     real client IPs — run `VERIFY.md`'s distinct-IP check.
  2. If distinct real IPs share one bucket, the ingress connects from a non-local address: set
     `FORWARDED_ALLOW_IPS` to that observed peer address/range. **Find it from uvicorn's own
     access log, not the app's structured log line** — `apps/api/app/routes/metrics.py`'s
     `LatencyMiddleware` logs exactly `route=... status=... duration_ms=...` per request
     (`metrics.py:310-312`), with no client-address field at all. Uvicorn's access log is on by
     default under the image's unmodified `CMD` and prints the raw peer for every request, in
     the form `<client_addr> - "<request_line>" <status_code>`, e.g.:
     ```
     10.0.4.213:54321 - "POST /api/v1/public/chat HTTP/1.1" 200
     ```
     It lands in the same CloudWatch application log group as the structured lines above — App
     Runner service → **Logs** tab, or `aws logs tail /aws/apprunner/<service>/<id>/application
     --since 15m --region us-east-1`. The numeric address before the first ` - ` is the peer
     uvicorn saw; that's what to set `FORWARDED_ALLOW_IPS` to. Re-run the distinct-IP check once
     it's set.
  3. Only if no stable peer range exists fall back to `*` — and then `VERIFY.md`'s
     **spoof-resistance check is mandatory**: a forged `X-Forwarded-For` must NOT move the
     caller into a fresh bucket. If it does, `*` is unacceptable; pin the observed range
     instead.

- **CPU / memory**: the smallest size (1 vCPU / 2 GB) is plenty for a portfolio-scale
  deployment; increase later from the console with zero code changes if needed.
- **Auto scaling**: App Runner's *default* auto-scaling configuration is min **1** / max **25**
  — it guarantees a floor, not a ceiling, so "leave the default" silently permits up to 25
  concurrent instances. **Create (or select) a custom auto-scaling configuration and pin Max
  size = 1 (min 1 / max 1)** before creating the service — do not accept the default here. Why:
  PRD §9's rate limiter (`apps/api/app/routes/ratelimit.py`'s own docstring) and the
  `chat_latency` `LatencyTracker` (`apps/api/app/routes/metrics.py`) are both pure in-memory,
  per-process state — more than one instance splits each cap's/tracker's state per-instance,
  silently multiplying every §9 limit, and can turn `VERIFY.md` check 2 (the distinct-IP bucket
  check) into a **false pass**: if device A and device B land on different instances, device B
  gets a fresh bucket regardless of whether `FORWARDED_ALLOW_IPS` is even working.
- **Health check**: Protocol HTTP, **Path `/api/v1/healthz`** (PRD §9 / the task-02 brief) — a
  no-auth, no-DB liveness probe (`apps/api/app/routes/health_routes.py`) that always answers
  `{"status": "ok"}`. Leave interval/timeout/threshold at the console defaults unless you
  observe them being too aggressive during rollout.
- **Networking**: "Public endpoint"; outgoing traffic "Public" — the API talks to Supabase and
  the NVIDIA NIM endpoint over the public internet, so no VPC connector is needed.
- **Instance role** (distinct from the ECR access role in step 1 — this is what the *running
  container* itself is allowed to do via the AWS SDK/metadata endpoint): **none needed**.
  AdvisorDesk's API never calls another AWS service directly at runtime (the database is
  Supabase, not RDS; there's no S3/SQS/etc. usage) — App Runner ships stdout/stderr to
  CloudWatch Logs automatically without requiring this role. Leave it unset (or select "None"
  if the console requires an explicit choice).

## 3. Environment variables

Set every variable in `infra/deploy/env-checklist.md`'s "API (App Runner)" rows. The task-02
brief pins these **non-secret** values verbatim — set them exactly as written:

| Variable | Value |
|---|---|
| `GOOGLE_REDIRECT_URI` | `https://api.advisordesk.tyagiakanksha.com/api/v1/auth/callback` |
| `CORS_ORIGINS` | `https://advisordesk.tyagiakanksha.com,https://admin.advisordesk.tyagiakanksha.com` |
| `MCP_HTTP_ENABLED` | `true` |
| `FORWARDED_ALLOW_IPS` | start UNSET; then per the step-2 escalation ladder (observed peer range preferred; `*` only if spoof-check passes) |
| `ADMIN_APP_URL` | `https://admin.advisordesk.tyagiakanksha.com` |
| `ENVIRONMENT` | `production` |

Every remaining variable (`DATABASE_URL`, `NVIDIA_API_KEY`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, `ADMIN_EMAILS`, and the rest) is either a secret you
paste in from its own source, or a non-secret tunable with a sensible default — see
`env-checklist.md` for the complete table with sources. **Paste secret values directly into the
App Runner console's environment variable form — never into any file in this repo.**

## 4. Deploy, then link the custom domain

Once the service is running and `https://<the-apprunner-default-domain>/api/v1/healthz` returns
`{"status": "ok"}`, link the real domain:

App Runner service → **Custom domains** → **Link domain** → `api.advisordesk.tyagiakanksha.com`.

App Runner will show you a set of DNS records to create (typically a CNAME target for the
hostname itself, plus one or more CNAME records for ACM certificate validation). Create **every
one of them** in Cloudflare:

- **DNS is on Cloudflare.** Every record App Runner asks for must be created **DNS-only (grey
  cloud icon — never the orange "Proxied" icon)**. Cloudflare's proxy buffers responses
  (breaking `/api/v1/public/chat`'s unbuffered SSE streaming) and adds a second, redundant TLS
  termination hop in front of App Runner's own — both are actively harmful here, not just
  unnecessary.
- **Known Cloudflare gotcha (from the owner's own portfolio-site setup): the record-creation
  form can silently reflow mid-fill and save as Proxied even when you clicked "DNS only."**
  After saving **each** record, reload the DNS records list and re-check its proxy-status icon
  before moving to the next one — don't trust the icon you last saw in the form before saving.
- Leave the portfolio root/`www` records on this same Cloudflare zone completely untouched —
  this task only adds the three `advisordesk`/`admin.advisordesk`/`api.advisordesk` subdomains.

Certificate validation can take a few minutes to a couple of hours. Once App Runner shows the
custom domain as "Active", `https://api.advisordesk.tyagiakanksha.com/api/v1/healthz` should
return `200 {"status": "ok"}` — record that (and the rest of the deployed checklist) in
`infra/deploy/VERIFY.md`.

## ECS Fargate alternative (PRD §11 row 5)

App Runner is the default here because it needs zero additional infrastructure to get HTTPS, a
custom domain, and autoscaling for a single container — exactly the shape of this deployment. If
the owner instead wants the ECS Fargate path: push the same `advisordesk/api` ECR image (no
Dockerfile changes) into a Fargate **task definition** (container port 8000, the same environment
variables as above — including `FORWARDED_ALLOW_IPS`, which uvicorn reads from the environment
natively), run it as a **Fargate service** with `awsvpc` networking behind
an **Application Load Balancer** (the ALB is what terminates TLS and does the health check against
`/api/v1/healthz` here — Fargate itself has no built-in custom-domain/certificate flow the way
App Runner does), and point the same Cloudflare custom-domain CNAME at the ALB's DNS name instead
of the App Runner default domain. This trades App Runner's "no ALB, no task definition, no
service to hand-wire" simplicity for full control over networking, task placement, and scaling
policy — worth it for a multi-container or higher-traffic production system, but more moving
parts than this portfolio-scale, single-container API needs.
