---
id: vrf-t02
phase: video-review-fixes
depends_on: []
status: todo
spec: advisordesk-prd.md §5.3 (citations event), §7.5 (refusal behaviour)
review: sonnet
---

# Task 02 — a refusal never shows Sources; home subtitle; t01 deferred minors

## Goal

With cw t01 the client knows a reply is a refusal from the explicit `refusal` flag. But
`MessageBubble` still renders `CitationList` whenever `citations` is non-empty — so a near-miss
refusal (retrieval returned one chunk just above the 0.5 threshold, the model declined) shows a
warning Alert AND "Sources: [1] ISOs and NSOs", which reads as "here is your source" under an
answer that says there is none (t01 review minor M-1; the 2026-10-31 demo review flagged it on
screen). After this task a refusal renders no Sources region at all. Second, the home subtitle
"retirement, insurance, taxes and college savings" omits equity compensation, investing and
estate planning, which are a large share of the library. Third, fold t01's deferred minors
M-2/M-4/M-5 (stale comments; fixtures without `refusal`).

## Context (read ONLY these)

- `apps/client/src/components/chat/MessageBubble/Component.tsx` — header comment `:11-17`,
  `citations` at `:51`, `<CitationList>` at `:55`, the `message.refusal` branch at `:75-85`.
- `apps/client/src/components/chat/MessageBubble/Component.test.tsx` — existing cases at `:51`
  (citation chips), `:66`/`:137` (refusal status region / warning alert), `:98` (zero citations,
  refusal false).
- `apps/client/src/components/chat/CitationList/Component.tsx` (renders nothing for `[]`; it is
  NOT where the refusal rule belongs — `MessageBubble` owns refusal rendering).
- `apps/client/src/lib/copy.ts:33-36` (`HOME_DESCRIPTION`), `SOURCES_LABEL` in the same file.
- `apps/client/src/components/content/ContentListScreen/Component.test.tsx:34`.
- t01 minors: `apps/client/src/types/api/chat.ts:15` (M-2 stale comment);
  `apps/client/src/components/chat/useChatStream.ts` `attachMessageId` doc comment (M-4);
  fixtures sending `{citations: []}` without `refusal` in `useChatStream.test.ts` (~the feedback
  cases), `useChatStream.feedback.test.ts`, `ChatScreen/feedback.test.tsx` (M-5).
- `advisordesk-prd.md` §7.5 — the paragraph cw t01 amended (grep `refusal`).
- `docs/FRONTEND-CONVENTIONS.md` §4 (dumb components), §7 (mock only the network edge).

## Interfaces

- `MessageBubble/Component.tsx`: render `<CitationList citations={citations} />` only when
  `!message.refusal`. Header comment gains one sentence: a refusal never advertises Sources, even
  when retrieval returned a near miss (`app/config.py` `SIMILARITY_THRESHOLD` comment: "a
  citation on a refusal" is exactly the artefact this hides).
- `copy.ts`: `HOME_DESCRIPTION = 'Plain-English explainers on taxes, retirement, equity
  compensation, investing, insurance, estate planning and college savings.'`
- PRD §7.5: append one sentence to the amended paragraph: "The client renders a refusal without
  a Sources list, even when retrieval returned a near-miss chunk." (§14 changelog: one line,
  v1.8, same style as the t01 entry.)
- M-2/M-4: comments only. M-5: add `refusal: false` to each listed fixture; behaviour unchanged.

## Files

**Modify** `MessageBubble/Component.tsx`, `MessageBubble/Component.test.tsx`, `lib/copy.ts`,
`ContentListScreen/Component.test.tsx`, `types/api/chat.ts`, `useChatStream.ts`, the three M-5
test files, `advisordesk-prd.md`.
**Authorised test amendments**: `ContentListScreen/Component.test.tsx:34` may pin the new full
sentence; the M-5 fixtures gain `refusal: false`. Nothing else in existing tests changes.

## Steps

RED (test-author):
- [ ] `MessageBubble/Component.test.tsx`: new case "renders no Sources region for a refusal even
  when citations are present (near miss)" — assistant message with `refusal: true` and ONE
  citation → `queryByRole('region', { name: SOURCES_LABEL })` is null AND the status region is
  present. Keep `:51` (non-refusal with citations still shows Sources) untouched.
- [ ] `ContentListScreen/Component.test.tsx:34`: pin the new sentence exactly.
- [ ] `pnpm test -- --run src/components/chat/MessageBubble src/components/content/ContentListScreen`
  → exactly 2 new failures; record output.

GREEN (implementer):
- [ ] Implement Interfaces incl. PRD + minors. `pnpm test -- --run` all green;
  `pnpm type-check`; `pnpm lint` — paste real output.
- [ ] Commit: `fix(client): a refusal renders no Sources; home subtitle names the library (vrf t02)`.
  Stage only your paths.

## Acceptance

A refusal with a near-miss citation renders the warning Alert and no `region` named Sources; a
grounded answer still lists its Sources; the home page subtitle lists the seven topics.
