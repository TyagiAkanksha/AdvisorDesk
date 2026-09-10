// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatScreen } from '.';

// task-05 (phase-4), RED (TDD): `ChatScreen/Component.tsx` does not exist yet — the barrel import
// above fails to resolve, the expected RED failure (test-author brief STOP RULE).
//
// Brief Step 5 + Interfaces: docs/plans/phase-4-rag-assistant/task-05-client-chat-ui.md.
// FRONTEND-CONVENTIONS.md §7: "never mock the hook" — this file drives the REAL `useChatStream`
// hook end-to-end by mocking only `fetch` (the network edge), exactly like a user would: type a
// question, click Send, read the rendered conversation.
//
// Controller-approved revision: converted from `fireEvent` to `@testing-library/user-event`
// (FRONTEND-CONVENTIONS.md §7's pinned idiom, matching apps/admin's existing usage style —
// e.g. `content/ContentListScreen/deleteError.test.tsx`'s `userEvent.setup()` +
// `await user.click(...)`) now that `@testing-library/user-event` is installed for apps/client
// (controller commit 332764c). The original RED draft used `fireEvent` only because the package
// was not yet resolvable from this workspace — assertions and test list are unchanged.
//
// Controller-approved pin fix (defect surfaced during implementation, see
// `.superpowers/sdd/reports/p4-t05-implementer.md`'s "Blocking issue"): the "disables the
// message input while streaming" test originally checked `toBeDisabled()` *synchronously* right
// after an awaited `user.click()`, with no `waitFor`. That assumption — that React's
// `streaming: true` flush from `send()` would still be observable at that instant — does not
// hold: with a mocked `fetch`/`ReadableStream` that resolves entirely via microtasks, the WHOLE
// `send()` cycle (fetch → parse → `citations`/`done` → `streaming: false`) completes faster than
// `user.click()`'s own internal pointer/mouse/focus event sequencing (which is gated behind real
// macrotasks) — so by the time the test's `await user.click(...)` returns, the disabled window
// has already opened AND closed, unobserved. Three independent timing probes (bare chained-
// microtask handlers, a capped 500-tick loop, and direct instrumentation of the real
// implementation) confirmed this in the implementer's report. Fix: gate the mocked stream open
// with a deferred promise (`gatedStreamResponse` below) so `streaming` provably STAYS `true`
// until the test explicitly releases it — turning a timing race into a stable, `waitFor`-safe
// assertion. No other test in this file changed.
//
// Judgment calls (test-author, flagged for controller review — mirrored in useChatStream.test.ts
// and MessageBubble/Component.test.tsx for consistency across the three files):
// (1) `ChatScreen` takes NO props (rendered `<ChatScreen />`): it is the client island that owns
//     `useChatStream()` itself (docs/FRONTEND-CONVENTIONS.md §6 — unlike the RSC `content/`
//     screens, which receive server-fetched data as props). Per §3, a zero-prop component has no
//     `interface.ts`; the brief's Files list names one anyway — left for the implementer to
//     resolve (an empty/omitted `interface.ts` is not a test-observable difference).
// (2) Accessible names invented here (not pinned anywhere): the message field is a textbox named
//     "Message"; the submit control is a button named "Send". Both are literal contract pins for
//     the implementer, same status as `DISCLAIMER` in `content/ArticleScreen/Component.tsx`.
// (3) Each message bubble is `role="article"`, named "You" / "Assistant" (ARIA's article role:
///    "a self-contained composition" — a reasonable fit for one chat turn); a refusal renders
//     inside a `role="status"` region, mirroring the existing `common/EmptyState` precedent
//     (docs/FRONTEND-CONVENTIONS.md §9) rather than inventing a new pattern.
// (4) Markdown rendering is asserted the same way `content/Markdown/Component.test.tsx` already
//     does for structural claims it can't make via `getByRole` (that file uses
//     `container.querySelector('script')`) — `<strong>` has no distinct ARIA role, so
//     `container.querySelector('strong')` is the correct query, not a role query.

interface SseFrame {
  event: string;
  data: unknown;
}

function sseBody(frames: SseFrame[]): string {
  return frames
    .map((frame) => `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`)
    .join('');
}

function streamResponse(frames: SseFrame[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sseBody(frames)));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  });
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/**
 * Build a `Response` whose SSE body stays open (no bytes enqueued, never closed) until the
 * returned `release()` is called — used only by the "disables the message input while
 * streaming" test to hold `streaming: true` open for a deterministic window, instead of racing
 * a fully-microtask-resolving stream against `user.click()`'s own event sequencing.
 */
function gatedStreamResponse(frames: SseFrame[]): { response: Response; release: () => void } {
  const gate = deferred<void>();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      await gate.promise;
      controller.enqueue(new TextEncoder().encode(sseBody(frames)));
      controller.close();
    },
  });
  const response = new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  });
  return { response, release: () => gate.resolve() };
}

async function askQuestion(
  user: ReturnType<typeof userEvent.setup>,
  question: string,
): Promise<void> {
  const input = screen.getByRole('textbox', { name: 'Message' });
  await user.type(input, question);
  await user.click(screen.getByRole('button', { name: 'Send' }));
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('ChatScreen', () => {
  it('renders the typed question as a user bubble and the streamed answer as an assistant bubble, each identifiable by role', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'A Roth IRA is a retirement account.' } },
          {
            event: 'citations',
            data: {
              citations: [{ content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' }],
            },
          },
          { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
        ]),
      ),
    );
    const user = userEvent.setup();

    render(<ChatScreen />);
    await askQuestion(user, 'What is a Roth IRA?');

    expect(await screen.findByRole('article', { name: 'You' })).toHaveTextContent(
      'What is a Roth IRA?',
    );
    expect(await screen.findByRole('article', { name: 'Assistant' })).toHaveTextContent(
      'A Roth IRA is a retirement account.',
    );
  });

  it("renders the assistant's answer through Markdown (bold text becomes a <strong> element)", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'A Roth IRA offers **tax-free** growth.' } },
          {
            event: 'citations',
            data: {
              citations: [{ content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' }],
            },
          },
          { event: 'done', data: { session_id: 's-2', message_id: 'm-2' } },
        ]),
      ),
    );
    const user = userEvent.setup();

    const { container } = render(<ChatScreen />);
    await askQuestion(user, 'What is a Roth IRA?');

    await waitFor(() => expect(container.querySelector('strong')).not.toBeNull());
    expect(container.querySelector('strong')?.textContent).toBe('tax-free');
  });

  it('renders numbered citation chips linking to /content/{slug} in server order', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Both accounts are common retirement vehicles.' } },
          {
            event: 'citations',
            data: {
              citations: [
                { content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' },
                {
                  content_id: 'c-2',
                  title: 'Traditional IRA Basics',
                  slug: 'traditional-ira-basics',
                },
              ],
            },
          },
          { event: 'done', data: { session_id: 's-3', message_id: 'm-3' } },
        ]),
      ),
    );
    const user = userEvent.setup();

    render(<ChatScreen />);
    await askQuestion(user, 'Compare Roth and traditional IRAs.');

    // phase-8 task-12 (DESIGN.md §B4) pin update: Sources links are now titled
    // ('[1] <title>'), not bare '[n]' chips.
    const firstLink = await screen.findByRole('link', { name: '[1] Roth IRA Basics' });
    const secondLink = screen.getByRole('link', { name: '[2] Traditional IRA Basics' });
    expect(firstLink).toHaveAttribute('href', '/content/roth-ira-basics');
    expect(secondLink).toHaveAttribute('href', '/content/traditional-ira-basics');
  });

  it('renders a refusal distinctly, in a status region, when the answer carries no citations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'No published guidance covers this.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-4', message_id: 'm-4' } },
        ]),
      ),
    );
    const user = userEvent.setup();

    render(<ChatScreen />);
    await askQuestion(user, 'An uncovered question.');

    const refusal = await screen.findByRole('status');
    expect(refusal).toHaveTextContent('No published guidance covers this.');
  });

  it('disables the message input while streaming, and re-enables it once the stream completes', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'An answer.' } },
      { event: 'citations', data: { citations: [] } },
      { event: 'done', data: { session_id: 's-5', message_id: 'm-5' } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const user = userEvent.setup();

    render(<ChatScreen />);
    const input = screen.getByRole('textbox', { name: 'Message' });
    const sendButton = screen.getByRole('button', { name: 'Send' });
    expect(input).toBeEnabled();
    // phase-8 task-12 (DESIGN.md §B4) pin update: Send is disabled while the draft is empty and
    // enabled once there is something to send — the old pin expected it enabled on a blank form.
    expect(sendButton).toBeDisabled();
    await user.type(input, 'A question.');
    expect(sendButton).toBeEnabled();
    await user.clear(input);

    await askQuestion(user, 'A question.');

    // The stream is held open (no frames released yet) — `streaming` is stably `true`, not a
    // narrow race window, so `waitFor` here is about letting React's state update propagate,
    // not about racing the mocked network.
    await waitFor(() => expect(input).toBeDisabled());
    // phase-8 task-12 (DESIGN.md §B4) pin update: the composer swaps Send for a Stop icon
    // button while streaming — there is no "Send" button to query at this point.
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();

    release();

    await waitFor(() => expect(input).toBeEnabled());
    // phase-8 task-12 pin update: Stop swaps back to Send once the stream completes.
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  // phase-8 task-12 (DESIGN.md §B4) — new cases appended per the task brief.

  it('shows the welcome state with suggested questions, and clicking one sends it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Answer.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-9', message_id: 'm-9' } },
        ]),
      ),
    );
    const user = userEvent.setup();
    render(<ChatScreen />);

    expect(screen.getByRole('heading', { level: 1, name: 'Ask a question' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Do I need umbrella insurance?' }));

    expect(await screen.findByRole('article', { name: 'You' })).toHaveTextContent(
      'Do I need umbrella insurance?',
    );
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
  });

  it('shows Thinking… after sending until the first token arrives', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'First token.' } },
      { event: 'citations', data: { citations: [] } },
      { event: 'done', data: { session_id: 's-10', message_id: 'm-10' } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const user = userEvent.setup();
    render(<ChatScreen />);
    await askQuestion(user, 'Slow question');

    expect(await screen.findByText('Thinking…')).toBeInTheDocument();
    release();
    await waitFor(() => expect(screen.queryByText('Thinking…')).toBeNull());
  });

  it('shows an error alert with Retry after a failed request, and Retry re-sends the question', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({ error: { code: 'rate_limited', message: 'Slow down' } }),
      })
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Second try.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-11', message_id: 'm-11' } },
        ]),
      );
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<ChatScreen />);
    await askQuestion(user, 'Rate me');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Slow down');
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('Second try.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('New conversation clears the transcript and shows the welcome state again', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Answer.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-12', message_id: 'm-12' } },
        ]),
      ),
    );
    const user = userEvent.setup();
    render(<ChatScreen />);
    await askQuestion(user, 'First');
    await screen.findByText('Answer.');

    await user.click(screen.getByRole('button', { name: 'New conversation' }));

    expect(screen.queryByRole('article')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Ask a question' })).toBeInTheDocument();
  });
});
