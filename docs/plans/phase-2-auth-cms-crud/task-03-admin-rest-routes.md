---
id: task-03
phase: phase-2-auth-cms-crud
depends_on: [task-01, task-02]
status: planned
spec: advisordesk-prd.md §5.2, §5, §9
---

# task-03 — All nine §5.2 admin routes, DTOs, and the OpenAPI baseline

## Goal

The complete authenticated CMS REST surface exists: content CRUD + transitions, tags, stats — thin
routes over task-02's services, every one with a stable `operation_id`. The committed
`openapi.json` baseline + both apps' codegen become the standing wire-surface gate for the rest of
the build. Includes the §9 smoke test (`boot the API and hit /api/v1/stats`).

## Context (read ONLY these)

- `advisordesk-prd.md` §5.2 (routes + query params), §5 intro (soft-deleted 404 blanket rule).
- `CONVENTIONS.md` §4 (no try/except in routes), §5 (operation_id), §8 (baseline gate).
- `apps/api/app/services/content.py` — the signatures to wrap (do not re-implement logic).

## Files

- Create: `apps/api/app/routes/content_routes.py`,
  `apps/api/app/models/schemas/{content.py,tags.py,stats.py,common.py}`
- Create: `apps/api/tests/{test_routes_content.py,test_smoke.py}`
- Modify: `apps/api/app/factory.py` (include router), `apps/api/openapi.json`, both apps' codegen

## Interfaces

- **Consumes:** `require_admin` (task-01); all task-02 services; `get_session`/pipeline state
  (p1-t03 / task-02).
- **Produces (later tasks rely on — produce exactly):**
  - Routes/operation_ids: `GET /content` `content_list` (params `status,tag,q,page,page_size`) ·
    `POST /content` `content_create` (201) · `GET /content/{id}` `content_get` ·
    `PATCH /content/{id}` `content_update` · `DELETE /content/{id}` `content_delete` (204) ·
    `POST /content/{id}/publish` `content_publish` · `POST /content/{id}/archive`
    `content_archive` · `GET /tags` `tags_list` · `GET /stats` `stats_get`.
  - DTOs (schemas/): `ContentCreate{title, body_md="", tags=[]}` ·
    `ContentUpdate{title?, body_md?, tags?}` ·
    `ContentResponse{id, title, slug, body_md, status, tags, author_id, updated_by, published_at,
    created_at, updated_at}` · `ContentListResponse{items, total, page, page_size}`
    (envelope field names = implementation note) · `TagWithCount{id, name, count}` ·
    `StatsResponse{by_status, by_tag}`. Admin UI (tasks 05–06) consumes these via codegen.
- **Implementation note:** pagination envelope field names chosen here; record in README.

- **Envelope completion (phase-1 final-review decision — plan gap closed here):** register
  handlers for `RequestValidationError` and Starlette's `HTTPException` so framework-native 404
  (unknown route/id) and 422 (validation) responses ALSO emit the §9 envelope
  `{"error":{"code","message"}}` (codes `validation_error` / `http_<status>`), not FastAPI's
  native `{"detail": ...}` shape. Tests pin both: a bad-body 422 and an unknown-path 404 return
  the envelope. This task has the first parameterized/validated routes, so the gap becomes real
  here.

## Steps (TDD)

- [ ] **Step 1: Failing route tests** (`test_routes_content.py`, `login_as` helper): 401 matrix —
  every route without a session; CRUD happy path create→get→patch→list; list filters + pagination
  totals; publish→archive→delete transition flow (fake pipeline observed); **soft-deleted id →
  404 on get/patch/publish/archive/delete (§5 blanket rule)**; DELETE returns 204 and the item
  vanishes from list/stats; tags endpoint returns counts; error envelope shape on a 404.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** DTOs + routes (thin: parse → call service →
  DTO; no try/except). **Step 4:** run → PASS.
- [ ] **Step 5: Smoke test** (`test_smoke.py`, §9): boot `create_app` with the test session
  factory, `GET /api/v1/stats` with a session cookie → 200 with `by_status` keys.
- [ ] **Step 6: Baseline:** export `openapi.json`; run `pnpm -C apps/admin codegen` and
  `pnpm -C apps/client codegen`; commit all three together (the standing gate starts now).
- [ ] **Step 7: Gates → commit:**
  `feat(api): admin content/tags/stats routes + openapi baseline (phase-2 task-03)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_routes_content.py tests/test_smoke.py -q
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json
grep -c "operation_id" app/routes/content_routes.py    # 9
cd ../.. && pnpm -C apps/admin codegen && git diff --exit-code apps/admin/src/types/generated
```

## Acceptance

- All nine §5.2 routes live under `/api/v1`, admin-gated, with the exact operation_ids above.
- Soft-deleted rows 404 on every by-id operation; lists/counts exclude them (§5).
- §9 smoke test passes; baseline + both codegens committed in the same commit as the routes.
