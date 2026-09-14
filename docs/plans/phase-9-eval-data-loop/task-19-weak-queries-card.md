---
id: p9-t19
phase: phase-9-eval-data-loop
depends_on: [p9-t15, p9-t17]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 19 — the weak-query report on the admin dashboard (beat 5, seen not narrated)

## Goal

An advisor opens the admin dashboard and sees what clients asked that the content handled badly —
including every 👎 — without asking the agent. DESIGN §D's `weak_queries` already exists as a
service (`app/services/chat.py:503`) and as the MCP tool `report_weak_queries`
(`app/mcp/tools_gaps.py:95`); nothing on the REST/admin side reads it. Owner decision 2026-09-13
(after verifying beat 5 on prod: a 👎 on a confident, four-source answer showed up ONLY through the
human signal): one read-only admin route wrapping the service, one dashboard card. Scope is fixed
to exactly that — no filters, no pagination beyond `days`/`limit`, no per-content counts, no
"propose a fix" button (the agent panel already does that; it stays beat 4's entry point).

## Context (read ONLY these)

- `apps/api/app/services/chat.py:362` (`WEAK_QUERY_KINDS`), `:436-455` (`WeakQueryExample`,
  `WeakQueryGroup`), `:503-590` (`weak_queries` — signature, precedence table, grouping).
- `apps/api/app/mcp/tools_gaps.py:80-135` — the MCP tool's args and wire dict. The REST response
  mirrors its field NAMES (`normalized_question`, `worst_top_similarity`, `examples[].asked_at`)
  so the two surfaces agree.
- `apps/api/app/routes/oauth_admin_routes.py` — the sibling-router pattern (router-level
  `dependencies=[Depends(require_admin)]`, `responses={401: ErrorEnvelope}`, `operation_id`),
  and `apps/api/app/factory.py:181-197` (mount order).
- `apps/api/app/routes/content_routes.py:279-286` (`stats_get` — `get_session` + settings-free
  read) and `apps/api/app/routes/deps.py:121` (`get_settings`).
- `apps/api/tests/test_routes_content.py:89-118` (`_build_settings`/`_build_client`, `login_as`),
  `:145-200` (the unauthenticated-route case list + 401 envelope test — the new route joins the
  list), `:459-482` (the stats test shape).
- `apps/api/tests/test_weak_queries.py:100-150` (`_ask` — seeds one user/assistant pair with
  `found`/`top_similarity`/`feedback`/`ago`; copy its minimal form into the route test file).
- `apps/admin/src/lib/api/statsApi.ts`, `baseApi.ts:74` (`tagTypes`), `src/types/api/stats.ts`
  (the DTO alias rule), `src/lib/copy.ts:39-47`.
- `apps/admin/src/components/dashboard/DashboardScreen/{Component.tsx,useDashboard.ts}` and
  `components/RecentContent/{Component.tsx,interface.ts,index.ts,Component.test.tsx}` — the card
  pattern to mirror; `Component.test.tsx:12-65` — the request-aware `mockFetch` (returns 404 for
  unmocked routes — the new route MUST be added to it or every existing dashboard test sees the
  new card fail).
- `docs/FRONTEND-CONVENTIONS.md` §4 (`common/` is the only `@mui/*` importer), §5 (`src/types/`
  is the only `components['schemas']` reader), §7 (mock only the network edge).

## Files

**Create**
- `apps/api/app/models/schemas/weak_queries.py`
- `apps/api/app/routes/weak_queries_routes.py`
- `apps/api/tests/test_routes_weak_queries.py`
- `apps/admin/src/types/api/weakQueries.ts`
- `apps/admin/src/lib/api/weakQueriesApi.ts`
- `apps/admin/src/components/dashboard/DashboardScreen/components/WeakQueries/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`

**Modify**
- `apps/api/app/factory.py` — mount the router (after `content_router`, same `_API_PREFIX`).
- `apps/api/tests/test_routes_content.py:145-172` — ONE tuple appended to
  `_unauthenticated_route_cases()`: `("weak_queries_get", "GET", "/api/v1/weak-queries", None)`
  (authorised amendment; nothing else in that file changes).
- `apps/admin/src/lib/api/baseApi.ts:74` — `tagTypes` gains `'WeakQueries'`.
- `apps/admin/src/lib/copy.ts` — four constants (below).
- `apps/admin/src/components/dashboard/DashboardScreen/useDashboard.ts` — third query.
- `apps/admin/src/components/dashboard/DashboardScreen/Component.tsx` — third panel.
- `apps/admin/src/components/dashboard/DashboardScreen/Component.test.tsx` — `mockFetch` learns
  `/api/v1/weak-queries` (+ an `overrides.weakQueries` slot) and two new `it` blocks; every
  existing `it` stays byte-identical.

**Regenerate (same commit):** `apps/api/openapi.json` (`uv run python scripts/export_openapi.py`
from `apps/api`), `apps/admin/src/types/generated/schema.d.ts` (`pnpm -C apps/admin codegen`),
`apps/client/src/types/generated/schema.d.ts` if the client codegen reads the same file (run it
and commit whatever changes; a zero diff is fine). NOT `mcp-tools.json` — no tool changes.

## Interfaces

### `app/models/schemas/weak_queries.py`

```python
class WeakQueryExampleOut(BaseModel):
    question: str
    kind: str                      # one of WEAK_QUERY_KINDS
    top_similarity: float | None
    asked_at: datetime             # WeakQueryExample.created_at

class WeakQueryGroupOut(BaseModel):
    normalized_question: str       # WeakQueryGroup.normalized
    count: int
    kinds: list[str]               # WEAK_QUERY_KINDS order, as the service returns them
    worst_top_similarity: float | None
    examples: list[WeakQueryExampleOut]   # at most 3, newest first (service contract)

class WeakQueriesResponse(BaseModel):
    threshold: float               # settings.similarity_threshold the bands were judged against
    days: int                      # the window actually applied
    count: int                     # len(items) — same semantic as the MCP tool's `count`
    items: list[WeakQueryGroupOut] # REST lists use `items` (ContentList/ConnectedApps); the MCP
                                   # tool's key is `weak_queries` — say so in the docstring
```

Plain constructors, no `from_attributes` — build each model field-by-field in the route (the
dataclass field names differ: `normalized` → `normalized_question`, `created_at` → `asked_at`).

### `app/routes/weak_queries_routes.py`

```python
router = APIRouter(
    prefix="/weak-queries",
    tags=["weak-queries"],
    dependencies=[Depends(require_admin)],
    responses={401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)

_DEFAULT_DAYS = 7      # the dashboard's window ("last 7 days")
_MAX_DAYS = 90
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100       # same ceiling as tools_gaps._MAX_LIMIT

@router.get("", operation_id="weak_queries_get", response_model=WeakQueriesResponse)
def weak_queries_get(
    days: int = Query(_DEFAULT_DAYS, ge=1, le=_MAX_DAYS),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WeakQueriesResponse: ...
```

Calls `weak_queries(session, days=days, limit=limit, threshold=settings.similarity_threshold)`;
no `threshold` query parameter (same reasoning as `ReportWeakQueriesArgs`' docstring — the bands
only mean something against the live threshold). Out-of-range `days`/`limit` → the existing 422
`ErrorEnvelope` (`app/routes/errors.py`'s `RequestValidationError` handler; nothing to add).
Mounted in `factory.py` as `app.include_router(weak_queries_router, prefix=_API_PREFIX)` directly
after `content_router`. Final URL: `GET /api/v1/weak-queries?days=7&limit=20` (unprefixed under
`/api/v1` like `/stats` and `/content` — this API has no `/admin/` segment).

### `apps/admin/src/types/api/weakQueries.ts`

```ts
import type { components } from '../generated/schema';

export type WeakQueriesDto = components['schemas']['WeakQueriesResponse'];
export type WeakQueryGroupDto = components['schemas']['WeakQueryGroupOut'];

// Mirrors app/services/chat.py WEAK_QUERY_KINDS (precedence order). `kind` is a plain string on
// the wire; unknown values render with the raw string and the `default` colour.
export const WEAK_QUERY_KIND_LABELS: Record<string, string> = {
  negative_feedback: 'Thumbs down',
  refused: 'Refused',
  near_miss: 'Near miss',
  low_confidence: 'Low confidence',
};
export const WEAK_QUERY_KIND_COLORS: Record<string, 'error' | 'default' | 'warning' | 'info'> = {
  negative_feedback: 'error',
  refused: 'default',
  near_miss: 'warning',
  low_confidence: 'info',
};
```

### `apps/admin/src/lib/api/weakQueriesApi.ts`

```ts
export interface WeakQueriesArgs { days: number; limit: number }
getWeakQueries: builder.query<WeakQueriesDto, WeakQueriesArgs>({
  query: ({ days, limit }) => `/api/v1/weak-queries?days=${days}&limit=${limit}`,
  providesTags: ['WeakQueries'],
})
export const { useGetWeakQueriesQuery } = weakQueriesApi;
```

### `apps/admin/src/lib/copy.ts` (append)

```ts
export const WEAK_QUERIES_TITLE = 'Weak queries (last 7 days)';
export const NO_WEAK_QUERIES_MESSAGE = 'No weak queries in the last 7 days.';
export const WEAK_QUERIES_LOAD_ERROR = "Couldn't load weak queries.";
export const WEAK_QUERIES_ARIA_LABEL = 'Weak queries';
```

### `useDashboard.ts` (extend, same shape as `recent`)

```ts
weakQueries: WeakQueryGroupDto[] | undefined;   // data?.items
weakQueriesFailed: boolean;                     // data === undefined && isError
```
via `useGetWeakQueriesQuery({ days: 7, limit: 20 })`. The dashboard-level `isLoading`/`loadFailed`
stay tied to `stats` only (a weak-queries failure degrades the card, never the dashboard).

### `components/WeakQueries/` (dumb leaf)

`interface.ts`: `export interface WeakQueriesProps { items: WeakQueryGroupDto[] }`.
`Component.tsx`: `items.length === 0` → `<EmptyState message={NO_WEAK_QUERIES_MESSAGE} />`;
otherwise a `Table size="small" aria-label={WEAK_QUERIES_ARIA_LABEL}` with columns
**Question | Kinds | Asked | Worst similarity**: `normalized_question`; one `Chip size="small"`
per kind with `label={WEAK_QUERY_KIND_LABELS[kind] ?? kind}` and
`color={WEAK_QUERY_KIND_COLORS[kind] ?? 'default'}` (a `Stack direction="row" spacing={0.5}`);
`count` as `×N`; `worst_top_similarity` formatted `toFixed(2)` or `'—'` when `null`. Row key =
`normalized_question`. All imports from `@/components/common` only.

### `DashboardScreen/Component.tsx` (one more panel)

A third `Grid size={{ xs: 12 }}` after Recent content, same `Paper variant="outlined"` +
`Typography h5` title (`WEAK_QUERIES_TITLE`) + the same three-state body as Recent content:
`weakQueriesFailed ? <ErrorState message={WEAK_QUERIES_LOAD_ERROR} />`, `weakQueries ?
<WeakQueries items={weakQueries} />`, else `<Skeleton variant="rectangular" height={160} />`.

## Steps (TDD)

RED (test-author):
1. `tests/test_routes_weak_queries.py` — copy `_build_settings`/`_build_client` (without the
   pipeline) and a minimal `_ask` from `test_weak_queries.py`; pins:
   - `test_weak_queries_get_requires_admin_session` — 401 `auth_required` envelope.
   - `test_weak_queries_get_returns_groups_in_service_shape` — seed a 👎 pair
     (`found=True, top_similarity=0.6, feedback=-1`), a refused pair (`found=False,
     top_similarity=0.2`), a near-miss pair (`found=False, top_similarity=0.45`), and an
     answered-confident pair (`found=True, top_similarity=0.8`, must NOT appear); `GET
     /api/v1/weak-queries` → 200, `set(body) == {"threshold","days","count","items"}`,
     `body["days"] == 7`, `body["threshold"] == 0.5`, `count == 3 == len(items)`, each item has
     exactly `{"normalized_question","count","kinds","worst_top_similarity","examples"}`, the
     👎 item's `kinds == ["negative_feedback"]`, each example has exactly
     `{"question","kind","top_similarity","asked_at"}` and `asked_at` parses as ISO-8601.
   - `test_weak_queries_get_days_window_and_limit_apply` — one pair `ago=timedelta(days=10)`:
     default (7 d) excludes it, `?days=30` includes it; three pairs + `?limit=2` → `count == 2`.
   - `test_weak_queries_get_rejects_out_of_range_params` — `?days=0`, `?days=91`, `?limit=0`,
     `?limit=101` → 422 envelope (`error.code == "validation_error"` — copy the code the
     existing 422 pin in `test_routes_content.py:484` asserts).
   - Append the unauthenticated-route tuple to `test_routes_content.py`.
   Run: `uv run pytest -q tests/test_routes_weak_queries.py` → all fail with 404 / import
   errors; full suite: only these new tests red. Commit: `test(api): weak-queries admin route pins
   RED (p9 t19)`.
2. Admin RED: `WeakQueries/Component.test.tsx` — renders one row per item with the question, a
   chip per kind carrying the LABEL (`Thumbs down`, `Near miss`), `×2` for count 2, `0.60` for
   0.601, `—` for `null`; empty → `NO_WEAK_QUERIES_MESSAGE`. `DashboardScreen/Component.test.tsx`
   — extend `mockFetch` for `/api/v1/weak-queries` (fixture: two groups) and add
   `it('renders the weak-queries card from GET /api/v1/weak-queries')` (title + a row's question
   + a `Thumbs down` chip) and `it('shows the card error without blanking the dashboard')`
   (`weakQueries` override → 500 → `WEAK_QUERIES_LOAD_ERROR` visible AND the stat cards still
   render). These fail on missing modules/copy. Commit: `test(admin): weak-queries dashboard card
   pins RED (p9 t19)`.

GREEN (implementer): schemas → route → mount → regenerate `openapi.json` → admin codegen → types
→ api slice + tag → copy → hook → leaf → dashboard panel. Gates below. Commit: `feat(admin): weak
queries on the dashboard via GET /api/v1/weak-queries (p9 t19)`.

## Verify

```sh
cd /home/ak/Documents/github_akanksha/AdvisorDesk/apps/api   # ONLY TEST_DATABASE_URL exported
uv run ruff check --no-cache . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q -rs
uv run python scripts/export_openapi.py && git diff --exit-code -- openapi.json
cd ../admin && pnpm codegen && git diff --exit-code -- src/types/generated/schema.d.ts
pnpm type-check && pnpm lint && pnpm format:check && npx vitest run && pnpm build
cd ../client && pnpm codegen 2>/dev/null; git status --porcelain   # commit any client schema change
```

## Acceptance

- `GET /api/v1/weak-queries` is admin-session-gated (401 envelope without a session), clamps
  `days` 1–90 / `limit` 1–100 with the standard 422 envelope, and returns exactly the
  `WeakQueriesResponse` shape above — field names identical to the MCP tool's dict except the
  list key (`items`), which the schema docstring explains.
- The route adds no logic: one `weak_queries(...)` call, one field-for-field mapping. No new
  import-linter edge (`app.routes` → `app.services` already exists); 8 contracts still kept.
- The dashboard shows the card with kind chips, counts, and worst similarity; an empty window shows
  the empty state; a failed request degrades ONLY the card (stat cards, tag table and recent
  content still render, dashboard-level `ErrorState` not shown).
- `common/` remains the only `@mui/*` importer; `src/types/` the only `components['schemas']`
  reader; the leaf takes props and raises nothing; every existing dashboard `it` block is
  byte-identical (only `mockFetch`'s route table and fixtures changed).
- `openapi.json` and both generated `schema.d.ts` files are regenerated in the same commit and
  regenerate to a zero diff afterwards; `mcp-tools.json` untouched.
- API: 1071 + new tests passed / 0 failed / 1 skipped. Admin: all gates + `build` green.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-19-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-19-implementer.md` — must
  list the generated-file diffs (which schemas were added), the exact `mockFetch` edit, and gate
  counts for both apps (passed/failed/skipped).
