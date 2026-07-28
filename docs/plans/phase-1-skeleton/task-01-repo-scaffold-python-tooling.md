---
id: task-01
phase: phase-1-skeleton
depends_on: []
status: planned
spec: advisordesk-prd.md §3.1, §9, §11
---

# task-01 — Scaffold the monorepo and stand up the Python tooling gates

## Goal

The PRD §3.1 directory tree exists, `apps/api` is a uv project whose five gate commands all run
clean on an empty-but-real package, and the two gates-as-tests files exist so every later task
inherits a working quality harness. Everything in phases 1–7 builds inside this skeleton.

## Context (read ONLY these)

- `advisordesk-prd.md` §3.1 — the exact directory layout (normative).
- `advisordesk-prd.md` §9 "Config" — the 12-var env roster for `.env.example`.
- `CONVENTIONS.md` §2 (layering + import-linter contracts), §9 (tooling config values), §10
  (test rules, gates-as-tests).

## Files

- Create: `apps/api/pyproject.toml`, `apps/api/app/__init__.py`, `apps/api/app/main.py` (stub),
  and empty packages `apps/api/app/{routes,services,mcp,rag,agent,auth,models}/__init__.py`
- Create: `apps/api/tests/test_lint_clean.py`, `apps/api/tests/test_import_contracts.py`
- Create: `.env.example`, `.gitignore`, `README.md` (stub with "Implementation notes" section),
  `SUGGESTIONS.md` (stub), `seed/sample_content/.gitkeep`, `infra/.gitkeep`

## Interfaces

- **Consumes:** nothing (first task).
- **Produces (later tasks rely on — produce exactly):**
  - Package layout `app.routes` / `app.services` / `app.mcp` / `app.rag` / `app.agent` /
    `app.auth` / `app.models` (CONVENTIONS.md §2 table).
  - Import-linter contracts in `apps/api/pyproject.toml`: (1) `app.models` pure leaf,
    (2) `app.services` imports only `app.models`+`app.config`, (3) `app.routes` ⟂ `app.mcp`
    independence, (4) nothing imports `app.main`.
  - The five gate commands exactly as in the phase INDEX (all later Verify blocks reuse them).
  - Dev deps available to all tasks: `pytest`, `httpx`, `ruff`, `mypy`, `import-linter`.
  - `.env.example` var names: `OPENAI_API_KEY`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`,
    `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, `ADMIN_EMAILS`, `CORS_ORIGINS`,
    `SIMILARITY_THRESHOLD`, `RATE_LIMIT_PER_MIN`, `RATE_LIMIT_PER_DAY`, `SESSION_CREATE_PER_DAY`,
    `MCP_HTTP_ENABLED` (+ `TEST_DATABASE_URL`, dev-only, commented).

## Steps (TDD)

- [ ] **Step 1: Write the two failing gate-tests first.**
  `tests/test_lint_clean.py`: subprocess `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy` (no path args), each asserting `returncode == 0` with stdout in the failure
  message. `tests/test_import_contracts.py`: subprocess `uv run lint-imports`, asserting exit 0.
- [ ] **Step 2: Run them to see them fail** (no pyproject yet):
  `cd apps/api && uv run pytest -q` → Expected: command fails — no pyproject/environment yet.
- [ ] **Step 3: Create `pyproject.toml`** with `[project]` (name `advisordesk-api`,
  `requires-python = ">=3.11"`, empty runtime deps for now), dev group (`pytest`, `httpx`,
  `ruff`, `mypy`, `import-linter`), and the tool config verbatim from CONVENTIONS.md §9:
  ruff line 100 + `E,F,I,UP,B` + the `extend-immutable-calls` FastAPI block; mypy
  `strict = true`, `files = ["app"]`; `[tool.importlinter]` `root_package = "app"` with the four
  §2 contracts; `[tool.pytest.ini_options]` `testpaths = ["tests"]`.
- [ ] **Step 4: Create the package skeleton** (`app/__init__.py` + the seven subpackages, each
  `__init__.py` with `from __future__ import annotations` and a one-line docstring; `app/main.py`
  stub docstring only).
- [ ] **Step 5: Run the gates to see them pass:** `uv sync && uv run pytest -q` → Expected:
  2 passed. Then the other four gate commands → Expected: all exit 0.
- [ ] **Step 6: Contract-verification ritual (CONVENTIONS.md §2):** add a deliberate
  `from app.routes import x` inside `app/models/__init__.py` → `uv run lint-imports` exits 1 and
  `test_import_contracts` fails → revert → both green again.
- [ ] **Step 7: Repo-root files:** `.gitignore` (`.env`, `*.env`, `!.env.example`, `.venv/`,
  `node_modules/`, `.next/`, `__pycache__/`, `coverage/`), `.env.example` (all vars above, each
  with a one-line comment + PRD default), `README.md` stub (project one-liner, dev quickstart
  placeholder, empty "## Implementation notes" section), `SUGGESTIONS.md` stub, `seed/`, `infra/`.
- [ ] **Step 8: Gates (phase INDEX) → commit:**
  `feat(api): monorepo scaffold + python tooling gates (phase-1 task-01)`

## Verify

```bash
cd apps/api
uv run ruff check . && uv run ruff format --check .   # exit 0, no output
uv run mypy                                            # Success: no issues found
uv run lint-imports                                    # Contracts: 4 kept, 0 broken
uv run pytest -q                                       # 2 passed
git status --short                                     # no .env, no stray files
```

## Acceptance

- The §3.1 tree exists exactly (admin/client folders may be empty until task-04).
- All five Python gates green; the two gates-as-tests fail when lint/typing/contracts break
  (proven once via the ritual in Step 6).
- `.env.example` lists all 12 §9 vars + `TEST_DATABASE_URL`; `.gitignore` re-allows only
  `.env.example`.
- README has an empty "Implementation notes" section; SUGGESTIONS.md exists.
