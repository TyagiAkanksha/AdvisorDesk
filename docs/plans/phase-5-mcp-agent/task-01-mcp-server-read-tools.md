---
id: task-01
phase: phase-5-mcp-agent
depends_on: [phase-2-auth-cms-crud/task-02, phase-3-publish-client-content/task-02]
status: planned
spec: advisordesk-prd.md §3, §6
---

# task-01 — MCP server foundation and the read tools

## Goal

The MCP server runs inside the FastAPI process with the tool-registration pattern every tool
follows (Pydantic args → service call with session + actor → structured JSON), an in-process
invocation seam the agent loop uses, the §3 exposure rule pinned, and the first two tools
(`search_content`, `count_content`) proving the pattern. The committed `mcp-tools.json` baseline
starts here.

## Context (read ONLY these)

- `advisordesk-prd.md` §3 (in-process rule, `MCP_HTTP_ENABLED` exposure rule, shared services)
  and §6 (tool table rows for `search_content`/`count_content`; "not vector search").
- `CONVENTIONS.md` §2 (mcp ⟂ routes contract), §8 (baseline determinism).
- `app/services/content.py` / `tags.py` / `stats.py` — the functions to wrap.

## Files

- Create: `apps/api/app/mcp/{server.py,runtime.py,tools_read.py}`
- Create: `apps/api/scripts/export_mcp_tools.py`, `apps/api/mcp-tools.json` (generated, committed)
- Create: `apps/api/tests/{test_mcp_read_tools.py,test_mcp_exposure.py}`
- Modify: `apps/api/app/factory.py` (mount-when-enabled wiring), `apps/api/pyproject.toml`
  (runtime dep: `mcp`)

## Interfaces

- **Consumes:** services (p2-t02), pipeline state (p3-t02), `require_admin` (p2-t01, for the
  HTTP-exposure path), `AdminPrincipal`.
- **Produces (later tasks rely on — produce exactly):**
  - `app.mcp.server`: `build_mcp_server() -> Server` — registers every tool module; single
    registration point.
  - `app.mcp.runtime`: `call_tool(name: str, arguments: dict, *, session: Session,
    actor_id: uuid.UUID) -> dict` — validates via the tool's Pydantic args model, executes,
    returns the tool's JSON payload; raises `ToolNotFoundError` / `ToolInputError` (add to the
    error family). **This is the seam the agent loop (task-03) calls — no HTTP involved.**
    Also `list_tool_schemas() -> list[dict]` (name, description, JSON schema) — fed to the agent
    loop (task-03) AND the baseline export.
  - Tools (names/args/returns exactly per §6): `search_content(q?, status?, tag?, limit=10)` →
    `{items:[{id,title,slug,status,tags}], count}` (metadata search over title/tag/status — NOT
    vector search); `count_content(status?, tag?)` → `{count}`. Both read through
    `active_select` (soft-deleted invisible, §6 footer).
  - Exposure wiring: `factory.py` mounts the MCP HTTP transport only when
    `settings.mcp_http_enabled`, and behind `require_admin`.
  - `scripts/export_mcp_tools.py` → deterministic `apps/api/mcp-tools.json` (sorted, indent 2).
    **Standing gate from now on: tool-schema changes regenerate it in the same commit.**

## Steps (TDD)

- [ ] **Step 1: Failing read-tool tests** (`test_mcp_read_tools.py`, via `call_tool` — no HTTP):
  `search_content` finds by title substring, filters by status+tag, respects `limit`, excludes
  soft-deleted (**§6 pin**); `count_content` matches seeded matrix counts and excludes
  soft-deleted; bad args (`limit="x"`) → `ToolInputError` with field detail; unknown tool →
  `ToolNotFoundError`. One happy + one failure per tool (§9).
- [ ] **Step 2:** run → FAIL. **Step 3: implement** server.py/runtime.py/tools_read.py.
  **Step 4:** run → PASS.
- [ ] **Step 5: Failing exposure tests** (`test_mcp_exposure.py`): default settings → the MCP
  HTTP route does not exist (404); `mcp_http_enabled=True` → route exists, 401 without an admin
  session, 200-class with one (**§3 pin, both states**).
- [ ] **Step 6:** run → FAIL → wire factory → PASS.
- [ ] **Step 7: Baseline:** generate + commit `mcp-tools.json`.
- [ ] **Step 8: Gates → commit:**
  `feat(api): in-process MCP server + read tools + baseline (phase-5 task-01)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_mcp_read_tools.py tests/test_mcp_exposure.py -q
uv run python scripts/export_mcp_tools.py && git diff --exit-code mcp-tools.json
uv run lint-imports    # routes ⟂ mcp contract still kept
```

## Acceptance

- Both read tools behave per §6 via the in-process seam; schema list feeds the loop and the
  committed baseline.
- Exposure rule pinned in both states; write surface unreachable unauthenticated (§3).
- `app.mcp` imports services only — never `app.routes` (contract kept).
