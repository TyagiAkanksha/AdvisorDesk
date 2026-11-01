---
id: vrf-t01
phase: video-review-fixes
depends_on: []
status: todo
spec: advisordesk-prd.md §6 (MCP tools); MCP spec "Tool annotations" (readOnlyHint/destructiveHint)
review: sonnet
---

# Task 01 — MCP tool annotations (`readOnlyHint` / `destructiveHint`)

## Goal

claude.ai's connector permissions page lists `list_proposals` (and would list any future read
tool) as "needs approval" because our `tools/list` advertises no annotations at all. After this
task every registered tool carries MCP `ToolAnnotations`: the five read tools say
`readOnlyHint: true`, the destructive writes say `destructiveHint: true`, and the committed
`apps/api/mcp-tools.json` shows it. Hosts that honour annotations then run reads without asking.

## Context (read ONLY these)

- `apps/api/app/mcp/tool_spec.py` — `ToolSpec` dataclass (`name`, `description`, `args_model`,
  `handler`), and the module's "imports nothing from `app.mcp`" placement rule.
- `apps/api/app/mcp/runtime.py:191-208` — `list_tool_schemas()` (`{name, description,
  inputSchema}`) and `_ALL_TOOLS`.
- `apps/api/app/mcp/server.py:125-137` — `_handle_list_tools` builds `types.Tool(name=,
  description=, input_schema=)`.
- `apps/api/app/mcp/tools_read.py`, `tools_write.py`, `tools_proposals.py`, `tools_gaps.py` —
  the `ToolSpec(...)` registrations (14 tools).
- `apps/api/scripts/export_mcp_tools.py` — writes `apps/api/mcp-tools.json` (standing gate: any
  tool-schema change regenerates it in the same commit).
- `apps/api/app/agent/llm.py` — where `list_tool_schemas()` output becomes the model's tool
  definitions (around `:82`). The new key must NOT leak into the OpenAI payload.
- `apps/api/tests/test_mcp_read_tools.py` (the "some dict-shaped field besides name/description"
  controller decision), `tests/test_agent_llm_client.py`, `tests/test_agent_llm_arg_repair.py`.
- `CONVENTIONS.md` (gates), `apps/api/pyproject.toml:131-190` (import-linter: `app.mcp` never
  imports `app.routes`/`app.agent`/`app.db`; tool modules keep importing only `tool_spec`).

## Interfaces

```python
# app/mcp/tool_spec.py
@dataclass(frozen=True)
class ToolHints:
    """MCP ToolAnnotations we publish. `read_only=True` tools perform no mutation at all;
    `destructive=True` tools may overwrite or remove data (MCP's own default when a tool is
    not read-only — we state it explicitly so the exported baseline is exact)."""
    read_only: bool = False
    destructive: bool = True

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., dict[str, Any]]
    hints: ToolHints = ToolHints()   # default = conservative: not read-only, destructive
```

Per-tool values (exact):

| tool | read_only | destructive |
|---|---|---|
| search_content, count_content, list_proposals, report_content_gaps, report_weak_queries | True | False |
| delete_content, archive, edit_content, accept_proposal | False | True |
| create_draft, publish, tag_content, propose_content_fix, reject_proposal | False | False |

- `list_tool_schemas()` gains `"annotations": {"readOnlyHint": bool, "destructiveHint": bool}`
  per tool (MCP wire casing). Docstring updated.
- `_handle_list_tools` passes `annotations=types.ToolAnnotations(...)`. The SDK is `mcp>=2.0.0`;
  verify field names first: `uv run python -c "import mcp.types as t; print(list(
  t.ToolAnnotations.model_fields))"` and use whatever casing it prints (snake_case expected,
  matching `input_schema=` already used there).
- `app/agent/llm.py`: whatever maps `list_tool_schemas()` → OpenAI tool definitions must keep
  emitting only `name`/`description`/`parameters`. If it already copies fields explicitly, no
  change; if it forwards the dict, filter.
- `apps/api/mcp-tools.json` regenerated with `uv run python scripts/export_mcp_tools.py`
  (confirm the exact invocation in the script's header).

## Files

**Create** `apps/api/tests/test_mcp_tool_hints.py`.
**Modify** `app/mcp/tool_spec.py`, `app/mcp/runtime.py`, `app/mcp/server.py`, the four tool
modules, `apps/api/mcp-tools.json`, and (only if needed) `app/agent/llm.py`.
**Authorised test amendments**: any existing test that pins the exact key set of a
`list_tool_schemas()` entry or compares `mcp-tools.json` byte-for-byte — list each one touched in
the report with file:line.

## Steps

RED (test-author):
- [ ] `tests/test_mcp_tool_hints.py`: (1) every entry of `list_tool_schemas()` has
  `annotations` with boolean `readOnlyHint` and `destructiveHint`; (2) the table above holds
  exactly (parametrised over all 14 names; a tool missing from the table fails the test);
  (3) `tools/list` through `app.mcp.server` (reuse the existing server/list-tools test fixture —
  find it with `grep -rn "_handle_list_tools\|tools/list" tests/`) yields
  `annotations.read_only_hint is True` for `search_content` and `destructive_hint is True` for
  `delete_content`; (4) the OpenAI tool definitions built in `app/agent/llm.py` for the model
  contain no `annotations` key (extend the existing payload-shape test in
  `test_agent_llm_client.py` if one exists, else add here).
- [ ] Run `uv run pytest tests/test_mcp_tool_hints.py -q` → the new tests FAIL (AttributeError /
  KeyError), nothing else in the suite changes. Record the output in the report.

GREEN (implementer):
- [ ] Implement the Interfaces; regenerate `mcp-tools.json`; `uv run pytest -q` all green.
- [ ] Gates: `uv run mypy`, `uv run ruff check --no-cache`, `uv run ruff format --check`,
  import-linter (the command CONVENTIONS.md names) — paste real output.
- [ ] Commit message: `feat(mcp): advertise readOnly/destructive tool annotations (vrf t01)`.
  Stage only the files you changed (`git add <paths>`), never `git add -A`.

## Acceptance

`uv run python -c "from app.mcp.runtime import list_tool_schemas as l; print({t['name']:
t['annotations'] for t in l()})"` prints the table; the committed `mcp-tools.json` diff shows
exactly one new `annotations` object per tool and nothing else.
