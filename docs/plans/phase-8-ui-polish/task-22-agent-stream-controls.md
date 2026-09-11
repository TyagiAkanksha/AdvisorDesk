---
id: p8-t22
phase: phase-8-ui-polish
depends_on: [p8-t14]
status: done
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 22 — `useAgentStream`: `stop()`, `reset()`, text offsets + `turnSegments` (C7, hook half)

## Goal

Give the agent panel's hook the two controls task 23's header/composer need — stop the
in-flight stream (keeping what arrived) and clear the conversation — and record, on every tool
event, how much assistant text had arrived when it did, so the panel can render tool cards
**between** the text segments they interrupted (DESIGN.md §C7 "in arrival order interleaved
with text segments"). A pure `turnSegments(turn)` helper turns a turn into that ordered list
and pairs each `tool_call` with its `tool_result`. No UI changes here.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §5 C7 (Turns and Stop bullets).
- `docs/FRONTEND-CONVENTIONS.md` §3, §6, §7.
- `apps/admin/src/components/agent/useAgentStream.ts` — whole file: `ToolEvent`, `AgentTurn`,
  `appendAssistantToken`/`appendAssistantEvent`, the `AbortController` + `streamingRef`/
  `turnsRef` pattern (abort is NOT surfaced as an error; `finally` flips `streaming`).
- `apps/admin/src/components/agent/useAgentStream.test.tsx` (helpers `sseBody`,
  `streamResponse`, `Wrapper`; test 1's `expectedEvents` block is the one pin rewritten) and
  `useAgentStream.guards.test.tsx` (unchanged — its `events: []` pins are unaffected).
- `apps/client/src/components/chat/useChatStream.ts` lines for `stop`/`reset` (sub-phase B
  task 11 — same shape, minus the session id) — read-only reference.

## Files

**Create**
- `src/lib/agentTurnSegments.ts`, `src/lib/agentTurnSegments.test.ts`

**Modify**
- `src/components/agent/useAgentStream.ts`
- `src/components/agent/useAgentStream.test.tsx` (one pin amended + cases appended)

## Interfaces

```ts
// useAgentStream.ts
export interface ToolEvent {
  kind: 'call' | 'result';
  tool: string;
  detail: string;
  /** Length of the assistant turn's `text` at the moment this event arrived — lets the renderer
   * place the card between the text that preceded it and the text that followed (phase-8 t22). */
  textOffset: number;
}
export interface UseAgentStreamResult {
  turns: AgentTurn[];
  streaming: boolean;
  error: string | null;
  send: (text: string) => void;
  /** Abort the in-flight request; whatever arrived stays; no error; no-op when idle. */
  stop: () => void;
  /** Stop if streaming, then clear turns and error. */
  reset: () => void;
}
// appendAssistantEvent computes textOffset from the in-progress assistant turn's current text
// length (0 when it has to start a new assistant turn).

// src/lib/agentTurnSegments.ts — pure
export interface TextSegment { kind: 'text'; text: string }
export interface ToolSegment {
  kind: 'tool';
  tool: string;
  /** The call's `detail` (compact JSON of the arguments); '' for a result with no matching call. */
  args: string;
  /** The result's `detail` (result_summary), or null while the call is still running. */
  result: string | null;
}
export type TurnSegment = TextSegment | ToolSegment;
/**
 * Walk `turn.events` in order. A 'call' closes the current text run at `event.textOffset`
 * (emitting a text segment if non-empty), then opens a tool segment. A 'result' fills the
 * EARLIEST still-open tool segment with the same `tool` (FIFO — results arrive in execution
 * order); a result with no open call cuts the text at ITS offset and opens its own segment with
 * `args: ''`. Trailing text after
 * the last cut becomes the final text segment. A turn with no events → [{ kind: 'text', text }]
 * (or [] when text is ''). Text between a call and its result is attributed AFTER the card.
 */
export function turnSegments(turn: AgentTurn): TurnSegment[];
```

**`stop`/`reset` implementation (exact):**

```ts
const stop = useCallback(() => {
  abortControllerRef.current?.abort();
}, []);

const reset = useCallback(() => {
  abortControllerRef.current?.abort();
  setError(null);
  setTurnsState(() => []);
}, [setTurnsState]);
```

`setTurnsState(() => [])` keeps `turnsRef` in sync (the ref is what the next `send` resends).

## Steps (TDD)

- [ ] **RED — test-author.**

**`src/lib/agentTurnSegments.test.ts`** (node)

```ts
import { describe, expect, it } from 'vitest';

import type { AgentTurn } from '@/components/agent/useAgentStream';

import { turnSegments } from './agentTurnSegments';

const args = JSON.stringify({ title: 'Roth IRA Conversion Basics' });

describe('turnSegments', () => {
  it('interleaves text and a paired call/result at the recorded offset', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: 'Creating the draft. Done.',
      events: [
        { kind: 'call', tool: 'create_draft', detail: args, textOffset: 20 },
        { kind: 'result', tool: 'create_draft', detail: 'Created d-42.', textOffset: 20 },
      ],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'text', text: 'Creating the draft. ' },
      { kind: 'tool', tool: 'create_draft', args, result: 'Created d-42.' },
      { kind: 'text', text: 'Done.' },
    ]);
  });

  it('a call without a result yet is an open tool segment', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: '',
      events: [{ kind: 'call', tool: 'search_content', detail: '{"q":"roth"}', textOffset: 0 }],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'tool', tool: 'search_content', args: '{"q":"roth"}', result: null },
    ]);
  });

  it('pairs results FIFO when the same tool is called twice', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: '',
      events: [
        { kind: 'call', tool: 'publish', detail: '{"id":"a"}', textOffset: 0 },
        { kind: 'call', tool: 'publish', detail: '{"id":"b"}', textOffset: 0 },
        { kind: 'result', tool: 'publish', detail: 'Published a', textOffset: 0 },
        { kind: 'result', tool: 'publish', detail: 'Published b', textOffset: 0 },
      ],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'tool', tool: 'publish', args: '{"id":"a"}', result: 'Published a' },
      { kind: 'tool', tool: 'publish', args: '{"id":"b"}', result: 'Published b' },
    ]);
  });

  it('a result with no matching call still renders as a tool segment', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: 'Hi',
      events: [{ kind: 'result', tool: 'orphan', detail: 'ok', textOffset: 2 }],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'text', text: 'Hi' },
      { kind: 'tool', tool: 'orphan', args: '', result: 'ok' },
    ]);
  });

  it('text-only and empty turns', () => {
    expect(turnSegments({ role: 'assistant', text: 'Just text.', events: [] })).toEqual([
      { kind: 'text', text: 'Just text.' },
    ]);
    expect(turnSegments({ role: 'assistant', text: '', events: [] })).toEqual([]);
    expect(turnSegments({ role: 'user', text: 'Hello', events: [] })).toEqual([
      { kind: 'text', text: 'Hello' },
    ]);
  });
});
```

**`useAgentStream.test.tsx`** — amend test 1's `expectedEvents` to carry the offset
(`'Creating ' + 'the draft. '` = 20 characters had arrived when both events landed):

```tsx
    const expectedEvents: ToolEvent[] = [
      { kind: 'call', tool: 'create_draft', detail: JSON.stringify(argumentsFixture), textOffset: 20 },
      { kind: 'result', tool: 'create_draft', detail: resultSummary, textOffset: 20 },
    ];
```

and append (a gated stream helper mirroring `AgentPanel/Component.test.tsx`'s
`gatedStreamResponse` — copy it in):

```tsx
  it('stop() aborts the in-flight stream, keeps the partial turn, sets no error, and ends streaming', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Partial ' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => result.current.send('Q'));
    await waitFor(() => expect(result.current.streaming).toBe(true));

    act(() => result.current.stop());
    release();

    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.turns[0]).toEqual({ role: 'user', text: 'Q', events: [] });
  });

  it('stop() is a no-op when idle', () => {
    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });

    expect(() => act(() => result.current.stop())).not.toThrow();
    expect(result.current.streaming).toBe(false);
  });

  it('reset() clears turns and error, and the next send() resends an empty history', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Hi' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Again' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => result.current.send('First'));
    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.turns).toHaveLength(2);

    act(() => result.current.reset());
    expect(result.current.turns).toEqual([]);
    expect(result.current.error).toBeNull();

    act(() => result.current.send('Second'));
    await waitFor(() => expect(result.current.streaming).toBe(false));
    const body = JSON.parse((fetchMock.mock.calls[1]?.[1] as RequestInit).body as string) as {
      messages: unknown[];
    };
    expect(body.messages).toEqual([{ role: 'user', content: 'Second' }]);
  });

  it('reset() while streaming aborts first and leaves no turns behind', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Partial ' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => result.current.send('Q'));
    await waitFor(() => expect(result.current.streaming).toBe(true));

    act(() => result.current.reset());
    release();

    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.turns).toEqual([]);
    expect(result.current.error).toBeNull();
  });
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- useAgentStream agentTurnSegments` →
  `lib/agentTurnSegments` unresolved; amended test 1 fails (`textOffset` missing); the four
  new cases fail (`stop`/`reset` undefined); `pnpm -C apps/admin type-check` flags
  `textOffset` on `ToolEvent`; `guards.test.tsx` stays green.

- [ ] **GREEN — implementer:** `textOffset` in `appendAssistantEvent` → `stop`/`reset` →
  `agentTurnSegments.ts`. Keep the unmount-abort effect and the re-entrancy guard intact.

- [ ] **Run GREEN:** `pnpm -C apps/admin test -- useAgentStream agentTurnSegments AgentPanel`
  (AgentPanel's existing pins must still pass — the extra event field is invisible to them);
  full suite; `pnpm -C apps/admin type-check`.

- [ ] **Gates:** `pnpm gates:admin` → clean. No screenshots (hook only).

- [ ] **Commit:**
  `git add apps/admin/src/components/agent/useAgentStream.ts apps/admin/src/components/agent/useAgentStream.test.tsx apps/admin/src/lib/agentTurnSegments.ts apps/admin/src/lib/agentTurnSegments.test.ts`
  `git commit -m "feat(admin): useAgentStream stop/reset, tool-event text offsets, turnSegments (p8 t22)"`

## Verify

```bash
pnpm -C apps/admin test -- useAgentStream agentTurnSegments AgentPanel
pnpm gates:admin
```

## Acceptance

- `stop` keeps the partial turn and raises no error; `reset` clears turns/error and the next
  `send` resends an empty history; both guarded when idle.
- Every `ToolEvent` carries `textOffset`; `turnSegments` pairs FIFO and interleaves at offsets
  (five node cases green); existing AgentPanel pins untouched and green.
