---
id: task-02
phase: phase-2-auth-cms-crud
depends_on: [phase-1-skeleton/task-02]
status: built
spec: advisordesk-prd.md §4, §4.1, §5.2, §9
---

# task-02 — Content, tag, and stats services with the lifecycle seam

## Goal

The full CMS business layer exists as session-first service functions: draft creation with §4 slug
rules, listing/filtering, updates with actor stamping, soft delete as tombstone + chunk removal in
one transaction, tags with §4.1 reactivation, stats. Publish/archive run behind an explicit
`ChunkPipeline` seam (no-op here; phase-3 task-02 fills it with real embedding). These are the
exact functions the §5.2 routes AND the phase-5 MCP tools wrap — PRD §3's "no duplicated business
logic" rule.

## Context (read ONLY these)

- `advisordesk-prd.md` §4 (slug rules, lifecycle rule), §4.1 (soft delete, uniqueness/
  reactivation, actor columns), §5.2 (list params), §9 (test list: slug permanence, tag
  reactivation, soft-delete visibility).
- `CONVENTIONS.md` §3 (session-first, flush-never-commit, active_select, actor param).

## Files

- Create: `apps/api/app/services/{content.py,tags.py,stats.py,lifecycle.py}`
- Create: `apps/api/tests/{test_services_content.py,test_services_tags_stats.py}`
- Modify: `apps/api/app/services/errors.py` (ensure `NotFoundError`, `ConflictError` cover these
  paths)

## Interfaces

- **Consumes:** models + `active_select` (p1-t02); error family (p1-t03).
- **Produces (later tasks rely on — produce exactly):**
  - `app.services.lifecycle`: `class ChunkPipeline(Protocol)` —
    `rebuild_chunks(session, content) -> int` and `remove_chunks(session, content_id) -> int`;
    `class NoopChunkPipeline` (returns 0s). Wired via `app.state.chunk_pipeline`
    (factory param `chunk_pipeline=None` → Noop). **phase-3-publish-client-content/task-02
    replaces the wiring with the real embedding pipeline — signatures must not change.**
  - `app.services.content` (all take `session: Session` first; `actor_id: uuid.UUID | None`):
    - `create_draft(session, *, title, body_md="", tags=(), actor_id) -> Content`
    - `get_content(session, content_id) -> Content` (active only; else `NotFoundError`)
    - `list_content(session, *, status=None, tag=None, q=None, page=1, page_size=20)
      -> tuple[list[Content], int]`
    - `update_content(session, content_id, *, title=None, body_md=None, tags=None, actor_id,
      pipeline) -> Content` (slug unchanged; re-chunks via pipeline iff published)
    - `delete_content(session, content_id, *, actor_id, pipeline) -> None` (soft delete §4)
    - `publish_content(session, content_id, *, actor_id, pipeline) -> Content`
    - `archive_content(session, content_id, *, actor_id, pipeline) -> Content`
    - `generate_slug(session, title) -> str` (§4: slugify; on collision `-2`, `-3`, ...;
      collision check spans soft-deleted rows)
  - `app.services.tags`: `get_or_create_tags(session, names) -> list[Tag]` (normalizes to
    lowercase-hyphen; reactivates soft-deleted same-name rows — same id, §4.1),
    `list_tags_with_counts(session) -> list[tuple[Tag, int]]` (non-deleted tags; counts over
    non-deleted content).
  - `app.services.stats`: `content_stats(session) -> StatsData` (`by_status: dict[str,int]`,
    `by_tag: dict[str,int]`, soft-deleted excluded).

## Steps (TDD)

- [ ] **Step 1: Failing content tests** (`test_services_content.py`): create sets uuid/draft/slug
  `roth-ira-basics`; second same-title → `-2`; **slug permanence pin (§9): soft-delete the first,
  create same title again → `-3` suffix, deleted slug never reused**; title edit leaves slug;
  update stamps `updated_by=actor` and bumps `updated_at`; get/list exclude soft-deleted
  (**§9 visibility pin via `active_select`**); delete on published removes chunks via a recording
  fake pipeline and leaves `status='published'` + `published_at` untouched (§4); publish sets
  `status`/`published_at` and calls `pipeline.rebuild_chunks` once; archive calls
  `remove_chunks`; update of a published item re-chunks, of a draft does not; list filters
  status/tag/q + pagination totals.
- [ ] **Step 2:** `uv run pytest tests/test_services_content.py -q` → FAIL.
- [ ] **Step 3: Implement** `lifecycle.py` + `content.py` minimal-to-green; flush-never-commit;
  every read through `active_select`.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Failing tag/stats tests** (`test_services_tags_stats.py`): normalization
  (`"Tax Planning"` → `tax-planning`); **reactivation pin (§9): soft-deleted tag re-created →
  same row id, active**; counts ignore soft-deleted content and exclude deleted tags; stats
  by_status/by_tag correct on a seeded matrix.
- [ ] **Step 6:** run → FAIL; **implement** `tags.py` + `stats.py`; run → PASS.
- [ ] **Step 7: Gates → commit:**
  `feat(api): content/tag/stats services + lifecycle seam (phase-2 task-02)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_services_content.py tests/test_services_tags_stats.py -q
uv run mypy && uv run lint-imports        # services import only models+config (contract kept)
grep -rn "commit()" app/services/         # no hits — transaction boundary stays with callers
grep -rn "is_deleted ==" app/ | grep -v queries.py   # no ad-hoc soft-delete filters
```

## Acceptance

- §9's slug-permanence, tag-reactivation, and (service-level) soft-delete-visibility tests pass.
- Delete = tombstone + `remove_chunks` in the same transaction; status untouched (§4).
- The pipeline seam is the only publish/embed coupling — a fake pipeline fully exercises phase-2;
  phase-3 swaps the wiring without touching these signatures.
- No service commits, no service imports outside models/config.
