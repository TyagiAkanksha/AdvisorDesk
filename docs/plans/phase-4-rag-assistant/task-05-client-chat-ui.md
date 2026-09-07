---
id: task-05
phase: phase-4-rag-assistant
depends_on: [task-02, phase-3-publish-client-content/task-04]
status: built
spec: advisordesk-prd.md §2.2, §5.3, §9
---

# task-05 — Client chat UI

## Goal

The client app's chat screen streams assistant answers token-by-token with numbered citations
linking to the source articles, renders refusals distinctly, keeps the session id in
`localStorage`, and turns errors/429s into friendly copy (§2.2, §5.3, §9).

## Context (read ONLY these)

- `docs/FRONTEND-CONVENTIONS.md` §3, §6 (client-island + hand-rolled SSE hook rules), §9.
- `advisordesk-prd.md` §5.3 (event shapes + session/localStorage rules — no cookies).
- `apps/client/src/components/content/Markdown` (p3-t04) — reuse for answer bodies.

## Files

- Create: `apps/client/src/components/chat/ChatScreen/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: `apps/client/src/components/chat/useChatStream.ts` (colocated VM hook)
- Create: `apps/client/src/components/chat/{MessageBubble,CitationList}/…` (folder-per-component)
- Create: thin page `apps/client/src/app/chat/page.tsx`; nav link from the content list header
- Create: `apps/client/src/types/api/chat.ts`

## Interfaces

- **Consumes:** `public_chat` endpoint events (task-02); `Markdown`; theme/common.
- **Produces (later tasks rely on — produce exactly):**
  - `useChatStream` (in-file Args/Result): state
    `{messages: ChatMessage[], streaming: boolean, error: string | null}` and
    `send(text: string)`; `ChatMessage = {role:'user'|'assistant', text,
    citations?: {content_id,title,slug}[], refusal?: boolean}`.
    Internals: `fetch` POST + `ReadableStream` SSE parser handling exactly `token` /
    `citations` / `done` / `error`; `session_id` read from and persisted to
    `localStorage['advisordesk_session']` on `done` (§5.3); HTTP 429 before any event → the §9
    friendly copy. **The parser utility is written to be liftable for phase-5's
    `useAgentStream` — keep it a standalone function `parseSseStream(reader, handlers)`.**
  - `CitationList`: numbered `[n]` chips linking to `/content/{slug}` (the p3-t04 route), order =
    server order (first use).

## Steps (TDD)

- [ ] **Step 1: Failing hook tests** (jsdom; mocked `fetch` returning scripted
  `ReadableStream`s): tokens accumulate into one assistant message in order; `citations` event
  attaches deduped citations; `done` stores the session id and the next `send` posts it back;
  `error` event → `error` state set, streaming false; 429 response → friendly message, no crash;
  empty-citations answer renders as refusal (`refusal: true` when `citations` event carries `[]`
  and the text matches the refusal — implementation note: flag on empty citations).
- [ ] **Step 2:** `pnpm -C apps/client test` → FAIL. **Step 3: implement** `parseSseStream` +
  `useChatStream`. **Step 4:** run → PASS.
- [ ] **Step 5: Failing component tests**: user/assistant bubbles by role; assistant text
  rendered through `Markdown`; citation chips link to `/content/{slug}`; refusal styled
  distinctly (queried by role/status); input disabled while streaming.
- [ ] **Step 6:** run → FAIL → **implement** screen/components + thin page → PASS.
- [ ] **Step 7: Gates → commit:** `feat(client): streaming chat UI with citations (phase-4 task-05)`

## Verify

```bash
pnpm -C apps/client test && pnpm -C apps/client lint && pnpm -C apps/client type-check
pnpm -C apps/client dev &   # with seeded API: covered question streams a cited answer,
                            # citation chips open the article pages; uncovered question shows
                            # the refusal; reload keeps the same session (localStorage)
```

## Acceptance

- §2.2 client chat story works against the live seeded stack; citations `[n]` link to real
  article pages; refusal path visually distinct.
- Session id lives in localStorage only (no cookies), echoed per §5.3.
- 429 and stream errors surface friendly copy, never raw JSON.

> ⚠️ Phase INDEX checkpoint: after this task's gates pass, pause for the user's live pass before
> closing phase 4.
