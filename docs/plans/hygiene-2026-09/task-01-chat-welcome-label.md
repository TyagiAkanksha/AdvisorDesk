---
id: hy-t01
phase: hygiene-2026-09
depends_on: []
status: todo
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: sonnet
---

# Task 01 — Chat welcome region gets its own label; one `hasConversation` expression

## Goal

Close two t24 Minors in `apps/client`:

- **t24 M3 (plan-mandated):** "welcome region label echoes the h1". `ChatWelcome` renders
  `<Box role="region" aria-label={CHAT_TITLE}>` — the same string as the page's `h1`
  ("Ask a question"), so a screen-reader user hears the same name twice for two different
  things. The region is the suggested-questions block, so name it that.
- **t24 M4:** "two expressions for one condition in ChatScreen". `ChatScreen` computes
  `hasConversation = messages.length > 0` and then still uses `messages.length === 0` and
  `messages.length > 0` inline in two places. Use the one derived boolean everywhere.

No visual change. No new copy other than one constant.

## Context (read ONLY these)

- `apps/client/src/components/chat/ChatScreen/components/ChatWelcome/{Component.tsx, Component.test.tsx, interface.ts}`
- `apps/client/src/components/chat/ChatScreen/Component.tsx` (lines 26–27 and 40, 88 at the time of writing)
- `apps/client/src/components/chat/ChatScreen/Component.test.tsx` — grep it for `'Ask a question'`
  region queries before changing anything (a `getByRole('region', { name: 'Ask a question' })`
  there would be a pin to rewrite; at the time of writing there is none — confirm).
- `apps/client/src/lib/copy.ts` — the chat block (`CHAT_TITLE`, `CHAT_DESCRIPTION`, `SUGGESTED_QUESTIONS`, …).
- `docs/FRONTEND-CONVENTIONS.md` §3, §7, §9.

## Files

**Modify**
- `apps/client/src/lib/copy.ts` — add one constant.
- `apps/client/src/components/chat/ChatScreen/components/ChatWelcome/Component.tsx`
- `apps/client/src/components/chat/ChatScreen/components/ChatWelcome/Component.test.tsx` (pin rewrite, named below)
- `apps/client/src/components/chat/ChatScreen/Component.tsx`

## Interfaces

```ts
// apps/client/src/lib/copy.ts — add directly under SUGGESTED_QUESTIONS
/** Accessible name of the welcome block's suggested-questions region (p8 t24 M3). */
export const SUGGESTED_QUESTIONS_LABEL = 'Suggested questions';
```

`ChatWelcomeProps` is unchanged (`{ onAsk: (question: string) => void }`).

## Steps

- [ ] **Step 1 (test-author, RED): rewrite the ChatWelcome pin.** In
  `ChatWelcome/Component.test.tsx`, change the region query and add the negative assertion:

  ```tsx
  expect(screen.getByRole('region', { name: 'Suggested questions' })).toBeInTheDocument();
  // t24 M3: the region must NOT reuse the page heading's name.
  expect(screen.queryByRole('region', { name: 'Ask a question' })).not.toBeInTheDocument();
  ```

  Keep every other assertion in that test verbatim (no heading, description text, four buttons,
  click sends the first suggested question).

- [ ] **Step 2 (test-author, RED): pin the single-expression rule in ChatScreen.** Create
  `ChatScreen/source.test.ts` (a **node-environment** file — not inside the jsdom
  `Component.test.tsx`: Vite rewrites the literal `new URL('./x', import.meta.url)` pattern
  into an asset URL, so resolve the path with `fileURLToPath` instead):

  ```ts
  import { readFileSync } from 'node:fs';
  import { dirname, join } from 'node:path';
  import { fileURLToPath } from 'node:url';
  import { describe, expect, it } from 'vitest';

  const SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'Component.tsx'), 'utf8');

  describe('ChatScreen source', () => {
    it('derives the conversation state once (no inline messages.length checks)', () => {
      expect(SOURCE).toContain('const hasConversation = messages.length > 0;');
      expect(SOURCE).not.toMatch(/messages\.length === 0/);
      expect(SOURCE).not.toMatch(/showNewConversation=\{messages\.length > 0\}/);
    });
  });
  ```

  *(Controller amendment during execution: the original step put this pin inside the jsdom
  test file with `new URL(...)`, which throws `The URL must be of scheme file`.)*

- [ ] **Step 3: run RED.** `cd apps/client && npx vitest run ChatWelcome ChatScreen` → the
  rewritten region test fails on `name: 'Suggested questions'`; the source pin fails on
  `messages.length === 0`. Paste both failure lines in the report.

- [ ] **Step 4 (implementer, GREEN):**
  - `copy.ts`: add `SUGGESTED_QUESTIONS_LABEL` exactly as in Interfaces.
  - `ChatWelcome/Component.tsx`: import `SUGGESTED_QUESTIONS_LABEL` (drop the now-unused
    `CHAT_TITLE` import); `<Box role="region" aria-label={SUGGESTED_QUESTIONS_LABEL}>`. Update
    the header comment's last paragraph: "p8 t24 M3 / hygiene t01: the region is named for its
    content ("Suggested questions"), not for the page heading it used to echo."
  - `ChatScreen/Component.tsx`: replace `{messages.length === 0 ? (` with
    `{hasConversation ? (` **and swap the two branches** so the map comes first and
    `<ChatWelcome onAsk={send} />` second (keep the index-as-key comment with the map);
    replace `showNewConversation={messages.length > 0}` with
    `showNewConversation={hasConversation}`.

- [ ] **Step 5: run GREEN + gates.** `cd apps/client && npx vitest run ChatWelcome ChatScreen`
  (all green), then `pnpm -C apps/client type-check && pnpm -C apps/client lint &&
  pnpm -C apps/client format:check` (if `format:check` does not exist, run
  `npx prettier --check src`).

- [ ] **Step 6: commit.** `git commit -m "refactor(client): name the chat welcome region for its content; single hasConversation (p8 t24 M3/M4)"`

## Acceptance criteria

- `ChatWelcome` region accessible name is exactly `Suggested questions`; no element on `/chat`
  has the accessible name `Ask a question` other than the `h1` and the nav link.
- `ChatScreen/Component.tsx` contains exactly one `messages.length` expression (the
  `hasConversation` declaration) besides `messages[messages.length - 1]` in `awaitingFirstToken`.
- Full client suite green; type-check, lint, prettier clean.

## Report

Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-01-test-author.md` (RED evidence);
implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-01-implementer.md` (GREEN + gates
evidence, commit hashes, concerns).
