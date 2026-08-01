---
id: task-00
phase: phase-5-mcp-agent
depends_on: [phase-3-publish-client-content/task-02]
status: planned
spec: advisordesk-prd.md §2 (draft → published → archived), §4 lifecycle rule, §9 envelope
---

# task-00 — Lifecycle hardening (pre-task, owner decision 2026-07-25)

## Goal

Two carried defects are fixed BEFORE the MCP write tools wrap these services: (a) publishing an
already-published item no longer resets `published_at`, re-bills embeddings, or reorders the
public feed (phase-2 t02 finding #9, consequence upgraded at the phase-3 final review); (b) the
`draft → published → archived` state machine is enforced server-side with the §9 envelope —
today only the admin UI's disabled buttons stand between an API/MCP caller and a nonsense
transition.

## Context (read ONLY these)

- `advisordesk-prd.md` §2 admin stories ("I can move an item through statuses:
  `draft → published → archived`"), §4 "Lifecycle rule (critical)" + atomicity paragraph, §9
  envelope.
- `app/services/content.py` — `publish_content` (unconditionally stamps
  `published_at = now()` and calls `rebuild_chunks`) and `archive_content` (no status check):
  the two functions to harden. `update_content` is NOT in scope — its
  re-chunk-iff-published behavior is correct and already pinned.
- `app/services/errors.py` — `ConflictError` ("state-transition conflict — maps to 409") is the
  existing precedent; no new error class.
- `app/routes/content_routes.py` — `content_publish` / `content_archive` declare their error
  responses; the 409 must appear in the wire surface.

## The pinned transition matrix (controller decision, from the PRD flow + the admin UI's de
facto contract — `canPublish = draft|archived`, `canArchive = published` only)

| current \ action | `publish` | `archive` |
|---|---|---|
| `draft` | ✅ set `published_at`, build chunks (unchanged) | ❌ `ConflictError` → 409 |
| `published` | ✅ **idempotent guard**: preserve `published_at`, NO pipeline call | ✅ (unchanged) |
| `archived` | ✅ **re-publish**: preserve `published_at`, rebuild chunks (they were removed on archive) | ❌ `ConflictError` → 409 |
| soft-deleted | 404 (unchanged, via `get_content`) | 404 (unchanged) |

- **`published_at` rule — one sentence, implement exactly this:** `published_at` is stamped iff
  it is currently `NULL` (the first successful publish); it is never overwritten. This keeps the
  public feed order (`published_at DESC`) stable across re-publishes.
- **Publish-on-published skips the pipeline entirely.** Justification the code comment must
  carry: PRD §4 guarantees a published item's chunks always reflect its current `body_md`
  (`update_content` re-chunks atomically on every published edit), so "body unchanged since last
  embed" is the ONLY state reachable through the API/MCP surface — no comparison mechanism or
  schema change is needed. (If the implementer instead chooses an explicit comparison, it must
  not require a migration; document the choice in the report either way.)
- **Publish-on-archived always rebuilds** — archive removed the chunks; skipping would publish
  an unretrievable item.
- `ConflictError` messages name both states, e.g.
  `"Cannot archive content with status 'draft'."` — the message reaches the §9 envelope
  verbatim.

## Files

- Create: `apps/api/tests/test_lifecycle_transitions.py`
- Modify: `apps/api/app/services/content.py` (`publish_content`, `archive_content` — including
  their docstrings, which currently describe the unguarded behavior),
  `apps/api/app/routes/content_routes.py` (declare 409 on `content_archive`; `content_publish`
  has no illegal transition, so no 409 there), `apps/api/openapi.json` + both codegens (same
  commit — standing wire-surface gate).

## Interfaces

- **Consumes:** `ChunkPipeline` seam (p2/p3), `ConflictError` → 409 mapping (p1-t03),
  `get_content` active-row 404 (unchanged).
- **Produces (later tasks rely on):** `publish_content` / `archive_content` with the matrix
  above — **signatures unchanged**. Phase-5 task-02's `publish`/`archive` MCP tools wrap these
  and inherit the semantics; its brief pins the conflict-through-the-tool-path shape.

## Steps (TDD)

- [ ] **Step 1: Failing service tests** (`test_lifecycle_transitions.py`, DB fixture + recording
  fake pipeline, mirroring `test_services_content.py` idioms):
  - double publish: publish → capture `published_at` → publish again → same `published_at`
    (equality, not approx), `rebuild_chunks` called exactly ONCE across both calls, second call
    returns the row with `status='published'`;
  - re-publish after archive: publish → archive (chunks removed) → publish again →
    `published_at` unchanged from the first publish, `rebuild_chunks` called again (twice
    total), status `published`;
  - archive from `draft` → `ConflictError` whose message names both states; row untouched
    (status still `draft`, no pipeline call);
  - archive from `archived` → `ConflictError`; `remove_chunks` NOT called a second time;
  - the legal paths still pass: draft → published sets `published_at` once; published →
    archived removes chunks (guard against over-tightening — the existing suite covers these
    too, but assert them here against the new guards).
- [ ] **Step 2: Failing endpoint tests** (same file, TestClient): POST
  `/content/{id}/archive` on a draft → HTTP 409, body exactly
  `{"error": {"code": "conflict", "message": ...}}`; double POST `/content/{id}/publish` →
  200 both times, `published_at` identical in both response bodies.
- [ ] **Step 3:** run → FAIL (env-exported command). **Step 4: implement** — guards at the TOP
  of `publish_content`/`archive_content` (services raise; routes stay `try/except`-free per
  CONVENTIONS §4), docstrings updated to describe the matrix. **Step 5:** run → PASS.
- [ ] **Step 6: Baseline:** add the 409 response declaration to `content_archive`, regenerate
  `openapi.json` + both codegens — same commit.
- [ ] **Step 7: Gates → commit:**
  `fix(api): lifecycle hardening — idempotent re-publish + server-side transition guard (phase-5 task-00)`

## Verify

```bash
set -a && source /home/ak/Documents/github_akanksha/AdvisorDesk/.env && set +a && \
  cd /home/ak/Documents/github_akanksha/AdvisorDesk/apps/api && \
  uv run pytest tests/test_lifecycle_transitions.py -q   # all pass
uv run pytest -q                                          # full suite (274+) still green
git diff --exit-code openapi.json 2>/dev/null || true     # regenerated in-commit
```

## Acceptance

- The matrix is pinned test-by-test: preserve, skip, rebuild-on-republish, and both 409
  rejections, at the service AND route layers.
- `published_at` is written iff `NULL`; no code path overwrites it.
- Existing suite green — no pinned test weakened (none pins the old reset behavior; verified by
  controller grep 2026-08-01).
- Wire surface regenerated in the same commit; signatures unchanged.
