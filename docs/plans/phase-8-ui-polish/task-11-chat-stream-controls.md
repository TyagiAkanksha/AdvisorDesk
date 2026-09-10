---
id: p8-t11
phase: phase-8-ui-polish
depends_on: [p8-t08]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 11 — `useChatStream`: `stop()`, `reset()`, `retry()` (apps/client, B4 hook half)

## Goal

Give the chat VM hook the three controls the new composer needs — stop the in-flight stream
(keeping the partial answer), start a new conversation (clear messages + the stored session),
and retry the last question after an error — with stream-fixture tests. No UI changes in this
task; task 12 wires the buttons.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §4 B4 (the `useChatStream` bullet and the Error
  bullet).
- `docs/FRONTEND-CONVENTIONS.md` §3 (VM hooks colocated, Args/Result in-file), §6 (streams:
  `fetch` + `ReadableStream`, `localStorage['advisordesk_session']`), §7.
- `apps/client/src/components/chat/useChatStream.ts` — read the whole file: `send()`'s
  re-entrancy guard (`streamingRef`), the per-request `AbortController` (`abortControllerRef`,
  aborted on unmount, abort is NOT surfaced as an error), `persistSessionId`/`readStoredSessionId`,
  `SESSION_STORAGE_KEY`, `UseChatStreamResult`.
- `apps/client/src/components/chat/useChatStream.test.ts` — the fixture helpers (`streamResponse`,
  gated streams) and the existing pins; reuse the helpers, do not restructure the file.
- `apps/client/src/components/chat/ChatScreen/Component.test.tsx` lines 1–60 — the
  `gatedStreamResponse` idea (a deferred promise keeps `streaming` true until released).

## Files

**Modify**
- `src/components/chat/useChatStream.ts`
- `src/components/chat/useChatStream.test.ts` (append)

## Interfaces

**Produces exactly:**

```ts
export interface UseChatStreamResult {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  send: (text: string) => void;
  /** Abort the in-flight request. The partial assistant message (if any) is kept as-is; no error is raised. No-op when idle. */
  stop: () => void;
  /** Start a new conversation: clear messages and error, forget the stored session id. Aborts first if streaming. */
  reset: () => void;
  /** After an error: drop the failed exchange (the last user message and any assistant message after it) and send that question again. No-op when there is no user message or while streaming. */
  retry: () => void;
}
```

**Implementation notes (`useChatStream.ts`):**
- `stop`: `useCallback(() => { abortControllerRef.current?.abort(); }, [])`. The existing
  `catch` already ignores our own aborts and the `finally` flips `streaming` false and clears
  the ref — so a stopped stream leaves whatever tokens arrived in place. Nothing else.
- `reset`: `stop()` then `setMessages([])`, `setError(null)`, and
  `clearStoredSessionId()` — a new helper beside `persistSessionId` that
  `localStorage.removeItem(SESSION_STORAGE_KEY)` inside the same try/catch shape
  (a throwing accessor degrades to a no-op, like the other two).
- `retry`: reads the current messages synchronously — keep a `messagesRef` mirror updated in an
  effect (`useEffect(() => { messagesRef.current = messages; }, [messages])`), same pattern as
  `streamingRef`. Find the index of the last `role === 'user'` message; if none or
  `streamingRef.current`, return. Otherwise `setMessages(prev => prev.slice(0, index))`, then
  `send(text)` (which appends the user turn again and clears `error`).
  `send`'s identity is stable, so `retry`'s deps are `[send]`.
- Return `{ messages, streaming, error, send, stop, reset, retry }`.

## Steps (TDD)

- [ ] **RED — test-author.** Append to `useChatStream.test.ts`, reusing that file's
  `streamResponse` helper and its `renderHook`/`act` imports (add a gated variant if the file
  has none — a `Promise` the test resolves to release `reader.read()`):

```ts
  it('stop() aborts the in-flight stream, keeps the partial assistant text, sets no error, and ends streaming', async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    // First frame arrives, then the reader blocks on `gate` until abort.
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: encode('event: token\ndata: {"text":"Partial "}\n\n') })
        .mockImplementationOnce(() => gate.then(() => ({ done: true, value: undefined }))),
      cancel: vi.fn(),
      releaseLock: vi.fn(),
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: { getReader: () => reader } }));

    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('Question?'));
    await waitFor(() => expect(result.current.messages[1]?.text).toBe('Partial '));
    expect(result.current.streaming).toBe(true);

    act(() => result.current.stop());
    release();

    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.messages[1]?.text).toBe('Partial ');
    expect(result.current.error).toBeNull();
  });

  it('stop() is a no-op when idle', () => {
    const { result } = renderHook(() => useChatStream());
    expect(() => act(() => result.current.stop())).not.toThrow();
    expect(result.current.streaming).toBe(false);
  });

  it("reset() clears messages and error and removes localStorage['advisordesk_session']", async () => {
    localStorage.setItem('advisordesk_session', 's-old');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Hi' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
        ]),
      ),
    );
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('Q'));
    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.messages).toHaveLength(2);
    expect(localStorage.getItem('advisordesk_session')).toBe('s-1');

    act(() => result.current.reset());

    expect(result.current.messages).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(localStorage.getItem('advisordesk_session')).toBeNull();
  });

  it('retry() after an HTTP error drops the failed exchange and re-sends the same question', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 429, json: async () => ({ error: { code: 'rate_limited', message: 'Slow down' } }) })
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Answer' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-2', message_id: 'm-2' } },
        ]),
      );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('Retry me'));
    await waitFor(() => expect(result.current.error).toBe('Slow down'));
    expect(result.current.messages).toEqual([{ role: 'user', text: 'Retry me' }]);

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.messages.map((m) => m.role)).toEqual(['user', 'assistant']);
    expect(result.current.messages[0]?.text).toBe('Retry me');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse((fetchMock.mock.calls[1]?.[1] as RequestInit).body as string)).toMatchObject({ message: 'Retry me' });
  });

  it('retry() is a no-op with no user message', () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.retry());
    expect(result.current.messages).toEqual([]);
  });
```

  (`encode` = `new TextEncoder().encode` — add a one-line helper if the file lacks one. If the
  429 fixture shape differs from what `friendlyErrorMessage` expects, mirror the file's existing
  429 test fixture exactly — the assertion is on the *message text*, whatever that fixture
  yields.)

- [ ] **Run RED:** `pnpm -C apps/client test -- useChatStream.test` → the five new cases FAIL
  (`stop`/`reset`/`retry` undefined; type-check fails on the new result fields).

- [ ] **GREEN — implementer:** implement per the notes; keep every existing test green
  (especially the unmount-abort and re-entrancy pins).

- [ ] **Run GREEN:** same; `pnpm -C apps/client type-check`; full suite.

- [ ] **Gates:** `pnpm gates:client` → clean. No screenshots (hook only).

- [ ] **Commit:**
  `git add apps/client/src/components/chat/useChatStream.ts apps/client/src/components/chat/useChatStream.test.ts`
  `git commit -m "feat(client): useChatStream stop/reset/retry controls (p8 t11)"`

## Verify

```bash
pnpm -C apps/client test -- useChatStream
pnpm gates:client
```

## Acceptance

- `stop` keeps the partial answer and raises no error; `reset` clears state + storage;
  `retry` re-sends the last question exactly once and clears the error; all guarded against
  re-entrancy; existing pins untouched.
