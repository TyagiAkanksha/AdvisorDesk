---
id: hy-t08
phase: hygiene-2026-09
depends_on: []
status: done
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: sonnet
---

# Task 08 — `test_oauth_discovery.py`: isolate the "default `Settings()`" test from the process env

## Goal

Close the t13 Minor (Opus): "`tests/test_oauth_discovery.py:109` builds a bare `Settings()`
(CONVENTIONS §10 — only fails when `MCP_HTTP_ENABLED` is exported into the process env; CI is
unaffected)". The test `test_discovery_available_without_mcp_enabled` deliberately exercises
the zero-env-var defaults (`mcp_http_enabled is False`, issuer `http://localhost:8000`), but
reads whatever the developer's shell exports — it has already failed once in this repo's
history when a `source .env` leaked `MCP_HTTP_ENABLED=true`. Strip the two env vars the test
depends on with a `monkeypatch` fixture, the idiom `tests/test_config.py::clean_env` already
uses.

## Context (read ONLY these)

- `apps/api/tests/test_oauth_discovery.py` — the whole file (≈ 150 lines); the target test is
  `test_discovery_available_without_mcp_enabled` (line ≈ 107 at the time of writing).
- `apps/api/tests/test_config.py` lines ≈ 20–50 — `_ENV_ROSTER` + the `clean_env` fixture idiom.
- `apps/api/app/config.py` — `Settings` fields `mcp_http_enabled` (default `False`) and
  `oauth_issuer_url` (default `"http://localhost:8000"`); pydantic-settings reads env vars
  case-insensitively by field name.
- `CONVENTIONS.md` §10 (tests) and §5 (`Settings()` must succeed with zero env vars).

## Files

**Modify**
- `apps/api/tests/test_oauth_discovery.py`

## Interfaces

```python
# tests/test_oauth_discovery.py — new module-level fixture, placed above the first test
import pytest  # add to the imports (keep `from __future__ import annotations` first)

_DISCOVERY_ENV = ["MCP_HTTP_ENABLED", "OAUTH_ISSUER_URL"]


@pytest.fixture
def clean_discovery_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the env vars this file's default-`Settings()` test depends on (CONVENTIONS §10).

    hygiene t08 (p8 t13 minor): `test_discovery_available_without_mcp_enabled` asserts the
    zero-env-var defaults; a developer shell exporting `MCP_HTTP_ENABLED=true` (or a custom
    issuer) made it fail for reasons unrelated to the code under test.
    """
    for name in _DISCOVERY_ENV:
        monkeypatch.delenv(name, raising=False)
```

```python
def test_discovery_available_without_mcp_enabled(clean_discovery_env: None) -> None:
    """Default `Settings()` (MCP disabled) still serves both docs, at the default issuer."""
    settings = Settings()
    …body unchanged…
```

## Steps

- [ ] **Step 1 (test-author, RED evidence — no new test file):** from `apps/api`, run
  `MCP_HTTP_ENABLED=true uv run pytest tests/test_oauth_discovery.py::test_discovery_available_without_mcp_enabled -q`
  (one-shot env prefix — do **not** `export` it and never `source .env`). Expected: **FAILED**
  on `assert settings.mcp_http_enabled is False`. Paste the failure line. Then run the same
  command without the prefix → PASSED. That pair is the RED evidence: the test's outcome
  depends on the shell, which is the defect.
- [ ] **Step 2 (implementer, GREEN):** add the fixture and the parameter exactly as in
  Interfaces. Do not change any assertion.
- [ ] **Step 3: run GREEN.** The Step 1 command **with** the `MCP_HTTP_ENABLED=true` prefix now
  PASSES; also `OAUTH_ISSUER_URL=https://elsewhere.example uv run pytest
  tests/test_oauth_discovery.py -q` passes (the other tests in the file pass an explicit
  `oauth_issuer_url` already). Paste both summaries.
- [ ] **Step 4: gates.** `cd apps/api && uv run ruff check . && uv run ruff format --check . &&
  uv run mypy && uv run pytest tests/test_oauth_discovery.py tests/test_config.py -q` (export
  only `TEST_DATABASE_URL` if a DB fixture is needed — these two files need none).
- [ ] **Step 5: commit.** `git commit -m "test(api): isolate the default-Settings discovery test from the shell env (p8 t13 minor)"`

## Acceptance criteria

- `MCP_HTTP_ENABLED=true uv run pytest tests/test_oauth_discovery.py -q` → all pass.
- No assertion changed; `openapi.json` untouched; ruff/mypy clean.

## Report

Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-08-test-author.md` (the RED
pair); implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-08-implementer.md`.
