// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { AgentPanel } from '.';

// phase-5 task-04 (admin agent panel), RED (TDD), Step 5 tests 7-9: `AgentPanel/Component.tsx`
// does not exist yet — the barrel import above fails to resolve, module-resolution RED (same
// accepted failure mode `apps/client/src/components/chat/ChatScreen/Component.test.tsx`
// documents for its own not-yet-existing screen).
//
// Brief: docs/plans/phase-5-mcp-agent/task-04-admin-agent-panel.md, Interfaces + Step 5.
// Spec: advisordesk-prd.md §2.2 (example commands + "reports what it did... renders each tool
// call live"), §5.4 (event shapes), §6 ("Cap: 8 tool calls per request. At the cap, the agent
// stops, reports exactly which operations completed and which remain").
// FRONTEND-CONVENTIONS.md §7: "never mock the hook" — this file drives the REAL `useAgentStream`
// hook end-to-end by mocking only `fetch` (the network edge), exactly like a user would: type a
// command, click Send, read the rendered conversation.
//
// This header originally recorded test-author judgment calls made against the phase-5 RED pass
// — task-23 (DESIGN.md §5 C7) then rewrote both the component and this file's own pins, so (1)
// and (3) below are updated (p8 final, F16) to describe the contract those pins exercise today;
// (2) and (4) were already accurate and are unchanged:
// (1) `AgentPanel` takes ONE prop, `onClose: () => void` (`interface.ts`) — the shell's
//     `closeAgent`, wired to the panel's own close button. It still owns `useAgentStream()`
//     itself; only the close affordance moved from the shell into the panel.
// (2) Accessible names invented here (not pinned anywhere beyond the brief's prose): the command
//     field is a textbox named "Message"; the submit control is a button named "Send"; each turn
//     is `role="article"`, named "You" / "Assistant" — all reused verbatim from
//     `ChatScreen/Component.test.tsx`'s own precedent (phase-4 t05) for one consistent contract
//     across both chat-shaped UIs in this codebase.
// (3) Tool-event rendering IS queried by role/name: each `ToolCallCard` renders as a `button`
//     whose accessible name is its collapsed summary ("Running <tool>…" / "Ran <tool> ·
//     <summary>") — see the scripted-exchange test below, which queries the card by
//     `getByRole('button', { name: /^Ran create_draft/ })`. `ToolCallCard` also has its own
//     focused unit test file (`agent/ToolCallCard/Component.test.tsx`).
// (4) Test 9 (input disabled while streaming) uses a GATED stream fixture
//     (`gatedStreamResponse`/`deferred`, lifted verbatim from `ChatScreen/Component.test.tsx`'s
//     own fix — see that file's header comment for the full LESSON): a mocked `fetch`/
//     `ReadableStream` that resolves entirely via microtasks can complete faster than
//     `user-event`'s own macrotask-gated pointer/click sequencing, so asserting a transient
//     `disabled` state needs the stream held open under test control, not a race against
//     real timing.

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

/** See judgment call (4) above — held open until `release()` is called. */
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

async function askAgent(user: ReturnType<typeof userEvent.setup>, text: string): Promise<void> {
  const input = screen.getByRole('textbox', { name: 'Message' });
  await user.type(input, text);
  await user.click(screen.getByRole('button', { name: 'Send' }));
}

function renderPanel(onClose = vi.fn()) {
  return render(
    <Providers>
      <AgentPanel onClose={onClose} />
    </Providers>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('AgentPanel', () => {
  it('renders a scripted exchange: user bubble, tool-call cards in stream order, then final assistant text', async () => {
    const argumentsFixture = { title: 'Roth IRA Conversion Basics', tags: ['retirement'] };
    const resultSummary = 'Created draft d-42 (Roth IRA Conversion Basics).';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Creating the draft. ' } },
          { event: 'tool_call', data: { tool: 'create_draft', arguments: argumentsFixture } },
          {
            event: 'tool_result',
            data: { tool: 'create_draft', result_summary: resultSummary },
          },
          { event: 'token', data: { text: 'Done — draft created.' } },
          {
            event: 'done',
            data: {
              tool_calls: [
                {
                  tool: 'create_draft',
                  arguments: argumentsFixture,
                  result_summary: resultSummary,
                },
              ],
            },
          },
        ]),
      ),
    );
    const user = userEvent.setup();

    renderPanel();
    await askAgent(user, 'Draft an article on Roth IRA conversion basics and tag it retirement.');

    expect(await screen.findByRole('article', { name: 'You' })).toHaveTextContent(
      'Draft an article on Roth IRA conversion basics and tag it retirement.',
    );
    const assistant = await screen.findByRole('article', { name: 'Assistant' });
    await waitFor(() => expect(assistant).toHaveTextContent('Done — draft created.'));

    // `resultSummary` must be escaped before interpolation — it contains regex metacharacters
    // (parens, a trailing period) that must match LITERALLY, since the pin requires
    // `result_summary` rendered verbatim (mirrors useAgentStream.test.tsx test 1's own verbatim
    // pin on the same string).
    const escapedResultSummary = resultSummary.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const card = within(assistant).getByRole('button', {
      name: new RegExp(`^Ran create_draft · ${escapedResultSummary}$`),
    });
    expect(card).toHaveAttribute('aria-expanded', 'false');
    const text = assistant.textContent ?? '';
    expect(text.indexOf('Creating the draft.')).toBeLessThan(text.indexOf('Ran create_draft'));
    expect(text.indexOf('Ran create_draft')).toBeLessThan(text.indexOf('Done — draft created.'));

    await user.click(card);
    expect(
      within(assistant).getByText(/"title": "Roth IRA Conversion Basics"/),
    ).toBeInTheDocument();
  });

  it('renders a §6 cap-report final message as a normal assistant message, not an error', async () => {
    const capText =
      'I completed 8 operations: published 6 drafts and archived 2 items. 3 operations remain — please re-run this request to continue.';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: capText } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      ),
    );
    const user = userEvent.setup();

    renderPanel();
    await askAgent(user, 'Find everything tagged estate-planning and publish the drafts.');

    const assistant = await screen.findByRole('article', { name: 'Assistant' });
    await waitFor(() => expect(assistant).toHaveTextContent(capText));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('Send is gated on a draft; while streaming the field is disabled and Stop replaces Send; both restore after', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Working on it.' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const user = userEvent.setup();

    renderPanel();
    const input = screen.getByRole('textbox', { name: 'Message' });
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    await user.type(input, 'How many published pieces do we have on tax planning?');
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(input).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Working…' })).toBeInTheDocument();

    release();

    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Working…' })).not.toBeInTheDocument();
  });

  it('header: an h2 "Agent", Clear resets the conversation, the close button calls onClose', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Hi' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      ),
    );
    const onClose = vi.fn();
    const user = userEvent.setup();

    renderPanel(onClose);
    expect(screen.getByRole('heading', { level: 2, name: 'Agent' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeDisabled();

    await askAgent(user, 'Hello');
    await screen.findByRole('article', { name: 'Assistant' });
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Ask the agent to work on your content');

    await user.click(screen.getByRole('button', { name: 'Close agent panel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('the empty state offers three suggested commands and clicking one sends it', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse([
        { event: 'token', data: { text: 'Sure.' } },
        { event: 'done', data: { tool_calls: [] } },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    renderPanel();
    const status = screen.getByRole('status');
    const suggestions = within(status).getAllByRole('button');
    expect(suggestions).toHaveLength(3);

    await user.click(suggestions[1]!);

    await screen.findByRole('article', { name: 'You' });
    const body = JSON.parse((fetchMock.mock.calls[0]?.[1] as RequestInit).body as string) as {
      messages: { content: string }[];
    };
    expect(body.messages[0]?.content).toBe('List the drafts tagged estate-planning.');
  });

  it('Stop aborts the stream and keeps what arrived, with no error', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Never shown' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const user = userEvent.setup();

    renderPanel();
    await askAgent(user, 'Q');
    await user.click(await screen.findByRole('button', { name: 'Stop' }));
    release();

    await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument());
    expect(screen.getByRole('article', { name: 'You' })).toHaveTextContent('Q');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('Enter sends the draft; Shift+Enter inserts a newline instead', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse([
        { event: 'token', data: { text: 'Ok' } },
        { event: 'done', data: { tool_calls: [] } },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    renderPanel();
    const input = screen.getByRole('textbox', { name: 'Message' });
    await user.type(input, 'first{Shift>}{Enter}{/Shift}second');
    expect(input).toHaveValue('first\nsecond');
    expect(fetchMock).not.toHaveBeenCalled();

    await user.type(input, '{Enter}');

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(input).toHaveValue('');
  });

  it('an `error` event renders an inline error alert', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          {
            event: 'error',
            data: { error: { code: 'agent_failed', message: 'The agent hit a wall.' } },
          },
        ]),
      ),
    );
    const user = userEvent.setup();

    renderPanel();
    await askAgent(user, 'Q');

    expect(await screen.findByRole('alert')).toHaveTextContent('The agent hit a wall.');
  });

  it('renders the helper line under the composer', () => {
    renderPanel();

    expect(screen.getByText('Enter to send · Shift+Enter for a new line')).toBeInTheDocument();
  });
});
