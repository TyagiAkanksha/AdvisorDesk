---
id: task-02
phase: phase-5-mcp-agent
depends_on: [task-01]
status: planned
spec: advisordesk-prd.md §6, §4.1
---

# task-02 — The six MCP write tools

## Goal

`create_draft`, `edit_content`, `delete_content`, `tag_content`, `publish`, and `archive` exist as
thin Pydantic-validated wrappers over the phase-2/3 services — same behavior as the REST routes by
construction (PRD §3), actor-stamped, soft-delete-aware. With task-01's pair, all 8 core §6 tools
are live for the agent loop.

## Context (read ONLY these)

- `advisordesk-prd.md` §6 tool table (each row is the contract: args, behavior, returns) + the
  tools footer (non-deleted rows only; actor recording).
- `app/mcp/{runtime.py,tools_read.py}` (task-01) — follow the registration pattern exactly.
- `app/services/content.py` / `tags.py` — wrap, never re-implement.

## Files

- Create: `apps/api/app/mcp/tools_write.py`
- Create: `apps/api/tests/test_mcp_write_tools.py`
- Modify: `apps/api/app/mcp/server.py` (register), `apps/api/mcp-tools.json` (regenerate)

## Interfaces

- **Consumes:** `call_tool` seam + registration pattern (task-01); services with the real
  pipeline (p3-t02).
- **Produces (later tasks rely on — produce exactly, per §6):**
  - `create_draft(title: str, body_md: str = "", tags: list[str] = [])` → `{id, slug}` — always
    status `draft`; missing tags created (soft-deleted names reactivated, §4.1).
  - `edit_content(content_id: str, title?, body_md?, tags?)` → `{id, slug, status}` — partial
    update; re-embeds iff published (via the pipeline); slug unchanged.
  - `delete_content(content_id: str)` → `{deleted: true}` — soft delete: tombstone + chunk
    removal in one transaction (§4).
  - `tag_content(content_id: str, add: list[str] = [], remove: list[str] = [])` →
    `{id, tags}` — `add` creates/reactivates missing tags.
  - `publish(content_id: str)` → `{id, status, published_at}` — the full §4 publish transaction.
  - `archive(content_id: str)` → `{id, status}` — status→archived + chunk removal.
  - All six: a `content_id` addressing a missing OR soft-deleted item → structured not-found
    tool error (§6 footer); the acting admin's id is stamped into `author_id`/`updated_by`
    (§4.1) — `call_tool`'s `actor_id` threads through.

## Steps (TDD)

- [ ] **Step 1: Failing write-tool tests** (`test_mcp_write_tools.py`, `call_tool` + fake
  pipeline; §9 demands happy + one failure per tool):
  - `create_draft`: returns id+slug, status `draft`, actor stamped as `author_id`; reactivates a
    soft-deleted tag name (same tag id — §4.1 pin); failure: empty title → `ToolInputError`;
  - `edit_content`: body change on a published item triggers `rebuild_chunks` once; on a draft it
    doesn't; `updated_by` = actor; failure: soft-deleted id → not-found error (**MCP half of the
    §9 soft-delete-visibility pin**);
  - `delete_content`: `is_deleted=True` + `remove_chunks` called, one transaction; failure:
    unknown id;
  - `tag_content`: add+remove in one call; failure: soft-deleted id;
  - `publish`: draft → published with chunks built; failure: embedding failure surfaces as a
    structured tool error and leaves the item draft (§4 atomicity through the tool path);
  - `archive`: published → archived, chunks removed; failure: unknown id.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** `tools_write.py` (thin wrappers; zero
  business logic — assert by reading the diff: every tool body is parse → service call → dict).
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Baseline:** regenerate `mcp-tools.json` (now 8 tools) — same commit.
- [ ] **Step 6: Gates → commit:** `feat(api): six MCP write tools (phase-5 task-02)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_mcp_write_tools.py -q   # all passed
uv run python scripts/export_mcp_tools.py && git diff --exit-code mcp-tools.json
python -c "import json;print(len(json.load(open('mcp-tools.json'))))"   # 8
```

## Acceptance

- All 8 core §6 tools registered with schemas matching the table (names, args, defaults).
- Behavior parity with REST is structural (same service calls), not duplicated logic.
- Actor stamping and soft-delete not-found semantics pinned per tool; §9's happy+failure
  coverage complete.
