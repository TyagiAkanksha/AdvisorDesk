# AdvisorDesk — Python Conventions (apps/api)

**Scope:** Python only — the FastAPI backend at `apps/api/`. Frontend rules live in
[`docs/FRONTEND-CONVENTIONS.md`](docs/FRONTEND-CONVENTIONS.md). The PRD
([`advisordesk-prd.md`](advisordesk-prd.md)) wins on any conflict.

These rules are distilled from the reference project (`reference_project/span-agent/`) and adapted
to AdvisorDesk's PRD §3.1 layout. Two deliberate deviations from the reference are recorded in §6
(Alembic) and in `docs/FRONTEND-CONVENTIONS.md` §2 (Material UI).

---

## 1. House style

- Every shipped `.py` file begins with `from __future__ import annotations`.
- Full type annotations on all public functions, methods, and module-level assignments. Private
  `_`-prefixed helpers may omit them when obvious.
- Docstring on every public symbol: one-sentence summary, blank line, elaboration;
  `Args:`/`Returns:`/`Raises:` for non-trivial signatures. Docstrings explain **why**, and cite the
  PRD section that mandates the behavior (e.g. "PRD §4.1: slugs are never reused").
- Prefer `collections.abc` types (`Callable`, `Sequence`, `Mapping`, `Iterator`) over concrete
  types in annotations.
- No bare `except Exception` and no `raise Exception(...)` — use the typed family (§4).
- Keep files small; each function serves **one purpose**. A module accumulating unrelated
  responsibilities is a split-smell — raise it rather than growing it.

## 2. Layout & layering (import-linter-enforced)

PRD §3.1 fixes the package layout:

```
apps/api/app/
  main.py        # wiring ONLY (engine, session factory, create_app) — nothing imports main
  factory.py     # create_app()
  config.py      # pydantic-settings Settings
  db.py          # engine/session-factory constructors
  routes/        # FastAPI routers + register_error_handlers + SSE utilities
  services/      # business logic — the ONLY layer that touches the ORM (routes AND mcp use it)
  mcp/           # MCP server + tool definitions (wraps services; PRD §3)
  rag/           # chunking, embeddings, pipeline, retrieval, synthesis
  agent/         # agent loop calling MCP tools in-process
  auth/          # Google OAuth, session cookies, require_admin
  models/        # SQLAlchemy ORM models + Pydantic DTO schemas (models/schemas/)
```

Dependency direction (each layer may import the ones after it, never before):

| Layer | May import |
|---|---|
| `routes/` | `agent/` (see rule 3), plus everything the next row lists |
| `mcp/`, `agent/` | `services/`, `rag/`, `auth/`, `models/`, `config` — and `agent/` imports `mcp/` (its tool interface) |
| `rag/`, `auth/` | `services/`, `models/`, `config` |
| `services/` | `models/`, `config` |
| `db` | `config` at most (engine/session factories take the URL as a parameter) |
| `models/` | (stdlib + third-party only) |

Only `main.py`, Alembic's `env.py`, and tests import `db`; it is wiring, not a request-path layer.

Hard rules, declared as import-linter contracts in `apps/api/pyproject.toml` and enforced by
`tests/test_import_contracts.py`:

1. `app.models` imports no other `app.*` package (pure leaf).
2. `app.services` imports only `app.models` and `app.config` from `app.*`.
3. `app.mcp` never imports `app.routes` — tools must stay ignorant of HTTP machinery. *(Owner
   ratification, phase-5 checkpoint 2026-08-02: this rule was originally bidirectional "sibling
   independence". Phase 5's agent loop made the chain `routes → agent → mcp` legal by necessity —
   `/agent/chat` calls `run_agent`, which calls MCP tools through `app.mcp.runtime.call_tool` —
   so the enforced contract was narrowed to the direction that actually protects the
   architecture. The PRD §3 "no duplicated business logic" rule is untouched: both surfaces
   still share `app.services`.)*
4. Nothing imports `app.main`.

**Contract-verification ritual** (run once when adding a contract): inject a deliberately violating
import, confirm `lint-imports` exits 1, revert, confirm exit 0. A contract that has never failed is
untested.

**No tight coupling between modules — no exceptions.** The contracts above are the enforcement,
not the boundary of the rule: if two modules can only change together, restructure them even when
no contract forbids the import.

## 3. Services

- Plain functions, **session-first**: `def create_draft(session: Session, *, title: str, ...)`.
  Never hold a module-level session or engine.
- Services `flush()` to assign ids and surface constraint errors eagerly, but **never `commit()` or
  `rollback()`**. The transaction boundary belongs to the caller — in HTTP requests, the
  `get_session` dependency commits on success and rolls back on error; tests own their own
  transactions.
- The acting admin is passed explicitly (`actor_id: uuid.UUID | None`) and stamped into
  `author_id`/`updated_by` per PRD §4.1 — never read from any global.
- Soft-delete filtering is defined **once**: `app/services/queries.py::active_select(model)`
  returns a `Select` pre-filtered on `is_deleted == False`. Every read of a soft-deletable model
  goes through it. An ad-hoc `.where(X.is_deleted == False)` elsewhere is a review-blocking
  defect — a missed filter is a data leak (PRD §4.1), and a test pins the helper's behavior.
- `updated_at` is maintained by the service layer on every write (PRD §4.1). No DB triggers.

## 4. Errors

- Typed exception family in `app/services/errors.py` — e.g. `NotFoundError`, `ConflictError`,
  `AuthRequiredError`, `RateLimitedError`, `EmbeddingFailedError`. Services raise these; they never
  construct HTTP responses.
- `app/routes/errors.py::register_error_handlers(app)` maps each exception type to a status code
  and the PRD §9 envelope `{"error": {"code", "message"}}` exactly once. The same envelope is used
  inside SSE `error` events.
- **Routes contain no `try/except`.** Rollback happens in the session dependency; mapping happens
  in the registered handlers. Carve-out: the outermost SSE stream generator (e.g.
  `app.routes.public_routes._generate_chat_stream`) MAY catch `Exception` solely to convert an
  in-stream failure into the §9 `error` event — raw detail logged, never enveloped — because by
  the time it can fail a 200 has already been sent and the registered handlers can no longer run;
  nothing broader than that one generator-body catch is exempted by this carve-out (phase-4
  task-02 review round 1, finding C-1; phase-5's `/agent/chat` reuses the identical shape).

## 5. App construction

- `app/factory.py::create_app(session_factory=None, settings=None) -> FastAPI` — no module-level
  globals; everything request-scoped lives on `app.state` and is read back through dependencies
  (`get_session`, `get_settings`).
- `create_app()` must succeed **with no database and no env vars** — this is what makes the
  OpenAPI baseline export (§8) and DB-less tests possible.
- `app/main.py` is the only wiring point: configure logging, load settings, build engine + session
  factory, call `create_app(...)`, expose `app`. Nothing imports `main`.
- Every route declares an explicit, stable, unique `operation_id`. The frontends'
  `openapi-typescript` codegen keys on them; renaming one is a breaking wire change (§8 gate).
- All routes live under `/api/v1` (PRD §5). Health endpoint: `GET /api/v1/healthz` — no auth, no
  DB touch, so container healthchecks can probe the bare process.

## 6. SQLAlchemy & migrations

- SQLAlchemy **2.0 style only**: `DeclarativeBase`, `Mapped[T]`, `mapped_column()`. The 1.x
  `Column()` style is banned in new code.
- Shared column helpers in `app/models/base.py`: `uuid_pk()` (server-side `gen_random_uuid()`),
  `TimestampMixin` (`created_at`, and `updated_at` on mutable tables), `SoftDeleteMixin`
  (`is_deleted`, PRD §4.1 scope: users/content/tags only).
- **Alembic is the only DDL path.** No `create_all()` at startup, ever. This deviates from the
  reference project deliberately: its README documents a production `500 UndefinedColumn` incident
  caused by startup-DDL drift ("green tests can hide a broken prod"). Migrations run explicitly
  (`uv run alembic upgrade head`); autogenerate output is always hand-reviewed before commit.
- Table/column shapes come verbatim from PRD §4; the §4.1 conventions (uuid PKs, timestamptz,
  is_deleted scope, FK indexes) are normative.

## 7. Config & secrets

- `app/config.py::Settings(BaseSettings)` (pydantic-settings) is the single config surface — the
  full PRD §9 env roster with PRD defaults (`SIMILARITY_THRESHOLD=0.35`, `RATE_LIMIT_PER_MIN=10`,
  `RATE_LIMIT_PER_DAY=50`, `SESSION_CREATE_PER_DAY=20`, `MCP_HTTP_ENABLED=false`, ...).
- Secrets only via env. Tracked file: `.env.example` (every var, commented). Real `.env` files are
  gitignored. **Never commit secrets.**

## 8. Wire-surface baselines

- `apps/api/openapi.json` — dumped by `apps/api/scripts/export_openapi.py` from a DB-less
  `create_app()`; committed.
- `apps/api/mcp-tools.json` — dumped by `apps/api/scripts/export_mcp_tools.py` (tool names +
  JSON schemas); committed once the MCP server exists.
- Both are written deterministically (`json.dumps(..., indent=2, sort_keys=True)`, `\n` newlines)
  so `git diff --exit-code` over them proves the wire surface did not move.
- **Gate:** any commit that changes a route, DTO, or tool schema regenerates the affected baseline
  (and the frontends' codegen, for OpenAPI) **in the same commit**.

## 9. Tooling

Package manager: **uv**; single project at `apps/api` (`requires-python = ">=3.11"`). Runtime
dependencies = exactly what shipped code imports; dev tools (`pytest`, `ruff`, `mypy`,
`import-linter`) live in the dev dependency group, never in runtime deps. `httpx` moved to a
runtime dependency in phase-2 task-01 (`app.auth.oauth.HttpxGoogleOAuthClient` talks to Google's
real OAuth2 endpoints over it) — it is also `starlette.testclient.TestClient`'s driver, but that
is no longer why it ships; removing it would break login, not just tests.

Ruff: `line-length = 100`, `select = ["E", "F", "I", "UP", "B"]`, plus the FastAPI DI exemption
(the configuration FastAPI's own docs recommend):

```toml
[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = ["fastapi.Depends", "fastapi.Query", "fastapi.Header",
                          "fastapi.Path", "fastapi.Body"]
```

Mypy: `strict = true` over an explicit `files = ["app"]` list. A package is either listed
(strict-clean) or not present — never partially typed. Third-party gaps get a targeted
`ignore_missing_imports` override with a comment naming the typed wrapper that contains them.
`tests/` and `scripts/` are **deliberately out of the mypy gate's scope** — the suite duck-types
fakes and passes convenience values (e.g. plain strings for `SecretStr` fields) that strict typing
would reject without any runtime benefit. A bare `mypy .` therefore reports errors in those trees;
that is expected, not a regression. The canonical gate is `uv run mypy` (the `files = ["app"]`
list), and only `app/` must be strict-clean.

The gate commands (module form, run from `apps/api/`):

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest -q
```

All five must be clean before every commit that touches `apps/api`. Additionally, run
`uv run mypy` **after every implementation or significant change** — not only at the commit gate;
type drift caught immediately is cheap, caught at commit time it hides which change caused it.

## 10. Tests

- **Tests are part of the task. No test means the task is not complete.** The unit-test baseline
  grows with every task; a change without covering tests does not merge.
- **TDD is mandatory:** the failing test (RED) exists and is run before the implementation
  (GREEN); both runs are recorded as evidence in the task report.
- **Test-author is a separate agent from the implementer.** A task's failing tests are written by
  the test-author agent from the task brief; the implementer makes them pass and may add tests,
  but may not weaken, modify, or delete the authored tests without controller approval.
- **Simulate actual usage, don't mock the interaction.** API tests drive the real entry points —
  `TestClient` over the HTTP surface, real throwaway-schema DB fixtures — and assert observable
  behavior. Mock ONLY true external seams (OpenAI, Google OAuth, the clock), never internal
  collaborators; a test that exercises a mock of our own code verifies nothing.
- Layout: `apps/api/tests/`, **no `__init__.py`** anywhere under tests (conftest scoping), unique
  test-file basenames across the whole tree.
- DB tests use a **throwaway schema per test**: the fixture creates `advisordesk_test_<hex>`, runs
  `alembic upgrade head` into it through the production engine factory, yields, drops it. When
  `TEST_DATABASE_URL` is unset, DB-fixture tests are skipped **by fixture name** in a collection
  hook — and a skip is recorded, never counted as a pass. DB tests must actually run when the env
  var is present; a silently-skipped gate is a gap.
- Gates-as-tests: `tests/test_lint_clean.py` (subprocess ruff + mypy, no path args so it stays
  aligned with the canonical config) and `tests/test_import_contracts.py` (subprocess
  `lint-imports`) make CI = `pytest`.
- Test what the PRD names first (§9's explicit list: chunking, lifecycle + rollback, similarity
  pin, soft-delete visibility, tag reactivation, slug permanence, MCP happy+failure, smoke), then
  endpoint status codes.
- External seams are injectable, never monkeypatched at a distance: `session_factory` into
  `create_app`, `Embedder`/LLM protocols into rag modules, clock into the rate limiter, OAuth
  client into auth.

## 11. Docker & local dev

- Per-service images: multi-stage uv build for the API (builder installs into a venv; slim runtime
  copies the venv, runs as a non-root user, stdlib-only `HEALTHCHECK` against `/api/v1/healthz`).
- `infra/docker-compose.yml` publishes ports on loopback only. The optional Postgres
  (`pgvector/pgvector:pg16`) sits behind `--profile local-db` (PRD §9); Supabase stays the default
  and deployed target.
- Migrations are invoked explicitly (`docker compose run --rm api uv run alembic upgrade head`),
  never at container startup.

## 12. Commits

- Conventional Commits with a scope: `feat(api): ...`, `fix(admin): ...`, `docs(plans): ...`,
  `chore(infra): ...`; scopes: `api` / `admin` / `client` / `infra` / `seed` / `plans` / `docs`.
- Reference the task id in a trailing parenthetical: `feat(api): content CRUD services (phase-2
  task-02)`.
- **Path-scoped `git add` only** — never `git add .` / `-A`. Never stage `.env` or secrets.

## 13. AI-assisted workflow

The working rules for AI agents in this repo — plan-mode-first, small task-sized dispatches,
test-author/implementer/reviewer agent separation, Sonnet-first model policy, fresh agent per
task, review-is-never-a-rubber-stamp — live in [`CLAUDE.md`](CLAUDE.md) (single source; not
restated here).
