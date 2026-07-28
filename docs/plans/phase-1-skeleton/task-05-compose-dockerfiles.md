---
id: task-05
phase: phase-1-skeleton
depends_on: [task-03, task-04]
status: planned
spec: advisordesk-prd.md §3.1, §9, §10 Phase 1
---

# task-05 — Dockerfiles and compose, including the local-db profile

## Goal

`docker compose up` serves the API and both frontends; `docker compose --profile local-db up`
additionally provides pgvector Postgres for fully-offline dev (PRD §9). This closes the §10
Phase 1 definition of done.

## Context (read ONLY these)

- `advisordesk-prd.md` §3.1 (infra file names: `docker-compose.yml`, `Dockerfile.api`,
  `Dockerfile.web` shared with build arg), §9 (local-db profile, Supabase default), §10 Phase 1.
- `CONVENTIONS.md` §11 (image + compose rules).

## Files

- Create: `infra/Dockerfile.api`, `infra/Dockerfile.web`, `infra/docker-compose.yml`
- Modify: `README.md` (dev quickstart: both DB paths, migration command)

## Interfaces

- **Consumes:** task-03 healthz + `main.py`; task-04 app scaffolds/ports.
- **Produces (later tasks rely on — produce exactly):**
  - Service names `api` / `admin` / `client` / `db` (profile `local-db`) — phase-4 seed and
    phase-6 deploy tasks reference them.
  - Ports on loopback: `127.0.0.1:8000:8000`, `127.0.0.1:3001:3000` (admin),
    `127.0.0.1:3000:3000` (client).
  - Migration invocation (documented in README, reused by phase-4 task-04):
    `docker compose -f infra/docker-compose.yml run --rm api uv run alembic upgrade head`.

## Steps (TDD)

*(Infra task — the "test" is the running stack; each step states its observable check.)*

- [ ] **Step 1: `Dockerfile.api`** — multi-stage uv (builder: manifests → `uv sync --frozen
  --no-dev` → copy `app/` → final sync; runtime: `python:3.11-slim`, copy venv, non-root
  `appuser`, stdlib-only `HEALTHCHECK` on `/api/v1/healthz`,
  `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`).
  Check: `docker build -f infra/Dockerfile.api .` succeeds;
  `docker run --rm -p 127.0.0.1:8000:8000 -e DATABASE_URL=... <img>` → healthz 200.
- [ ] **Step 2: `Dockerfile.web`** — `ARG APP` selects `apps/admin` or `apps/client`; pnpm build,
  Next standalone output, non-root runtime. Check: both `--build-arg APP=admin|client` images
  build and serve.
- [ ] **Step 3: `docker-compose.yml`** — services api/admin/client with `env_file: ../.env`,
  loopback ports, healthchecks, `depends_on`; `db` service `pgvector/pgvector:pg16` under
  `profiles: [local-db]` with a named volume and healthcheck; comment block documenting that
  `DATABASE_URL` points either at Supabase (default) or `db` (profile).
- [ ] **Step 4: Both paths boot.** `docker compose -f infra/docker-compose.yml up -d` (Supabase
  URL in `.env`) → all healthchecks green; down; `--profile local-db up -d` → db healthy, run the
  migration command, api healthy.
- [ ] **Step 5: README quickstart** — prerequisites, `.env` setup from `.env.example`, both DB
  paths, migration command, the five Python + frontend gate commands.
- [ ] **Step 6: Commit:** `chore(infra): dockerfiles + compose with local-db profile (phase-1 task-05)`

## Verify

```bash
docker compose -f infra/docker-compose.yml --profile local-db up -d --build
docker compose -f infra/docker-compose.yml run --rm api uv run alembic upgrade head  # 0001 applied
curl -s localhost:8000/api/v1/healthz    # {"status":"ok"}
curl -sI localhost:3001 | head -1        # HTTP/1.1 200 OK (admin)
curl -sI localhost:3000 | head -1        # HTTP/1.1 200 OK (client)
docker compose -f infra/docker-compose.yml --profile local-db down
```

## Acceptance

- §10 Phase 1 definition of done holds: scaffold + boots + schema migrated + both compose paths
  run + health endpoint answers.
- Ports published on loopback only; images run as non-root; no secrets baked into images.
- README documents both DB paths (§9) with Supabase as default.
