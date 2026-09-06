# Database (Supabase): migrate + seed, before the API serves traffic

Deployment guide for **Step 2** of the task-02 brief — applying Alembic migrations and seeding
the sample corpus against the deployed Supabase database. Like the other docs in
`infra/deploy/`, this is a walkthrough for the **owner to run interactively** from a local
checkout — nothing in this repo runs it for you, and nothing here is a container command (unlike
the local-dev path in the root `README.md`, which runs the same migration through `docker
compose run`).

**Do this BEFORE bringing the API up on the EC2 host (`ec2-single-host.md`), and before either
frontend.** `infra/Dockerfile.api`'s own top-of-file comment is explicit that
migrations are deliberately **not** run at container startup — Alembic is the only DDL path
(`CONVENTIONS.md` §6). The API's `/api/v1/healthz` check has no database dependency at all
(`apps/api/app/routes/health_routes.py`), so a service will come up "healthy" against an
un-migrated, unseeded database and then every real content/chat/auth request fails once traffic
arrives. Run the two commands below first, so the API has real tables and real content the
moment it starts serving:

**Ordering: Database (this doc) → the full stack on the EC2 host (`ec2-single-host.md` —
API + both frontends come up together via compose).**

## What you need

- A local checkout of this repo with [`uv`](https://docs.astral.sh/uv/) installed (same
  prerequisite as the root `README.md`).
- The Supabase pooler connection string — same `DATABASE_URL` value and source as
  `env-checklist.md`'s API row: Supabase dashboard → your project
  (`qfsknrtxibdtjyxxeykv`) → Connect → "Connection string".
- Your OpenAI API key — same `OPENAI_API_KEY` value and source as `env-checklist.md`'s API
  row: platform.openai.com → API keys. The seed step makes real embedding calls (via OpenAI's
  `text-embedding-3-small`), so this has to be a real, working key.

**Never put either value in a file in this repo — including this one.** Export them inline on
the command line, in your own shell, for these two one-shot commands only, exactly like every
other secret in `env-checklist.md`.

## 1. Apply migrations

```sh
cd apps/api && DATABASE_URL=<paste your Supabase pooler string here, in your shell only> \
  uv run alembic upgrade head
```

Must run **from `apps/api`** — there is no root `pyproject.toml`, so `uv run` at the repo root
is not inside the API project and cannot resolve `apps/api/alembic/env.py`'s imports.

Why the inline `DATABASE_URL=` is enough: `apps/api/alembic.ini`'s `sqlalchemy.url` is left
blank (`alembic.ini:94`), and `apps/api/alembic/env.py`'s `_database_url()` falls back to the
`DATABASE_URL` environment variable whenever the `.ini` doesn't pin one — no `.ini` edit needed.

This is idempotent — Alembic tracks applied revisions in its own `alembic_version` table, so
re-running `upgrade head` against an already-migrated database is a safe no-op.

## 2. Seed the sample corpus

```sh
cd apps/api && DATABASE_URL=<same pooler string as above> \
  OPENAI_API_KEY=<paste your OpenAI API key here, in your shell only> \
  uv run python -m app.seed
```

Same "must run from `apps/api`" reason as above — `python -m app.seed` needs the `app` package
importable, and the same reasoning applies to `scripts/mint_mcp_token.py` later
(`env-checklist.md`'s MCP bearer-token note).

This runs the real content lifecycle for every file in `seed/sample_content/*.md` — draft
creation, then a real publish (chunk + embed + insert) for everything marked
`status: published` — through the actual OpenAI `text-embedding-3-small` embedding endpoint, not
a fake. Expect it to take a little while and to count against your OpenAI API usage.

Expected output on a first run against a freshly migrated, empty database (the real numbers this
repo's own local run recorded — see the root `README.md`'s Implementation notes):

```text
seed_all: created=21 published=17 skipped=0 chunk_count=100
```

Also idempotent — `app/seed.py` checks by content **title**, not slug or filename
(`apps/api/app/seed.py`'s own docstring explains why slug-keying would be wrong here). Re-running
against an already-seeded database reports every file `skipped` and creates nothing new:

```text
seed_all: created=0 published=0 skipped=21 chunk_count=0
```

## Next

Once both commands above have run successfully against the Supabase database, continue to
`ec2-single-host.md` to stand up the stack against that same database.
