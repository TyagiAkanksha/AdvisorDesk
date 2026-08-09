# Frontends on AWS App Runner

Deployment guide for the `advisordesk/admin` and `advisordesk/client` images (phase-6 task-02).
Like `apprunner-api.md`, this is a walkthrough for the **owner to run interactively** — nothing
here runs automatically. Both frontends deploy the same way as the API: App Runner services
built from the images `push_ecr.sh` already pushed to ECR (implementation note per the task-02
brief: "the two web containers, App Runner too").

```sh
AWS_ACCOUNT_ID=<your account id> ./infra/deploy/push_ecr.sh
```

## The API-base wiring: build-time vs runtime (check this before deploying)

`infra/Dockerfile.web` builds ONE shared image shape for both apps, selected by `--build-arg
APP=admin|client`. The two apps wire their API base differently, and it matters for how you
configure each App Runner service:

- **`admin`: `NEXT_PUBLIC_API_URL` is a BUILD-TIME-ONLY value.** `Dockerfile.web`'s builder
  stage sets `ARG NEXT_PUBLIC_API_URL=http://localhost:8000` / `ENV NEXT_PUBLIC_API_URL=...`
  before `next build` — Next.js inlines every `NEXT_PUBLIC_*` variable straight into the
  browser-served JS bundle at that build step (`apps/admin/src/lib/apiBase.ts` reads it at
  module-load time, both for its RTK Query base URL and the raw Google-OAuth anchor href).
  **There is no runtime environment variable for this on the deployed admin service** — setting
  `NEXT_PUBLIC_API_URL` in the App Runner console after the fact does *nothing*; the value is
  already baked into the JS the browser downloads. If the API's public origin ever changes,
  rebuild+repush the admin image (`push_ecr.sh`'s `API_PUBLIC_URL` env var) and redeploy — there
  is no "just restart the container" fix.
- **`client`: `API_URL` is needed at BOTH build time AND runtime.** `apps/client/src/lib/
  publicApi.ts` reads `process.env.API_URL` directly (deliberately *not*
  `NEXT_PUBLIC_`-prefixed — this module only ever runs server-side, inside React Server
  Components). Two things need it:
  1. `next build` itself calls this code during its "Generating static pages" step, so
     `Dockerfile.web`'s builder stage needs `API_URL` as a build arg too (already wired by
     `push_ecr.sh`).
  2. The same code runs again on every real request after the container starts (SSR,
     per-request fetches) — the App Runner **client** service also needs `API_URL` set as a
     **plain runtime environment variable**, or every page render fails once the build-time
     value (whatever `push_ecr.sh` baked in) stops matching what's actually needed, or if you
     ever want to point a running container at a different API origin without a full rebuild.
  `infra/docker-compose.yml`'s `client` service sets `API_URL` both ways (`build.args` AND
  `environment:`) for exactly this reason — mirror that split here.
- `client`'s image also carries a harmless, unused `NEXT_PUBLIC_API_URL` build arg
  (`push_ecr.sh` sets it for consistency) — nothing in `apps/client` reads it today (no
  client-rendered fetch yet).

## Create each service

For **both** `admin` and `client`, in the AWS console: App Runner → **Create service** →
"Container registry" → "Amazon ECR" → the matching repo (`advisordesk/admin` or
`advisordesk/client`) → the git-sha tag `push_ecr.sh` pushed. Same "Manual" deployment trigger
and "Create new service role" ECR access role choice as `apprunner-api.md` step 1 — see that
doc for why.

- **Port**: `3000` for both — `infra/Dockerfile.web`'s runtime stage sets
  `ENV ... PORT=3000` and `EXPOSE 3000`.
- **Start command**: leave the image default (`sh -c "node apps/$APP/server.js"`) — unlike the
  API image, nothing here needs an override.
- **Health check**: Protocol HTTP, Path `/` — matches `Dockerfile.web`'s own stdlib `HEALTHCHECK`
  target (a plain TCP GET to `/`, treating any non-5xx status as healthy).
- **CPU / memory**: smallest size (1 vCPU / 2 GB) is enough for either app at this scale.
- **Auto scaling / Networking**: same defaults as the API service (`apprunner-api.md` step 2) —
  a single instance, public endpoint, no VPC connector.
- **Instance role**: none needed — neither frontend calls another AWS service at runtime.

### `admin` service — environment variables

None needed at runtime. `NEXT_PUBLIC_API_URL` is baked into the image already (see above) —
**do not** set it as an App Runner env var; it has no effect. The admin container also never
receives backend secrets (`NVIDIA_API_KEY`, `SESSION_SECRET`, `DATABASE_URL`, ...) — same
"frontend containers never see backend secrets" rule `infra/docker-compose.yml` follows (only
the `api` service loads `env_file`).

### `client` service — environment variables

| Variable | Value |
|---|---|
| `API_URL` | `https://api.advisordesk.tyagiakanksha.com` |

Set as a plain runtime environment variable — see the wiring explanation above for why this is
required in addition to (not instead of) the build-arg `push_ecr.sh` already baked in. Nothing
else — the client container also never receives backend secrets.

## Custom domains

Once each service is live on its App Runner default domain, link the real subdomains — same
flow as `apprunner-api.md` step 4 (App Runner service → **Custom domains** → **Link domain**):

- `client` → `advisordesk.tyagiakanksha.com`
- `admin` → `admin.advisordesk.tyagiakanksha.com`

**Same Cloudflare rules as the API domain** (full explanation in `apprunner-api.md` step 4 — read
it once, it applies identically here):

- Every DNS record App Runner asks for must be created **DNS-only (grey cloud — never
  Proxied)** in Cloudflare.
- Re-check each record's proxy-status icon *after saving* — the record form is known to
  silently reflow and save as Proxied even when "DNS only" was selected.
- The portfolio root/`www` records stay untouched.

Once both domains show "Active" with valid certificates, `https://advisordesk.tyagiakanksha.com`
and `https://admin.advisordesk.tyagiakanksha.com` should each 200 — record that (and the rest of
the deployed checklist) in `infra/deploy/VERIFY.md`.
