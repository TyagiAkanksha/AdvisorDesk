# API on AWS App Runner

Deployment guide for the `advisordesk/api` image (phase-6 task-02). This is a walkthrough for
the **owner to run interactively** in the AWS console (or the equivalent `aws apprunner` CLI
calls) — nothing in this repo runs it for you. Push the image first:

```sh
AWS_ACCOUNT_ID=<your account id> ./infra/deploy/push_ecr.sh
```

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
- **Start command** — **override the image's default CMD** with:

  ```sh
  sh -c 'exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"'
  ```

  **Why this override is necessary** (read this before skipping it): `infra/Dockerfile.api`'s
  own `CMD` deliberately does **not** pass `--forwarded-allow-ips` at all — its own comment
  explains that uvicorn's proxy-headers middleware, if told to trust `"*"`, would let a caller
  forge its own `X-Forwarded-For` and pick a fresh rate-limit bucket on every request (a real
  finding from an earlier review). The image leaves this unset so it defaults to trusting only
  `127.0.0.1`, and says explicitly: *"phase-6 task-02 ... is where a real proxy's actual egress
  range gets set explicitly, once one exists to trust."* That real proxy is App Runner's own
  ingress now — but the image's `CMD` has no mechanism to read a `FORWARDED_ALLOW_IPS`
  environment variable (nothing in `app/config.py` reads it either; it is not an application
  setting, it is a pure `uvicorn` CLI flag). This service-level **Start command** override is
  where that env var actually takes effect: App Runner injects every environment variable you
  set in step 3 into the container's shell environment before running the start command, so
  `"$FORWARDED_ALLOW_IPS"` expands to whatever you set `FORWARDED_ALLOW_IPS` to below (`*` —
  see `env-checklist.md`; safe specifically because the container is only ever reachable through
  App Runner's own ingress, never directly from the internet).

  This override is intentionally a **simplified** rewrite of the image's `CMD` — it drops the
  `DATABASE_URL_SHELL_OVERRIDE → DATABASE_URL` promotion shim the image's own `CMD` does. That
  shim exists solely for `infra/docker-compose.yml`'s local shell-export dev workflow (see that
  file's own `environment:` comment); it has no purpose here since a deployed App Runner service
  sets `DATABASE_URL` directly as a plain environment variable (step 3) — there's no "shell
  export" concept for App Runner to promote from.

- **CPU / memory**: the smallest size (1 vCPU / 2 GB) is plenty for a portfolio-scale
  deployment; increase later from the console with zero code changes if needed.
- **Auto scaling**: leave the default configuration (min 1 instance) — a single instance is
  enough to demo this app, and PRD §9's rate limiter is explicitly documented as in-memory /
  single-container (see `apps/api/app/routes/ratelimit.py`'s own docstring) — running more than
  one instance would split each cap's state per-instance, silently multiplying every limit.
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
| `FORWARDED_ALLOW_IPS` | `*` (only takes effect via the Start command override in step 2 above) |
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
variables and the same Start command override as above — Fargate task definitions support a
`command` override the same way), run it as a **Fargate service** with `awsvpc` networking behind
an **Application Load Balancer** (the ALB is what terminates TLS and does the health check against
`/api/v1/healthz` here — Fargate itself has no built-in custom-domain/certificate flow the way
App Runner does), and point the same Cloudflare custom-domain CNAME at the ALB's DNS name instead
of the App Runner default domain. This trades App Runner's "no ALB, no task definition, no
service to hand-wire" simplicity for full control over networking, task placement, and scaling
policy — worth it for a multi-container or higher-traffic production system, but more moving
parts than this portfolio-scale, single-container API needs.
