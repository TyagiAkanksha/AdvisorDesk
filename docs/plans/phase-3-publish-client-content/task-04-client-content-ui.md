---
id: task-04
phase: phase-3-publish-client-content
depends_on: [phase-1-skeleton/task-04, task-03]
status: planned
spec: advisordesk-prd.md §2.2, §5.3, §8, §12
---

# task-04 — Client app content pages (server-rendered)

## Goal

Clients browse published content: a list page of article cards and a markdown-rendered detail page
by slug (§2.2). Pages are React Server Components fetching the public API server-side —
SEO/TTFB-correct per FRONTEND-CONVENTIONS §6 — and the shared markdown renderer built here also
replaces the admin editor's preview internals.

## Context (read ONLY these)

- `docs/FRONTEND-CONVENTIONS.md` §3, §6 (client-app RSC rule).
- `advisordesk-prd.md` §5.3 (data source), §8 (disclaimer footer must be visible), §12 (SEO work
  out of scope — titles only).
- `apps/client/src/types/generated/schema.d.ts` (post task-03 codegen).

## Files

- Create: `apps/client/src/lib/publicApi.ts`, `apps/client/src/types/api/content.ts`
- Create: `apps/client/src/components/content/ContentListScreen/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: `apps/client/src/components/content/ArticleScreen/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: `apps/client/src/components/content/Markdown/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: thin pages `src/app/page.tsx` (list), `src/app/content/[slug]/page.tsx` (detail with
  `generateMetadata` title + `notFound()` on 404)
- Modify: `apps/admin/src/components/content/MarkdownPreview/Component.tsx` (swap internals to the
  same renderer approach; props unchanged)

## Interfaces

- **Consumes:** public DTOs via `@/types` (`PublicContentSummary`, `PublicContentDetail`);
  theme/common (p1-t04).
- **Produces (later tasks rely on — produce exactly):**
  - `@/lib/publicApi`: `getPublishedContent() -> Promise<PublicContentSummaryDto[]>` ·
    `getContentBySlug(slug: string) -> Promise<PublicContentDetailDto | null>` — server-side
    fetch helpers (`cache: 'no-store'`), base URL from `API_URL` env (server-side var).
  - `content/Markdown` (`{markdown: string}`): react-markdown + remark-gfm mapped onto MUI
    Typography/Link/List components (implementation note: renderer choice). **Phase-4 task-05
    reuses it for assistant answers.**
  - Route shape `/content/[slug]` — **phase-4's citation links target exactly this path.**

## Steps (TDD)

- [ ] **Step 1: Failing component tests** (jsdom): Markdown renders headings/lists/links from a
  GFM fixture (queried by role) and never raw HTML injection (`<script>` neutralized);
  ContentListScreen renders a card per item with title/tags and links to `/content/{slug}`;
  ArticleScreen renders title, Markdown body, tag chips, and the §8 disclaimer footer text.
- [ ] **Step 2:** `pnpm -C apps/client test` → FAIL. **Step 3: implement** components +
  `publicApi` + thin pages. **Step 4:** run → PASS.
- [ ] **Step 5: Swap admin preview internals** to the same renderer (props contract unchanged);
  admin tests still green: `pnpm -C apps/admin test`.
- [ ] **Step 6: Gates → commit:**
  `feat(client): content list + article pages with markdown (phase-3 task-04)`

## Verify

```bash
pnpm -C apps/client test && pnpm -C apps/client lint && pnpm -C apps/client type-check
pnpm -C apps/client dev &   # / lists seeded published articles; /content/<slug> renders markdown;
                            # unknown slug → 404 page; page source shows server-rendered HTML
grep -rn "'use client'" apps/client/src/components/content    # empty — RSC only
```

## Acceptance

- §2.2 client browsing story works server-rendered; unknown/deleted slugs show the 404 page.
- Disclaimer footer visible on every article (§8).
- One markdown renderer serves both apps (admin preview swapped without a props change).
- No RTK Query anywhere in `apps/client`.
