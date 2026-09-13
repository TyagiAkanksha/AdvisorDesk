---
id: p9-t17
phase: phase-9-eval-data-loop
depends_on: [p9-t02]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 17 — 👍/👎 under assistant answers: the only human signal in the loop

## Goal

A client can rate an answer, and the rating reaches `chat_messages.feedback`. DESIGN §A/D2: this is
the **only human ground truth** in the loop and the one control the audience can click during the
demo (beat 5). Task 02 already shipped `POST /api/v1/public/chat/{message_id}/feedback` and both
apps' generated types; the wire is unchanged here, so **no baseline or codegen is regenerated in
this task**. What is missing is entirely client-side:

1. `useChatStream` **stops discarding `message_id`** — it is destructured away at
   `apps/client/src/components/chat/useChatStream.ts:481` (`onDone: ({ session_id }) => {...}`),
   even though `SseHandlers.onDone` has typed it since phase 4 (line 40). It becomes
   `ChatMessage.messageId`, the capability the feedback call needs.
2. A dumb `FeedbackButtons` leaf (two icon buttons, `aria-pressed`, accessible names from
   `lib/copy`).
3. A network edge in `lib` (`sendMessageFeedback`) plus a colocated VM hook
   (`useMessageFeedback`) holding per-message state with an optimistic update and a revert on
   failure.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Part A" (the `feedback` row: nullable so "never
  asked" ≠ "neutral"; "the SSE `done` event already carries `message_id`… the client types and
  discards it"), D2, D6 beat 5, §"Execution order" step 8.
- `docs/plans/phase-9-eval-data-loop/task-02-feedback-endpoint.md` §Interfaces — the wire table
  (204 / 404 / 422, last-write-wins) this UI consumes, and the "NOT rate-limited" ruling (so
  repeated clicks are safe).
- `docs/FRONTEND-CONVENTIONS.md` — §3 (folder-per-component; `Component.tsx` is always
  `export default function Component(props)`; no inline Props; components are dumb; VM hooks flat
  and colocated), §4 (`common/` is the only place that imports `@mui/*`; grow it on demand),
  §5 (`src/types/` is the only layer touching `components['schemas'][...]`), §7 (vitest,
  `// @vitest-environment jsdom` as the literal first line, `globals: false`, colocated, import
  through the barrel, **drive real user interactions with `user-event`**, mock ONLY the network
  edge), §8 (prettier keys), §9 (icon-only buttons get `aria-label`; copy from one typed module).
- `apps/client/src/components/chat/useChatStream.ts` — the whole file. Specifically: `ChatMessage`
  (23-30), `SseHandlers.onDone` (40), `dispatchFrame`'s `done` case (127-129),
  `DEV_FALLBACK_API_URL`/`resolveApiBaseUrl` (238-249), the `attachCitations` pure helper
  (350-356) this task's new helper mirrors, and the `onDone` handler at 481-485 — **the discard
  site**.
- `apps/client/src/components/chat/MessageBubble/Component.tsx` (the assistant branch, 50-82) and
  `interface.ts`.
- `apps/client/src/components/chat/ChatScreen/Component.tsx` (23-93; the `messages.map` at 40-49).
- `apps/client/src/components/common/IconButton/{Component.tsx,interface.ts}` and its
  `Component.test.tsx` (which must stay green).
- `apps/client/src/components/common/Icon/Component.tsx` — the explicit `ICONS` registry and the
  comment explaining why it is explicit.
- `apps/client/src/lib/copy.ts` (the whole file — where the two labels go).
- `apps/client/src/types/api/chat.ts` + `apps/client/src/types/index.ts` — the Dto/alias barrel
  pattern.
- `apps/client/src/types/generated/schema.d.ts` — confirm (do not edit) that task 02's codegen is
  already present: the `"/api/v1/public/chat/{message_id}/feedback"` path, the
  `ChatFeedbackRequest` schema with `value: -1 | 1`, and the `public_chat_feedback` operation.
- `apps/client/src/components/chat/useChatStream.test.ts` — its SSE fixture helpers
  (`sseBody`/`streamResponse`, 55-141) to copy, and lines 272 / 583 / 558 / 600 / 639: every
  `toEqual` over `messages` is on a **user-only or empty** array, which is why adding `messageId`
  to assistant messages leaves this file green. **Verify that claim before writing code; do not
  edit this file.**
- `apps/client/src/lib/publicApi.test.ts` — the `vi.stubGlobal('fetch', ...)` idiom for testing a
  `lib` fetch helper.

## Files

**Create**
- `apps/client/src/lib/browserApiBase.ts`
- `apps/client/src/lib/feedbackApi.ts`
- `apps/client/src/lib/feedbackApi.test.ts`
- `apps/client/src/components/chat/FeedbackButtons/Component.tsx`
- `apps/client/src/components/chat/FeedbackButtons/interface.ts`
- `apps/client/src/components/chat/FeedbackButtons/index.ts`
- `apps/client/src/components/chat/FeedbackButtons/Component.test.tsx`
- `apps/client/src/components/chat/useMessageFeedback.ts`
- `apps/client/src/components/chat/useMessageFeedback.test.ts`
- `apps/client/src/components/chat/useChatStream.feedback.test.ts`
- `apps/client/src/components/chat/ChatScreen/feedback.test.tsx`

**Modify**
- `apps/client/src/components/chat/useChatStream.ts`
- `apps/client/src/components/chat/MessageBubble/Component.tsx`
- `apps/client/src/components/chat/MessageBubble/interface.ts`
- `apps/client/src/components/chat/ChatScreen/Component.tsx`
- `apps/client/src/components/common/IconButton/Component.tsx`
- `apps/client/src/components/common/IconButton/interface.ts`
- `apps/client/src/components/common/Icon/Component.tsx`
- `apps/client/src/lib/copy.ts`
- `apps/client/src/types/api/chat.ts`
- `apps/client/src/types/index.ts`

**Regenerate:** nothing. No route, DTO or tool changes here — `openapi.json`, both `schema.d.ts`
and `mcp-tools.json` must all be byte-identical at the end of this task (CONVENTIONS §8 only bites
when the wire moves). `apps/admin` is not touched at all.

## Interfaces

### `src/types/api/chat.ts` (append)

```ts
// phase-9 task-17 (DESIGN §A/D2): `POST /public/chat/{message_id}/feedback`'s body — a real
// Pydantic schema, so it comes from the generated OpenAPI types like every other wire type
// (docs/FRONTEND-CONVENTIONS.md §5), not hand-authored like `Citation` above.
export type ChatFeedbackRequestDto = components['schemas']['ChatFeedbackRequest'];
export type ChatFeedbackRequest = ChatFeedbackRequestDto;
/** `-1 | 1` — the endpoint's whole value domain. `0` is deliberately illegal (task 02): a row with
 *  no feedback stays NULL, so "never asked" and "asked, felt neutral" are never conflated. */
export type ChatFeedbackValue = ChatFeedbackRequestDto['value'];
```

Barrel (`src/types/index.ts`): extend the existing chat export line to
`export type { ChatFeedbackRequest, ChatFeedbackRequestDto, ChatFeedbackValue, ChatRequest,
ChatRequestDto, Citation, CitationDto } from './api/chat';`.

### `src/lib/browserApiBase.ts` (extracted, not reinvented)

`useChatStream`'s private `resolveApiBaseUrl` (lines 240-249) is now needed by a second
browser-side caller, so it moves to `lib` **verbatim** — same `NEXT_PUBLIC_API_URL` read, same
`DEV_FALLBACK_API_URL = 'http://localhost:8000'`, same production throw — exported as
`resolveBrowserApiBaseUrl()`, and `useChatStream.ts` imports it instead of declaring it.

Keep the whole existing comment block (it explains why this is `NEXT_PUBLIC_`-prefixed while
`lib/publicApi.ts`'s is not) and add one line: the function is deliberately **not** merged with
`publicApi.ts`'s identical-looking `resolveApiBaseUrl` — that one reads the server-only `API_URL`
for RSC fetches; the two differ in which env var they may read, and merging them would let a
server-only value leak into a browser bundle path or vice versa.

### `src/lib/feedbackApi.ts`

```ts
/**
 * The network edge for `POST /api/v1/public/chat/{message_id}/feedback` (phase-9 DESIGN §A/D2).
 *
 * A plain async function, not a hook and not RTK Query: `apps/client` uses RSC + hand-rolled
 * hooks and has no RTK store (docs/FRONTEND-CONVENTIONS.md §6). The one thing this module owns is
 * "what goes on the wire"; all state, optimism and error copy live in `useMessageFeedback`.
 *
 * @throws Error on any non-2xx response — including the 404 a pruned/unknown `message_id` gives.
 *   The caller turns that into friendly copy (§9: raw bodies are never rendered); this function
 *   deliberately does not read the body, since 204 has none and the failure modes here are not
 *   user-actionable.
 */
export async function sendMessageFeedback(
  messageId: string,
  value: ChatFeedbackValue,
): Promise<void> {
  const body: ChatFeedbackRequest = { value };
  const response = await fetch(
    `${resolveBrowserApiBaseUrl()}/api/v1/public/chat/${encodeURIComponent(messageId)}/feedback`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    throw new Error(`Feedback request failed: ${response.status}`);
  }
}
```

### `src/components/chat/useChatStream.ts` (three small edits)

1. `ChatMessage` gains:

```ts
  /**
   * The server-minted `chat_messages.id` from this turn's `done` event — the only capability
   * needed to rate the answer (phase-9 DESIGN §A: "no wire change"). `undefined` until `done`
   * lands, and on every user turn.
   */
  messageId?: string;
```

2. A new pure helper beside `attachCitations`, same shape and same "start an assistant turn if
   there isn't one" defensiveness rationale (M-7's precedent):

```ts
/** Attach the server's message id to the in-progress assistant message. Pure. */
function attachMessageId(messages: ChatMessage[], messageId: string): ChatMessage[] {
  const last = messages[messages.length - 1];
  if (last !== undefined && last.role === 'assistant') {
    return [...messages.slice(0, -1), { ...last, messageId }];
  }
  return messages;
}
```

   (Unlike `attachCitations` this one returns `messages` unchanged when there is no assistant turn:
   an id with no bubble to hang it on has nothing to render — creating an empty bubble for it would
   invent UI, where `attachCitations` had a real refusal to show.)

3. `onDone` keeps both fields:

```ts
            onDone: ({ session_id, message_id }) => {
              applyIfNotAborted(() => {
                persistSessionId(session_id);
                setMessages((prev) => attachMessageId(prev, message_id));
              });
            },
```

Everything else in the file is untouched, `resolveApiBaseUrl`'s body excepted (now imported).

### `src/components/chat/useMessageFeedback.ts` (the VM hook)

```ts
export interface UseMessageFeedbackResult {
  /** What this message currently shows — optimistic while a request is in flight. */
  valueFor: (messageId: string) => ChatFeedbackValue | null;
  /** True while this message's request is in flight; both of its buttons disable. */
  pendingFor: (messageId: string) => boolean;
  /** Friendly copy for the last failed submission, or `null`. */
  error: string | null;
  /** Record 👍/👎 for one message. No-op while that message already has a request in flight. */
  select: (messageId: string, value: ChatFeedbackValue) => void;
}

export function useMessageFeedback(): UseMessageFeedbackResult;
```

Behaviour (all pinned by the tests):

- Two `useState` records keyed by `messageId` (`values`, `pending`) plus one `error` string.
- `select` applies the value **before** the request (optimistic), marks the message pending, and on
  rejection restores the value the message had *before this click* (which may be a previous
  thumbs-up, not just `null`) and sets `error` to `GENERIC_ERROR_MESSAGE` from `lib/copy`.
- A successful request clears `error` (so a later success removes a stale banner) and clears
  pending.
- Per-message state, not one global "submitted" flag: a transcript has many answers and the demo
  rates more than one.
- **Why this state is not in `useChatStream`:** `messageId` belongs to the stream (it arrives on
  the stream's own `done` event), but the optimistic value and its revert belong to the feedback
  request. Putting them in `useChatStream` would make the stream hook import the feedback endpoint
  and own a second network lifecycle — the tight coupling FRONTEND-CONVENTIONS §4 forbids. The two
  meet in `ChatScreen`, which is the composition point.

### `src/components/chat/FeedbackButtons/` (dumb leaf)

```ts
// interface.ts
export interface FeedbackButtonsProps {
  /** The current rating, or `null` when the reader hasn't rated this answer. */
  value: ChatFeedbackValue | null;
  /** Disables both buttons (a request for this message is in flight). */
  disabled?: boolean;
  onSelect: (value: ChatFeedbackValue) => void;
}
```

`Component.tsx`: a `common/Stack` (`direction="row"`) of two `common/IconButton`s —
`name="ThumbUpAltOutlined"` / `"ThumbDownAltOutlined"`, `size="small"`,
`label={FEEDBACK_UP_LABEL}` / `{FEEDBACK_DOWN_LABEL}`, `pressed={value === 1}` / `{value === -1}`,
`color={value === 1 ? 'primary' : 'default'}` (and likewise for −1),
`onClick={() => onSelect(1)}` / `{() => onSelect(-1)}`, `disabled={disabled}`. No state, no
fetching, no conditional on `role` — the parent decides whether to render it at all.

### `src/components/common/` (two additive primitive changes)

- `IconButton`: `interface.ts` gains
  `/** Toggle state for a button that represents an on/off choice — renders `aria-pressed`
  (FRONTEND-CONVENTIONS §9: an assistive-tech user must be able to tell which thumb is chosen).
  Omit for a plain action button. */ pressed?: boolean;`, and `Component.tsx` destructures it and
  passes `aria-pressed={pressed}` to `MuiIconButton`. Optional, so the existing
  `IconButton/Component.test.tsx` stays green — verify.
- `Icon`: add `ThumbDownAltOutlined` and `ThumbUpAltOutlined` to the explicit `ICONS` registry
  (named imports from `@mui/icons-material/ThumbUpAltOutlined` / `.../ThumbDownAltOutlined` —
  both exist in the pinned `@mui/icons-material@^9.2.0`), keeping the registry alphabetical and the
  "explicit registry, NOT `import *`" comment intact.

### `src/lib/copy.ts` (append)

```ts
// phase-9 task-17 (DESIGN §A/D2): the 👍/👎 control under an assistant answer. Accessible names,
// not decoration — they are what a screen-reader user hears and what the tests query by.
export const FEEDBACK_UP_LABEL = 'Helpful';
export const FEEDBACK_DOWN_LABEL = 'Not helpful';
```

### `MessageBubble` (one optional prop, still dumb)

```ts
// interface.ts
export interface MessageBubbleProps {
  message: ChatMessage;
  /**
   * Rendered as the 👍/👎 control under an assistant answer, when the parent has an id to rate
   * (phase-9 task-17). One grouped prop rather than three loose ones: they are meaningless apart,
   * and `undefined` is the single "this turn is not rateable" signal.
   */
  feedback?: {
    value: ChatFeedbackValue | null;
    disabled: boolean;
    onSelect: (value: ChatFeedbackValue) => void;
  };
}
```

In `Component.tsx`'s assistant branch only, inside the `Paper`/`Alert` after `{answer}`:
`{feedback !== undefined && <FeedbackButtons value={feedback.value} disabled={feedback.disabled}
onSelect={feedback.onSelect} />}`. The user branch ignores the prop entirely.

### `ChatScreen` (the composition point)

```tsx
  // added beside the existing `useChatStream()` / `useChatComposer()` calls (lines 24-25)
  const feedback = useMessageFeedback();

  // the existing `hasConversation ? messages.map(...) : <ChatWelcome/>` block (lines 40-52),
  // with the map body replaced by:
        messages.map((message, index) => {
          const messageId = message.messageId;
          return (
            <MessageBubble
              key={index}
              message={message}
              feedback={
                message.role === 'assistant' && messageId !== undefined
                  ? {
                      value: feedback.valueFor(messageId),
                      disabled: feedback.pendingFor(messageId),
                      onSelect: (value) => feedback.select(messageId, value),
                    }
                  : undefined
              }
            />
          );
        })
```

and, beside the existing stream-error `Alert`, surface `feedback.error` the same friendly way:
`{feedback.error !== null && <Alert severity="error">{feedback.error}</Alert>}` — a failed rating
must not look like a failed answer, and §9 forbids a silent swallow. No `retry` action on it: the
reader can simply click the thumb again.

The index-as-key comment at lines 42-47 stays accurate (this change appends a field to an existing
index, it never reorders) — say so in the report rather than editing the comment.

## Steps (TDD)

- [ ] **RED — test-author, 1/5.** `apps/client/src/lib/feedbackApi.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';

import { sendMessageFeedback } from './feedbackApi';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('sendMessageFeedback', () => {
  it('POSTs the value as JSON to the message feedback endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await sendMessageFeedback('11111111-2222-3333-4444-555555555555', -1);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(
      '/api/v1/public/chat/11111111-2222-3333-4444-555555555555/feedback',
    );
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'content-type': 'application/json' });
    expect(JSON.parse(init.body as string)).toEqual({ value: -1 });
  });

  it('rejects on a non-2xx response so the caller can revert its optimistic update', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 404 })));

    await expect(sendMessageFeedback('gone', 1)).rejects.toThrow(/404/);
  });
});
```

- [ ] **RED — test-author, 2/5.** `apps/client/src/components/chat/FeedbackButtons/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FeedbackButtons } from '.';

// phase-9 task-17 (DESIGN §A/D2). Dumb leaf: it renders the current rating and raises a choice.
// Queried by accessible name + `aria-pressed`, the two things a screen-reader user actually gets.

describe('FeedbackButtons', () => {
  it('renders both thumbs unpressed when nothing has been rated', () => {
    render(<FeedbackButtons value={null} onSelect={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Helpful', pressed: false })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Not helpful', pressed: false }),
    ).toBeInTheDocument();
  });

  it('reports 1 when the reader clicks thumbs up', async () => {
    const onSelect = vi.fn();
    render(<FeedbackButtons value={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole('button', { name: 'Helpful' }));

    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('reports -1 when the reader clicks thumbs down', async () => {
    const onSelect = vi.fn();
    render(<FeedbackButtons value={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole('button', { name: 'Not helpful' }));

    expect(onSelect).toHaveBeenCalledWith(-1);
  });

  it('marks only the chosen thumb as pressed', () => {
    render(<FeedbackButtons value={-1} onSelect={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Not helpful' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Helpful' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('disables both thumbs while a request is in flight', async () => {
    const onSelect = vi.fn();
    render(<FeedbackButtons value={null} disabled onSelect={onSelect} />);

    expect(screen.getByRole('button', { name: 'Helpful' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Not helpful' }));

    expect(onSelect).not.toHaveBeenCalled();
  });
});
```

- [ ] **RED — test-author, 3/5.** `apps/client/src/components/chat/useMessageFeedback.test.ts`:

```ts
// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GENERIC_ERROR_MESSAGE } from '@/lib/copy';

import { useMessageFeedback } from './useMessageFeedback';

// Only the network edge is mocked (docs/FRONTEND-CONVENTIONS.md §7) — the hook's own state machine
// is exercised for real.

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (reason?: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useMessageFeedback', () => {
  it('shows nothing rated and nothing pending before any click', () => {
    const { result } = renderHook(() => useMessageFeedback());

    expect(result.current.valueFor('m-1')).toBeNull();
    expect(result.current.pendingFor('m-1')).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('applies the rating optimistically and POSTs it once', async () => {
    const gate = deferred<Response>();
    const fetchMock = vi.fn().mockReturnValue(gate.promise);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMessageFeedback());
    act(() => result.current.select('m-1', 1));

    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.pendingFor('m-1')).toBe(true);

    await act(async () => {
      gate.resolve(new Response(null, { status: 204 }));
      await gate.promise;
    });

    await waitFor(() => expect(result.current.pendingFor('m-1')).toBe(false));
    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('reverts to the previous rating and shows friendly copy when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(null, { status: 204 }))
        .mockResolvedValueOnce(new Response('{}', { status: 404 })),
    );

    const { result } = renderHook(() => useMessageFeedback());

    act(() => result.current.select('m-1', 1));
    await waitFor(() => expect(result.current.pendingFor('m-1')).toBe(false));
    expect(result.current.valueFor('m-1')).toBe(1);

    act(() => result.current.select('m-1', -1));
    await waitFor(() => expect(result.current.pendingFor('m-1')).toBe(false));

    // Reverted to the value it had BEFORE the failed click — not to null.
    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.error).toBe(GENERIC_ERROR_MESSAGE);
  });

  it('clears a stale error once a later rating succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response('{}', { status: 500 }))
        .mockResolvedValueOnce(new Response(null, { status: 204 })),
    );

    const { result } = renderHook(() => useMessageFeedback());

    act(() => result.current.select('m-1', -1));
    await waitFor(() => expect(result.current.error).toBe(GENERIC_ERROR_MESSAGE));

    act(() => result.current.select('m-2', 1));
    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.valueFor('m-2')).toBe(1);
  });

  it('keeps each message independent and ignores a second click while one is in flight', async () => {
    const gate = deferred<Response>();
    const fetchMock = vi.fn().mockReturnValue(gate.promise);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMessageFeedback());

    act(() => result.current.select('m-1', 1));
    act(() => result.current.select('m-1', -1));

    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.valueFor('m-2')).toBeNull();
    expect(result.current.pendingFor('m-2')).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      gate.resolve(new Response(null, { status: 204 }));
      await gate.promise;
    });
  });
});
```

- [ ] **RED — test-author, 4/5.** `apps/client/src/components/chat/useChatStream.feedback.test.ts`
  — a NEW file (the pre-existing `useChatStream.test.ts` is not edited):

```ts
// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useChatStream } from './useChatStream';

// phase-9 task-17: the `done` event's `message_id` was typed and thrown away
// (`useChatStream.ts:481`). It is the capability the feedback endpoint needs, so it now lands on
// the assistant message.

function streamResponse(frames: { event: string; data: unknown }[]): Response {
  const body = frames
    .map((frame) => `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`)
    .join('');
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(body));
        controller.close();
      },
    }),
    { status: 200, headers: { 'content-type': 'text/event-stream' } },
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('useChatStream message ids', () => {
  it('keeps the done event message_id on the assistant turn it belongs to', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'RSUs vest on a schedule.' } },
          { event: 'citations', data: { citations: [{ content_id: 'c-1', title: 'T', slug: 't' }] } },
          { event: 'done', data: { session_id: 's-1', message_id: 'm-42' } },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('When do my RSUs vest?'));

    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.messages[0]?.role).toBe('user');
    expect(result.current.messages[0]?.messageId).toBeUndefined();
    expect(result.current.messages[1]?.role).toBe('assistant');
    expect(result.current.messages[1]?.messageId).toBe('m-42');
    expect(localStorage.getItem('advisordesk_session')).toBe('s-1');
  });

  it('leaves earlier turns alone when a second answer arrives', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          streamResponse([
            { event: 'token', data: { text: 'First.' } },
            { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
          ]),
        )
        .mockResolvedValueOnce(
          streamResponse([
            { event: 'token', data: { text: 'Second.' } },
            { event: 'done', data: { session_id: 's-1', message_id: 'm-2' } },
          ]),
        ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('one'));
    await waitFor(() => expect(result.current.streaming).toBe(false));
    act(() => result.current.send('two'));
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.messages.map((message) => message.messageId)).toEqual([
      undefined,
      'm-1',
      undefined,
      'm-2',
    ]);
  });
});
```

- [ ] **RED — test-author, 5/5.** `apps/client/src/components/chat/ChatScreen/feedback.test.tsx`
  — the integration the task exists for (a NEW file; the pre-existing `Component.test.tsx` is not
  edited):

```tsx
// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatScreen } from '.';

// phase-9 task-17 (DESIGN §A/D2, demo beat 5): the thumbs appear under a real assistant bubble in
// the real screen, and a click reaches the real endpoint. Only `fetch` is mocked.

function streamResponse(frames: { event: string; data: unknown }[]): Response {
  const body = frames
    .map((frame) => `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`)
    .join('');
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(body));
        controller.close();
      },
    }),
    { status: 200, headers: { 'content-type': 'text/event-stream' } },
  );
}

const ANSWER_FRAMES = [
  { event: 'token', data: { text: 'RSUs are taxed as ordinary income at vest.' } },
  { event: 'citations', data: { citations: [{ content_id: 'c-1', title: 'RSUs', slug: 'rsus' }] } },
  { event: 'done', data: { session_id: 's-1', message_id: 'm-7' } },
];

function mockChatThenFeedback(feedbackStatus: number) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    if (url.includes('/feedback')) {
      return Promise.resolve(new Response(null, { status: feedbackStatus }));
    }
    return Promise.resolve(streamResponse(ANSWER_FRAMES));
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}

async function ask(): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Message'), 'When do my RSUs vest?');
  await user.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Helpful' })).toBeInTheDocument());
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('ChatScreen feedback', () => {
  it('shows no thumbs before an answer has arrived', () => {
    mockChatThenFeedback(204);
    render(<ChatScreen />);

    expect(screen.queryByRole('button', { name: 'Helpful' })).not.toBeInTheDocument();
  });

  it('sends the rating for the answered message when a thumb is clicked', async () => {
    const { calls } = mockChatThenFeedback(204);
    render(<ChatScreen />);
    await ask();

    await userEvent.click(screen.getByRole('button', { name: 'Not helpful' }));

    await waitFor(() =>
      expect(calls.some((url) => url.includes('/api/v1/public/chat/m-7/feedback'))).toBe(true),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Not helpful' })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
  });

  it('reverts the thumb and shows a friendly notice when the rating fails', async () => {
    mockChatThenFeedback(404);
    render(<ChatScreen />);
    await ask();

    await userEvent.click(screen.getByRole('button', { name: 'Helpful' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Helpful' })).toHaveAttribute(
        'aria-pressed',
        'false',
      ),
    );
    expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();
  });
});
```

- [ ] **Run RED:** `cd apps/client && npx vitest run src/lib/feedbackApi.test.ts
  src/components/chat` → the four new files fail to resolve their imports
  (`FeedbackButtons`, `useMessageFeedback`, `feedbackApi`) and the `messageId` assertions fail on
  `undefined`. `pnpm -C apps/client type-check` fails on the same missing modules. Paste both.

- [ ] **GREEN — implementer, 1/4 (types + lib).** `src/types/api/chat.ts` + barrel;
  `src/lib/browserApiBase.ts` (moved verbatim); `src/lib/feedbackApi.ts`; `src/lib/copy.ts`
  labels. Point `useChatStream.ts` at the extracted resolver and delete its local copy.

- [ ] **GREEN — implementer, 2/4 (stream state).** `ChatMessage.messageId`, `attachMessageId`,
  the `onDone` change. Then run `npx vitest run src/components/chat/useChatStream.test.ts` —
  **every pre-existing test there must still pass untouched** (the `toEqual` audit in Context says
  it will; if one fails, stop and report rather than editing it).

- [ ] **GREEN — implementer, 3/4 (components).** `common/Icon` registry entries;
  `common/IconButton`'s `pressed`; the `FeedbackButtons` folder (Component/interface/index);
  `MessageBubble`'s optional `feedback` prop; `ChatScreen`'s composition + the error `Alert`.

- [ ] **GREEN — implementer, 4/4 (hook).** `useMessageFeedback.ts`.

- [ ] **Run GREEN:** `cd apps/client && npx vitest run` (the whole app suite, not just the new
  files).

- [ ] **Gates:**
  ```sh
  pnpm -C apps/client type-check && pnpm -C apps/client lint && pnpm -C apps/client format:check \
    && (cd apps/client && npx vitest run)
  pnpm -C apps/client build     # next build — the App Router production build
  git status --porcelain apps/api apps/admin   # MUST be empty: no wire change in this task
  ```

- [ ] **Commit:**
  `git add apps/client/src`
  `git commit -m "feat(client): thumbs up/down on assistant answers (p9 t17)"`

## Verify

```sh
cd /home/ak/Documents/github_akanksha/AdvisorDesk
pnpm -C apps/client type-check && pnpm -C apps/client lint && pnpm -C apps/client format:check
(cd apps/client && npx vitest run)
pnpm -C apps/client build
git diff --exit-code -- apps/api/openapi.json apps/client/src/types/generated/schema.d.ts
```

Manual check (optional, the demo path): with the API and client dev servers up, ask a question,
click 👎, then
`docker exec advisordesk-test-db psql -U postgres -d <dev db> -c "select id, feedback from
chat_messages where role='assistant' order by created_at desc limit 1"` — `feedback` is `-1`. Never
run this against prod data.

## Acceptance

- The `done` event's `message_id` lands on the assistant `ChatMessage` it belongs to and nowhere
  else; earlier turns keep their own ids; user turns have none.
- `FeedbackButtons` is dumb (props in, event out), both buttons have accessible names from
  `lib/copy`, and `aria-pressed` reflects the current rating; disabled blocks the click.
- A click POSTs `{"value": ±1}` exactly once to
  `/api/v1/public/chat/{message_id}/feedback`; the UI updates optimistically, reverts to the
  **previous** value on failure, and surfaces `GENERIC_ERROR_MESSAGE` (never a raw body);
  a later success clears that notice.
- Per-message state: rating one answer never changes another's; a second click during a pending
  request is a no-op.
- `apps/client` conventions hold: `common/` is still the only `@mui/*` importer; `src/types/` is
  still the only module touching `components['schemas']`; no inline Props; the new hook is flat and
  colocated; every new test drives `user-event` and mocks only `fetch`.
- `useChatStream.test.ts`, `MessageBubble/Component.test.tsx`, `ChatScreen/Component.test.tsx` and
  `IconButton/Component.test.tsx` all pass **untouched**.
- All four client gates plus `next build` pass; `apps/api` and `apps/admin` are untouched
  (`git status --porcelain` proves it).

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-17-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-17-implementer.md` — must
  state the exact before/after of the `onDone` discard site (`useChatStream.ts:481`), confirm the
  pre-existing client tests passed unedited, and confirm no baseline/codegen was regenerated
  (and why none was needed).
