# AdvisorDesk

A CMS + retrieval-augmented client assistant for financial advisory content: a Next.js admin app
for authoring, a Next.js client app for browsing content and chatting with an assistant grounded
in that content, and a FastAPI backend that serves both over REST/SSE and exposes an in-process
MCP tool surface for the agent loop.

## Dev quickstart

### Prerequisites

- Docker + Docker Compose v2 (tested with Docker 29.2, Compose v5.1)
- [uv](https://docs.astral.sh/uv/) — only needed for running `apps/api`'s gates outside a container
- Node 24 + [pnpm](https://pnpm.io/) via corepack (`corepack enable`) — only needed for running the
  frontend gates outside a container

### 1. Configure environment

```sh
cp .env.example .env
```

Fill in `.env` — see PRD §9 for what each variable does. `DATABASE_URL` has two valid values,
described next. **Never commit `.env`** (it's gitignored; only `.env.example` is tracked).

Generate a `SESSION_SECRET` (required in every environment, including local/offline dev —
`app.main` fails fast at boot if it's empty):

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Admin login additionally needs real Google OAuth credentials (`GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET`); without them the app still boots in dev, but logging into the admin
app won't work until they're set.

`CORS_ORIGINS` ships pre-filled with the two local dev origins (`http://localhost:3000,
http://localhost:3001`) so cross-origin requests from `apps/client`/`apps/admin` work
out of the box; update it to your deployed frontend origins outside local dev.

### 2. Choose a database path (PRD §9)

**Supabase (default, and the deployed target):** set `DATABASE_URL` in `.env` to your Supabase
Postgres connection string, then run the stack without the `local-db` profile:

```sh
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml run --rm api uv run alembic upgrade head
```

**Local Postgres (fully offline dev), canonical:** set `DATABASE_URL` in `.env` to
`postgresql://postgres:postgres@db:5432/postgres` — same shape as the Supabase path above, just
with the `local-db` profile added, which starts a `pgvector/pgvector:pg16` container as the `db`
service:

```sh
docker compose -f infra/docker-compose.yml --profile local-db up -d --build
docker compose -f infra/docker-compose.yml run --rm api uv run alembic upgrade head
```

Note the `db` service name (not `localhost`) — containers reach each other over the compose
network, not the host loopback. `db`'s data persists in the named volume `advisordesk_local_db`
across restarts; `docker compose ... --profile local-db down -v` also removes it.

**Local Postgres, shell-export alternative:** if you'd rather not edit `.env` (e.g. it's already
pointed at Supabase and you only want to swap databases for one session), export `DATABASE_URL` in
the shell instead of setting it in `.env`. `docker compose ... up` picks up a shell-exported value
correctly (it arrives under a side-channel name, `DATABASE_URL_SHELL_OVERRIDE`, that
`infra/Dockerfile.api`'s `CMD` promotes to `DATABASE_URL` at container start — see the compose
file's `environment:` comment for why it's wired that way). The migration command is different,
though: `docker compose run <cmd>` *replaces* the image's `CMD` outright, so that promotion logic
never runs for it — a bare `run --rm api uv run alembic upgrade head` here would resolve an empty
`DATABASE_URL` and fail. Pass `-e DATABASE_URL="$DATABASE_URL"` on the `run` command itself instead;
a CLI `-e` beats `env_file` for that one container (verified live):

```sh
export DATABASE_URL=postgresql://postgres:postgres@db:5432/postgres
docker compose -f infra/docker-compose.yml --profile local-db up -d --build
docker compose -f infra/docker-compose.yml run --rm -e DATABASE_URL="$DATABASE_URL" api uv run alembic upgrade head
```

Either way, migrations are **never** run at container startup (CONVENTIONS.md §6) — the
`uv run alembic upgrade head` command above is the only DDL path, and is the one command reused
verbatim by later phases' seed/deploy tasks.

### 3. Verify

```sh
curl -s localhost:8000/api/v1/healthz    # {"status":"ok"}
curl -sI localhost:3001 | head -1        # HTTP/1.1 200 OK (admin)
curl -sI localhost:3000 | head -1        # HTTP/1.1 200 OK (client)
```

### 4. Tear down

```sh
docker compose -f infra/docker-compose.yml --profile local-db down   # add -v to drop the local db volume too
```

(`--profile local-db` is harmless to pass even if you ran the Supabase path — compose only tears
down services that are actually running.)

## Demo

An end-to-end walkthrough of both PRD §2.2 user stories, anchored on the real seeded content
(`seed/sample_content/`, `seed/eval_questions.yaml`) — no invented examples. Two independent
choices: which story (client, fully scriptable — or admin, a UI walkthrough behind Google
sign-in) and where to run it (locally per Dev quickstart above, or against the live deployment).

### Client story: browse content + ask grounded questions

Public, no auth. Point at a local API (`http://localhost:8000`, after Dev quickstart steps 1–3)
or the live one (`https://api.advisordesk.tyagiakanksha.com`) — every command below works against
either; `./scripts/demo.sh` runs all three (`BASE_URL=... ./scripts/demo.sh` to target the live
site).

**1. Browse published content** — `GET /api/v1/public/content`:

```sh
curl -s http://localhost:8000/api/v1/public/content | head -c 300
```

Returns a JSON array of published, non-deleted articles (`title`, `slug`, `tags`,
`published_at`). Captured live (2026-09-06): 27 published articles — the pristine 17-article seed
corpus plus ~10 the owner has published since (a fresh local seed gives exactly 17); either way
`roth-ira-conversion-basics` (used below) is present.

**2. Ask a real, answerable question** — one of `seed/eval_questions.yaml`'s entries — and watch
a streamed, cited answer (`POST /api/v1/public/chat`, body `{"message": "..."}`, optional
`session_id`):

```sh
curl -N -s -X POST http://localhost:8000/api/v1/public/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is a Roth IRA conversion and how is it taxed?"}'
```

Captured live output (trimmed — token events repeat one word/punctuation mark per event):

```
event: token
data: {"text": "A"}

event: token
data: {"text": " Roth"}

event: token
data: {"text": " IRA"}
...
event: token
data: {"text": "]."}

event: citations
data: {"citations": [{"content_id": "5b01f642-b239-4ccd-83e3-88412b367313", "title": "Roth IRA Conversion Basics", "slug": "roth-ira-conversion-basics"}, {"content_id": "0e05672a-7341-4bc5-af6e-e76624d31043", "title": "Backdoor Roth IRA Basics", "slug": "backdoor-roth-ira-basics"}]}

event: done
data: {"session_id": "59c704a1-0e3d-4f69-a5c1-17b64226b2bf", "message_id": "2c0808de-dd43-43fd-86cc-0d2426630708"}
```

Assembled answer: "A Roth IRA conversion moves money from a traditional IRA (or another pre-tax
retirement account, such as a traditional 401(k) rolled into an IRA) into a Roth IRA. The amount
converted is treated as ordinary income in the year of the conversion... [1]." — cited to the
exact article `eval_questions.yaml` expects (`expected_slugs: ["roth-ira-conversion-basics"]`).

**3. Ask a real, unanswerable question** — one of the eval set's four deliberately-uncovered
topics (`answerable: false`) — and see the assistant refuse rather than answer from general
knowledge:

```sh
curl -N -s -X POST http://localhost:8000/api/v1/public/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What does the firm recommend about cryptocurrency staking rewards?"}'
```

Captured live output (trimmed):

```
event: token
data: {"text": "No"}
...
event: token
data: {"text": "."}

event: citations
data: {"citations": [{"content_id": "5fe48a7f-641b-472d-b7d9-2981035f6735", "title": "Diversification and Asset Allocation Basics", "slug": "diversification-and-asset-allocation-basics"}]}

event: done
data: {"session_id": "d88ddc81-290a-42e0-b75e-945bbd6341e7", "message_id": "cfbd0b82-a018-4668-bdbc-f22a803235fe"}
```

Assembled answer: "No published guidance covers this; please ask the advisory team for
assistance." — the refusal PRD §7.5 requires ("does not answer from general knowledge") lives in
the answer text itself. Note `citations` is not always empty here: retrieval still surfaces
whatever chunk cleared `SIMILARITY_THRESHOLD` (default `0.5` — model-dependent; retuned from the
earlier NVIDIA-embedding-era `0.35` when the app switched to OpenAI's `text-embedding-3-small`),
even a loosely-related one that doesn't actually answer the question — verified consistently across all four of
`eval_questions.yaml`'s unanswerable entries while authoring this walkthrough. The refusal
wording is the reliable signal that the question wasn't answered, not an empty citations array.

### Admin story: sign in + the agent panel

Needs an authenticated, allowlisted admin session, so this half is UI steps, not curl. Prerequisite:
Google OAuth credentials and your email in `ADMIN_EMAILS` (Dev quickstart step 1) — the live
deployed admin only accepts the owner's own allowlisted account.

1. **Sign in** at the admin app (`http://localhost:3001` locally, or
   `https://admin.advisordesk.tyagiakanksha.com`) with an allowlisted Google account.
2. **Dashboard** — lands on a dashboard of all content: status, tags, updated date.
3. **Content list** — click **Content** in the left nav for the full CRUD list; filter/search by
   title, tag, and status.
4. **Agent panel** — click **Agent** in the top bar to open the agent chat sidebar (a persistent
   drawer on the right). Issue the PRD §2.2 example commands verbatim; the panel renders each
   `tool_call`/`tool_result` event live as it happens:
   - *"Draft an article on Roth IRA conversion basics and tag it retirement."* — the agent calls
     `create_draft`; a new draft appears in the content list (agent-created drafts are never
     auto-published).
   - *"How many published pieces do we have on tax planning?"* — the agent calls
     `count_content(status="published", tag="tax-planning")`. Against a freshly-seeded database
     (Dev quickstart) this reports **7** — cross-checked directly against
     `seed/sample_content/`'s frontmatter: 7 of the 8 tax-planning-tagged seed files are
     `status: published`; the 8th, `year-end-tax-planning-checklist`, is deliberately left
     `draft` (PRD §8) so the agent has something to find/publish in the next command. On the live
     deployed site the number will be different (and keeps growing) since the owner has published
     content beyond the seed — what to verify is the agent calling the right tool with the right
     filters, not a specific number.
   - *"Find everything tagged estate-planning and publish the drafts."* — the agent calls
     `search_content` then `publish` for each match; the dashboard's draft/published counts update.

### Two ways to run this

- **Run it yourself (local):** finish Dev quickstart steps 1–3, then run the client-path commands
  above (or `./scripts/demo.sh`) against `http://localhost:8000`, and the admin steps against
  `http://localhost:3001`. The client chat path needs `OPENAI_API_KEY` set (Dev quickstart step
  1); the admin story additionally needs your own Google OAuth app and your email in
  `ADMIN_EMAILS`.
- **See it live:** client at `https://advisordesk.tyagiakanksha.com` (content list + `/chat`),
  API at `https://api.advisordesk.tyagiakanksha.com` for the curl commands above, admin at
  `https://admin.advisordesk.tyagiakanksha.com` (owner's allowlisted account only).

### Gates (run before every commit that touches the relevant app)

Python (`apps/api`):

```sh
cd apps/api
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest -q
```

Frontend (`apps/admin`, `apps/client` — same three commands, run once per app):

```sh
pnpm -C apps/admin lint
pnpm -C apps/admin type-check
pnpm -C apps/admin test

pnpm -C apps/client lint
pnpm -C apps/client type-check
pnpm -C apps/client test
```

## Metrics

PRD §9.1's four metrics, **measured on the local seeded stack** (OpenAI provider —
`text-embedding-3-small@1024`, `SIMILARITY_THRESHOLD=0.5`). The corpus, groundedness and
agent-suite rows are phase 9's `rebaseline-2026-09` (2026-09-13, `gpt-5.4-mini` answerer /
`gpt-5.4` judge, dedicated database `advisordesk_p9rebaseline`; committed record:
`docs/plans/phase-9-eval-data-loop/verification-record.md`). The latency row is phase 7's capture
(2026-09-07, `gpt-4o-mini`, `docs/plans/phase-7-evaluation/verification-record.md`) and has not
been re-measured since the model change.

| Metric | Value |
|---|---|
| Seeded documents (content) | 37 total (33 published + 4 drafts) |
| Seeded chunks | 228 |
| MCP tools | 14 (8 core + `report_content_gaps`, `report_weak_queries`, and the four proposal tools `propose_content_fix`/`list_proposals`/`accept_proposal`/`reject_proposal`) |
| Groundedness | 93.0% ± 1.6 fully supported over 3 runs (label `rebaseline-2026-09`, `gpt-5.4-mini` answerer / `gpt-5.4` judge); refusals 18/18 correct |
| Agent suite baseline | 83.3% ± 10.0 over 3 fresh-DB runs (9/10, 8/10, 8/10) — temperature 0 does not make this model's tool-calling deterministic; see verification-record §9a |
| First-token latency, `/public/chat` | p50 = 717 ms, p95 = 1602 ms (n=30, nearest-rank) |

**Groundedness note (updated 2026-09, phase 9):** the previously published 58.8% was a single,
unpersisted run measured while the answerer still ran at `temperature=1.0` (fixed 2026-09-11) and
was judged by the same `gpt-4o-mini` model that wrote the answers — it was sampling noise, not a
measurement, and it is retired rather than silently overwritten. Evaluation runs are now persisted
(`eval_runs`/`eval_results`) and every metric is reported with its spread over three runs; the
baseline above is the label `rebaseline-2026-09`, judged by `gpt-5.4` (the answerer is
`gpt-5.4-mini`). The earlier `baseline-2026-09` figure (72.5% ± 5.9) is itself now superseded
(2026-09-13): it measured the older `gpt-4o-mini`/`gpt-4o` pair, a judge that still scored
markdown/citation markers and abbreviation-split sentences as unsupported claims, and a
21-question set over a smaller, since-expanded corpus, so it is retired rather than compared
against directly. Full method, run ids and per-class/failure-cause breakdowns:
[`docs/plans/phase-9-eval-data-loop/verification-record.md`](docs/plans/phase-9-eval-data-loop/verification-record.md).

## Deployment

AWS deployment scripts and step-by-step console walkthroughs live in `infra/deploy/`:

- `infra/deploy/push_ecr.sh` — builds, tags, and pushes the three images (`api`, `admin`,
  `client`) to Amazon ECR.
- `infra/deploy/database.md` — apply Alembic migrations and seed the sample corpus against the
  deployed Supabase database. **Run this before the API service (below) is expected to serve
  real traffic** — the API's health check has no DB dependency, so an un-migrated database fails
  silently until real requests arrive.
- `infra/deploy/ec2-single-host.md` — **the deployed topology (doc of record)**: all three
  containers on one EC2 instance behind Caddy (auto-HTTPS), secrets in SSM Parameter Store,
  Cloudflare grey-cloud DNS. (The original AWS App Runner walkthroughs, `apprunner-api.md` and
  `frontends.md`, are superseded — App Runner closed to new AWS customers in April 2026 —
  but `frontends.md`'s build-time-vs-runtime wiring section for `NEXT_PUBLIC_API_URL` (admin)
  and `API_URL` (client) is still authoritative.)
- `infra/deploy/env-checklist.md` — every production env var, which service needs it, whether
  it's a secret, and where its value comes from (no secret values are ever committed).
- `infra/deploy/VERIFY.md` — the deployed verification checklist (rate limiting, SSE, CORS, MCP
  auth, logout revocation, latency metrics) — see PRD §10 Phase 6.

## Implementation notes

- **Build contexts.** Both `infra/Dockerfile.api` and `infra/Dockerfile.web` build with the repo
  root as context (`build: {context: .., dockerfile: infra/Dockerfile.*}` in
  `infra/docker-compose.yml`) — the API image only needs `apps/api/`, but the web image needs the
  pnpm workspace root (`package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`) plus the one app
  directory selected by `--build-arg APP`.
- **Root `.dockerignore` (added, not explicitly listed in the task brief).** Without it, every
  `docker build` from the repo-root context would tar up `reference_project/` (~2.5 GB, vendored
  and gitignored), `node_modules/` (~650 MB), and `apps/api/.venv/` (~170 MB) before the daemon
  even started resolving layers. None of these are `COPY`'d by either Dockerfile, so this only
  changes build-context size, not image contents; `.env`/`*.env` are also excluded as defense in
  depth (neither Dockerfile `COPY`s them either).
- **Next.js `output: 'standalone'`.** Neither `apps/admin/next.config.ts` nor
  `apps/client/next.config.ts` set this before task-05 — both now do, since `infra/Dockerfile.web`'s
  runtime stage needs the self-contained `.next/standalone` server bundle rather than a full
  `pnpm install` in the runtime image.
- **Standalone server path (checked against real build output, not guessed).** Because this is a
  pnpm workspace with a root `package.json`, `next build`'s standalone tracer mirrors the
  repo-relative path rather than flattening it: the runnable entrypoint is
  `.next/standalone/apps/<app>/server.js`, with a hoisted `node_modules/` at the tree root. The
  runtime stage copies the standalone tree's *contents* into `/app` and runs
  `node apps/$APP/server.js`. Docker does **not** expand `ARG`/`ENV` inside exec-form
  `CMD`/`ENTRYPOINT` arrays (only `ENV`, `LABEL`, `COPY`, etc. get variable substitution), so a
  literal `CMD ["node", "apps/${APP}/server.js"]` would try to run a path containing the literal
  string `${APP}`. `Dockerfile.web` instead bakes `APP` into a build-time-fixed `ENV` and runs
  `CMD ["sh", "-c", "node apps/$APP/server.js"]` so the shell expands it at container start.
- **Missing `public/` directories.** Neither `apps/admin` nor `apps/client` has a `public/`
  directory yet (both use only the App Router's special files, e.g. `favicon.ico` under `src/app/`).
  `Dockerfile.web`'s builder stage runs `mkdir -p apps/${APP}/public` before `next build` so the
  runtime stage's `COPY --from=builder .../public ...` always has a source, even with zero static
  assets today.
- **`uv` binary in the API runtime image.** The task-05 interface contract fixes the migration
  command as `docker compose ... run --rm api uv run alembic upgrade head` (reused verbatim by a
  later phase-4 task) — that requires `uv` itself to be on `PATH` in the *runtime* image, not just
  the `ghcr.io/astral-sh/uv` builder stage. `Dockerfile.api`'s runtime stage adds
  `COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv` for exactly this; without it, `uv run`
  fails with `exec: "uv": executable file not found in $PATH` (observed while verifying this task).
- **`depends_on` on a profile-gated service (verified against Compose v5.1).** A bare
  `api: depends_on: db: condition: service_healthy` is a **hard compose-level error** whenever `db`
  isn't part of the run — `docker compose -f infra/docker-compose.yml config` (no `--profile
  local-db`) fails immediately with `service "api" depends on undefined service "db": invalid
  compose project`, before any container starts; it is not a silent no-op. Adding
  `required: false` under the `db` dependency fixes this: absent (`db` not part of the run) →
  the dependency is skipped entirely; present (`--profile local-db` active) → `condition:
  service_healthy` still gates `api`'s startup on `db` passing its `pg_isready` healthcheck
  (observed directly: `up -d --profile local-db` shows `Container infra-db-1 Healthy` before
  `Container infra-api-1 Starting` in the compose log).
- **`5432` publish decision.** Port `127.0.0.1:5432` was free on the verification machine (only
  `127.0.0.1:5433`, the unrelated throwaway `advisordesk-test-db` container, was occupied), so the
  `local-db` profile's `db` service publishes `127.0.0.1:5432:5432` as specified. If `5432` is
  occupied on your machine, drop that `ports:` entry from `infra/docker-compose.yml` — the `db`
  service is still reachable by every other compose service over the compose network at
  `db:5432`; only host-side (`psql` from the host, a GUI client, etc.) access needs the publish.
- **Non-profile-path verification technique (not shipped).** To prove `docker compose up -d`
  (no profile) boots `api`+`admin`+`client` without the `db` service, verification pointed
  `DATABASE_URL` at the pre-existing `advisordesk-test-db` throwaway container's
  `127.0.0.1:5433` host-published port. A container reaches a host port published to `127.0.0.1`
  specifically (not `0.0.0.0`) only via `network_mode: host` — bridge-network gateway routing
  (`host.docker.internal`) does not reach a `127.0.0.1`-scoped publish. This was done with a
  temporary, un-committed compose override applying `network_mode: host` to `api` only, purely
  for this check; it is not part of `infra/docker-compose.yml`, and real Supabase usage needs no
  such trick since it's reachable over the public internet from a normally-bridged container.
- **Frontend containers never see backend secrets.** `admin`/`client` in `infra/docker-compose.yml`
  deliberately omit `env_file: ../.env` — only `api` has it. `.env` carries backend secrets
  (`OPENAI_API_KEY`, `SESSION_SECRET`, `GOOGLE_CLIENT_SECRET`, `DATABASE_URL`, ...); none of that
  belongs inside a browser-served Next.js image. Each frontend service gets only the API-base
  value(s) it actually needs, passed explicitly rather than inherited wholesale: `admin` takes
  `NEXT_PUBLIC_API_URL` as a build `arg` (inlined into its browser bundle); `client` takes both
  `NEXT_PUBLIC_API_URL` as a build `arg` (inlined into its browser bundle too, same mechanism as
  admin's — `apps/client/src/components/chat/useChatStream.ts` reads it for the browser-side
  chat POST, so it is load-bearing, not unused) and `API_URL` as **both** a build `arg` and an `environment:` entry (final review,
  F1) — `API_URL` backs apps/client's server-only `src/lib/publicApi.ts`, which `next build`
  itself calls during prerendering (build-time) and which also runs per-request after the
  container starts (runtime), so a build arg alone isn't enough. Both point at the compose
  network's `api:8000` origin, not `localhost`.
- **Chunking tokenizer choice (`app/rag/chunking.py`, phase-3 task-01).** PRD §7.1 sizes chunks in
  "tokens" without naming a tokenizer. `count_tokens`/`chunk_markdown` use `tiktoken`'s
  `cl100k_base` encoding — a stable, deterministic, offline-after-first-download proxy for chunk
  sizing. This is **not** the embedding model's own tokenizer: the embedding model is OpenAI's
  `text-embedding-3-small` (PRD §7.1 v1.6; was NVIDIA's `nvidia/nv-embedqa-e5-v5` before the
  2026-09-06 provider switch) and `cl100k_base` is a separate, standalone tokenizer used purely
  to make the ~400-token target/50-token-overlap budget reproducible, not to mirror either
  embedding model's exact token boundaries.
- **Runtime Python version.** `Dockerfile.api`'s runtime stage runs on `python:3.12-slim-bookworm`.
  `apps/api/pyproject.toml` sets `requires-python = ">=3.11"` as a floor, not a pin; `3.12` is what
  the builder stage (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`) and local dev already use, so
  the runtime image stays version-matched to dev rather than drifting to whatever "latest 3.11+"
  a generic base image resolves to later.
- **Pagination envelope field names (phase-2 task-03).** Every paginated list response uses the
  same four field names — `items`, `total`, `page`, `page_size` — via a generic
  `app.models.schemas.common.PaginatedResponse[T]` that per-resource DTOs (e.g.
  `ContentListResponse`) specialize rather than reinventing. `total` is the full filtered count,
  independent of `page`/`page_size`. Any later paginated endpoint (e.g. PRD §5.3's
  `GET /public/content`) should specialize the same generic instead of introducing new field
  names, so the admin/client codegen consumers only ever deal with one page shape.
- **`app/seed.py`'s `content_dir` resolution vs. its own pinned Real Run command (phase-4
  task-04).** The task brief's Real Run command (`cd apps/api && ... && uv run python -m app.seed`)
  runs with `apps/api` as the process's working directory — `seed_all`'s Interfaces-pinned default
  (`content_dir=Path("seed/sample_content")`) resolves relative to *that* cwd, where the directory
  does not exist (only `<repo-root>/seed/sample_content` does). Rather than change the tested
  default, `python -m app.seed`'s `__main__` entry point (`_run_from_cli`) resolves the real
  `content_dir` through `app.seed_paths.seed_data_dir()`, which prefers `$SEED_DATA_DIR` (baked to
  `/app/seed` in the container image) and otherwise falls back to the repo-root `seed/` relative to
  its own file location — so `seed_all`'s signature and default are untouched, and the one call site
  resolves the path robustly regardless of invocation cwd *or* host-vs-container layout. (An earlier
  version computed this off `Path(__file__).resolve().parents[3]`, which crashed in the container's
  shallower `/app/app/...` layout; the env-driven resolver + `COPY seed` into the image fixed the
  containerized seed — see the phase-7 verification record.) Caught by actually running the Real Run
  command as written (first attempt silently produced `SeedReport(created=0, published=0, skipped=0,
  chunk_count=0)` — no error, just an empty glob).
- **Seeded documents and chunks (PRD §9.1 metric input; phase-4 task-04).** 21 original sample
  advisory articles (`seed/sample_content/`, spread across the six PRD §8 tags, every tag used ≥2
  times): 17 `status: published`, 4 `status: draft` (left for the phase-5 agent demo). Real run
  against the local `advisordesk-test-db` container (`127.0.0.1:5433`, migrated to head,
  real OpenAI `text-embedding-3-small` embedding calls, no fakes): first run —
  `SeedReport(created=21, published=17, skipped=0, chunk_count=100)`; an immediate re-run —
  `SeedReport(created=0, published=0, skipped=21, chunk_count=0)` — confirms idempotency against a
  real database, not just the fake-embedder test suite. (The database's raw `content`/`chunks`
  table totals are 2 rows and 1 chunk higher than these numbers: two pre-existing rows from earlier
  phase-3/phase-4 task verification smoke tests against this same shared dev database, unrelated to
  the seed corpus.) `seed/eval_questions.yaml` — the phase-7 groundedness harness's input (PRD
  §8.1) — has 17 answerable questions (each `expected_slugs` a real published seed slug) and 4
  deliberately-unanswerable questions on topics absent from the corpus (crypto staking, options
  strategies, offshore trusts, REIT syndication).
