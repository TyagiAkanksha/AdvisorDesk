---
id: task-03
phase: phase-3-publish-client-content
depends_on: [phase-2-auth-cms-crud/task-03]
status: built
spec: advisordesk-prd.md §5.3, §4.1
---

# task-03 — Public content API

## Goal

The two unauthenticated §5.3 content routes exist: published-and-non-deleted list (with tags) and
by-slug detail. This is the client app's entire content data source (task-04) and the public half
of the §9 soft-delete-visibility pin.

## Context (read ONLY these)

- `advisordesk-prd.md` §5.3 (routes — "published and non-deleted only"; deleted slug 404s and is
  never reassigned, §4.1).
- `CONVENTIONS.md` §4–§5, §8 (baseline gate).
- `app/services/content.py` — reuse `list_content`/lookups; add only what's missing.

## Files

- Create: `apps/api/app/routes/public_routes.py`, `apps/api/app/models/schemas/public.py`
- Create: `apps/api/tests/test_public_content.py`
- Modify: `apps/api/app/services/content.py` (add `get_published_by_slug`),
  `apps/api/app/factory.py` (include router), `apps/api/openapi.json` + both codegens

## Interfaces

- **Consumes:** content services + models; `active_select`.
- **Produces (later tasks rely on — produce exactly):**
  - Routes/operation_ids: `GET /public/content` `public_content_list` ·
    `GET /public/content/{slug}` `public_content_get`. No auth, no cookies.
  - DTOs: `PublicContentSummary{title, slug, tags, published_at}` ·
    `PublicContentDetail{title, slug, body_md, tags, published_at}` — **no ids, no admin fields**
    (client links by slug; §5.3).
  - Service addition: `get_published_by_slug(session, slug) -> Content` — raises `NotFoundError`
    unless `status == 'published'` and not deleted.

## Steps (TDD)

- [ ] **Step 1: Failing visibility-matrix tests** (`test_public_content.py`): seed one item per
  state {draft, published, archived, soft-deleted-published}; list returns ONLY the published one
  (with its tags); detail by slug → 200 for published; 404 for draft, archived, and deleted
  (**§9 public soft-delete pin — the deleted item still has `status='published'`, so this test
  fails if anyone forgets the `is_deleted` filter**); response bodies contain no `id`/`author`
  fields; endpoints work with no cookie at all.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** service addition + DTOs + routes.
  **Step 4:** run → PASS.
- [ ] **Step 5: Baseline:** regenerate `openapi.json` + both apps' codegen, same commit.
- [ ] **Step 6: Gates → commit:** `feat(api): public content routes (phase-3 task-03)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_public_content.py -q   # all passed
curl -s localhost:8000/api/v1/public/content | head -c 200            # published-only list, no ids
git diff --exit-code openapi.json                                      # baseline current
```

## Acceptance

- §5.3 exactly: published AND non-deleted only, both routes, slug-addressed detail, tags
  included in list.
- The four-state visibility matrix passes; public DTOs expose no internal fields.
- Baseline + codegens updated in the same commit.
