---
id: task-02
phase: phase-1-skeleton
depends_on: [task-01]
status: built
spec: advisordesk-prd.md §4, §4.1
---

# task-02 — Model the PRD §4 schema and migrate it with Alembic

## Goal

All seven §4 tables exist as SQLAlchemy 2.0 models and one reviewed Alembic migration creates them
(vector extension, HNSW index, the three §4.1 FK indexes) in a throwaway test schema. Every service
in phases 2–7 imports these models; the define-once active-row filter starts here.

## Context (read ONLY these)

- `advisordesk-prd.md` §4 (the SQL block is normative — copy names/types/constraints exactly) and
  §4.1 (conventions: uuid PKs, timestamps, is_deleted scope, FK indexes, active-row filter rule).
- `CONVENTIONS.md` §3 (queries helper), §6 (SQLAlchemy 2.0 + Alembic-only DDL), §10 (throwaway-
  schema fixture, skip-by-fixture-name).

## Files

- Create: `apps/api/app/models/{base,users,content,chunks,chat}.py`, `apps/api/app/db.py`,
  `apps/api/app/services/queries.py`
- Create: `apps/api/alembic.ini`, `apps/api/alembic/env.py`,
  `apps/api/alembic/versions/0001_initial_schema.py`
- Create: `apps/api/tests/conftest.py`, `apps/api/tests/test_models_schema.py`
- Modify: `apps/api/pyproject.toml` (runtime deps: `sqlalchemy>=2`, `psycopg[binary]`, `alembic`,
  `pgvector`)

## Interfaces

- **Consumes (task-01):** package layout, gate commands, dev deps.
- **Produces (later tasks rely on — produce exactly):**
  - `app.db`: `make_engine(database_url: str, *, schema: str | None = None) -> Engine`,
    `make_session_factory(engine: Engine) -> sessionmaker[Session]` (`expire_on_commit=False`).
  - `app.models.base`: `Base(DeclarativeBase)`, `uuid_pk()` (server default `gen_random_uuid()`),
    `TimestampMixin` (`created_at`; `updated_at` where mutable), `SoftDeleteMixin`
    (`is_deleted: Mapped[bool]`, not-null default false).
  - ORM classes/tables exactly per §4: `User/users`, `Content/content`, `Tag/tags`,
    `ContentTag/content_tags`, `Chunk/chunks` (`embedding: Vector(1536)`),
    `ChatSession/chat_sessions`, `ChatMessage/chat_messages`.
  - `app.services.queries`: `active_select(model) -> Select` — THE §4.1 active-row filter; every
    later read of users/content/tags goes through it.
  - Test fixtures (in `tests/conftest.py`): `tmp_engine` (creates schema
    `advisordesk_test_<hex8>`, runs `alembic upgrade head` into it, drops on teardown),
    `db_session`; collection hook skipping by fixture name when `TEST_DATABASE_URL` unset.

## Steps (TDD)

- [ ] **Step 1: Write failing schema tests** in `tests/test_models_schema.py` (all via
  `tmp_engine`/`db_session`): inserting a `Content` row yields uuid id + `created_at`/`updated_at`
  set and `is_deleted is False`; `slug` unique constraint raises `IntegrityError` on duplicate;
  `status` check constraint rejects `'bogus'`; `chunks.embedding` accepts a 1536-float vector;
  `active_select(Content)` excludes a row with `is_deleted=True`; inspector sees the HNSW index on
  `chunks` and the three §4.1 FK indexes.
- [ ] **Step 2: Run to see them fail:** `uv run pytest tests/test_models_schema.py -q` with
  `TEST_DATABASE_URL` exported → Expected: FAIL (models don't exist). Without the var → Expected:
  all SKIPPED (fixture-name hook — write that hook first and pin it here).
- [ ] **Step 3: Implement models + db + queries** per Interfaces; mixin composition per table
  exactly per §4.1 (mutable tables get `updated_at`; only users/content/tags get
  `SoftDeleteMixin`); `content.author_id`/`updated_by` nullable FKs to `users.id`.
- [ ] **Step 4: Alembic:** `env.py` targets `Base.metadata` and honors the test schema via
  `-csearch_path`; write `0001_initial_schema.py` by hand-reviewing autogenerate output — it must
  `CREATE EXTENSION IF NOT EXISTS vector`, create all 7 tables, the HNSW index
  (`vector_cosine_ops`), and indexes on `content_tags(tag_id)`, `chunks(content_id)`,
  `chat_messages(session_id, created_at)`.
- [ ] **Step 5: Run to PASS:** `uv run pytest tests/test_models_schema.py -q` → all passed (with
  the var set).
- [ ] **Step 6: Gates → commit:**
  `feat(api): sqlalchemy models + alembic initial schema (phase-1 task-02)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=postgresql://... uv run pytest tests/test_models_schema.py -q   # all passed
uv run pytest tests/test_models_schema.py -q                                       # all skipped (no URL)
uv run alembic history                                                             # exactly 0001
uv run ruff check . && uv run mypy && uv run lint-imports                          # clean
```

## Acceptance

- The migrated schema matches PRD §4 byte-for-byte on names/types/constraints (unique slugs
  spanning deleted rows; check constraints; nullable actor FKs; §4.1 index set).
- `active_select` is the only soft-delete filter in the codebase (grep for `is_deleted ==` hits
  `queries.py` and tests only).
- DB tests run for real when `TEST_DATABASE_URL` is set and skip visibly when not.
- `app.models` remains a pure leaf (lint-imports still 4/4 kept).
