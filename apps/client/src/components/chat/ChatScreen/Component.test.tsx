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

    const firstLink = await screen.findByRole('link', { name: '[1]' });
    const secondLink = screen.getByRole('link', { name: '[2]' });
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
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'An answer.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-5', message_id: 'm-5' } },
        ]),
      ),
    );
    const user = userEvent.setup();

    render(<ChatScreen />);
    const input = screen.getByRole('textbox', { name: 'Message' });
    expect(input).toBeEnabled();

    await askQuestion(user, 'A question.');

    expect(input).toBeDisabled();

    await waitFor(() => expect(input).toBeEnabled());
  });
});
