---
id: task-03
phase: phase-1-skeleton
depends_on: [task-02]
status: planned
spec: advisordesk-prd.md §5, §9
---

# task-03 — App factory, typed config, error envelope, health endpoint

## Goal

`create_app()` builds a FastAPI app with no DB and no env vars; `Settings` exposes the full §9 env
roster with PRD defaults; the typed error family maps to the §9 `{error:{code,message}}` envelope
in exactly one place; `GET /api/v1/healthz` answers. Every route task in phases 2–7 plugs into
these names, and the OpenAPI baseline export exists for task-04's codegen.

## Context (read ONLY these)

- `advisordesk-prd.md` §5 intro (`/api/v1`, envelope reuse in SSE), §9 (Config roster + defaults,
  Error handling, CORS).
- `CONVENTIONS.md` §4 (errors), §5 (app construction, operation_id rule), §7 (config), §8
  (openapi baseline determinism).

## Files

- Create: `apps/api/app/config.py`, `apps/api/app/factory.py`, `apps/api/app/routes/errors.py`,
  `apps/api/app/routes/deps.py`, `apps/api/app/routes/health_routes.py`
- Create: `apps/api/scripts/export_openapi.py`, `apps/api/openapi.json` (generated, committed)
- Create: `apps/api/tests/test_config.py`, `apps/api/tests/test_app_factory.py`
- Modify: `apps/api/app/main.py` (real wiring), `apps/api/pyproject.toml` (runtime deps:
  `fastapi`, `uvicorn`, `pydantic-settings`)

## Interfaces

- **Consumes (task-02):** `make_engine`, `make_session_factory`.
- **Produces (later tasks rely on — produce exactly):**
  - `app.config`: `class Settings(BaseSettings)` with fields for all §9 vars, PRD defaults
    (`similarity_threshold=0.35`, `rate_limit_per_min=10`, `rate_limit_per_day=50`,
    `session_create_per_day=20`, `mcp_http_enabled=False`), `cors_origins` parsed from
    comma-separated env.
  - `app.factory`: `create_app(session_factory=None, settings=None) -> FastAPI` — CORS middleware,
    error handlers registered, routers included, state stored on `app.state.session_factory` /
    `app.state.settings`.
  - `app.routes.deps`: `get_session(request) -> Iterator[Session]` (commit on success, rollback on
    exception, close always), `get_settings(request) -> Settings`.
  - `app.services.errors` (created here, extended later): `NotFoundError`, `ConflictError`,
    `AuthRequiredError`, `RateLimitedError`, `EmbeddingFailedError` — mapped in
    `app.routes.errors::register_error_handlers(app)` to 404/409/401/429/502 with the §9 envelope.
  - Route: `GET /api/v1/healthz`, `operation_id="healthz"`, `{"status":"ok"}`, no auth, no DB.
  - `scripts/export_openapi.py` → deterministic committed `apps/api/openapi.json` (sort_keys,
    indent 2, trailing newline).

## Steps (TDD)

- [ ] **Step 1: Failing config tests** (`tests/test_config.py`): defaults match the PRD values
  above with an empty env; `CORS_ORIGINS="http://a,http://b"` parses to a 2-item list.
- [ ] **Step 2:** `uv run pytest tests/test_config.py -q` → FAIL (no `app.config`).
- [ ] **Step 3: Implement `Settings`** → run to PASS.
- [ ] **Step 4: Failing factory tests** (`tests/test_app_factory.py`, `TestClient`, no DB):
  `create_app()` with no args succeeds; `GET /api/v1/healthz` → 200 `{"status":"ok"}`; a probe
  route raising `NotFoundError` (registered inside the test) → 404 with exact envelope
  `{"error":{"code":"not_found","message":...}}`; CORS preflight from a configured origin gets the
  ACAO header, an unlisted origin does not; `create_app().openapi()` contains
  `operation_id "healthz"`.
- [ ] **Step 5:** run → FAIL; **implement** `errors.py` + `factory.py` + `deps.py` +
  `health_routes.py`; run → PASS.
- [ ] **Step 6: Wire `main.py`** (settings → engine → session factory → `create_app`); write
  `scripts/export_openapi.py`; generate and commit `openapi.json`.
- [ ] **Step 7: Gates → commit:**
  `feat(api): app factory, settings, error envelope, healthz (phase-1 task-03)`

## Verify

```bash
cd apps/api
uv run pytest tests/test_config.py tests/test_app_factory.py -q    # all passed, no DB needed
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json   # deterministic
uv run uvicorn app.main:app --port 8000 &   # then:
curl -s localhost:8000/api/v1/healthz        # {"status":"ok"}
```

## Acceptance

- `create_app()` works with zero env/DB; all state flows through `app.state` + dependencies —
  `grep -rn "^engine\|^session" app/` shows no module-level handles outside `main.py`.
- Envelope shape is pinned by test and produced only by `register_error_handlers`.
- `openapi.json` committed and reproducible; healthz reachable under `/api/v1`.
