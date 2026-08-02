// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
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
// Judgment calls (test-author, flagged for controller review — mirrors
// `apps/admin/src/components/agent/useAgentStream.test.tsx`'s own judgment calls for
// consistency):
// (1) `AgentPanel` takes NO props — it is the persistent island that owns `useAgentStream()`
//     itself, mirroring `ChatScreen`'s own precedent exactly ("the client island that owns
//     `useChatStream()` itself... a zero-prop component has no `interface.ts`",
//     FRONTEND-CONVENTIONS.md §3). The open/closed VISUAL toggle (brief: "persistent right MUI
//     Drawer toggled from the AppShell") is a SEPARATE concern this file does not test — see
//     `AppShell/agentPanelToggle.test.tsx` — so `AgentPanel` here is rendered directly, with no
//     assumption about how/whether its host wraps it in an openable Drawer.
// (2) Accessible names invented here (not pinned anywhere beyond the brief's prose): the command
//     field is a textbox named "Message"; the submit control is a button named "Send"; each turn
//     is `role="article"`, named "You" / "Assistant" — all reused verbatim from
//     `ChatScreen/Component.test.tsx`'s own precedent (phase-4 t05) for one consistent contract
//     across both chat-shaped UIs in this codebase.
// (3) Tool-event rendering ("→ create_draft {…}" / "✓ create_draft — <summary>", brief's
//     `ToolCallCard` contract) is asserted via the assistant turn's rendered TEXT content and
//     ordering (`indexOf('→') < indexOf('✓')`), not by querying a `ToolCallCard`-specific role —
//     the brief does not pin any distinct ARIA role/name for the card itself, and `ToolCallCard`
//     has no test file of its own in this RED pass (Step 5's listed behaviors are all exercised
//     end-to-end through `AgentPanel`; the brief's Files list creates `ToolCallCard`/
//     `AgentMessage` folders for the IMPLEMENTER's Step 6, not for a test-author-authored
//     standalone unit test).
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

function renderPanel() {
  return render(
    <Providers>
      <AgentPanel />
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

    const text = assistant.textContent ?? '';
    expect(text).toMatch(/→\s*create_draft/);
    // `resultSummary` must be escaped before interpolation — it contains regex metacharacters
    // (parens, a trailing period) that must match LITERALLY, since the pin requires
    // `result_summary` rendered verbatim (mirrors useAgentStream.test.tsx test 1's own verbatim
    // pin on the same string).
    const escapedResultSummary = resultSummary.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    expect(text).toMatch(new RegExp(`✓\\s*create_draft.*${escapedResultSummary}`));
    const callIndex = text.indexOf('→');
    const resultIndex = text.indexOf('✓');
    expect(callIndex).toBeGreaterThanOrEqual(0);
    expect(resultIndex).toBeGreaterThan(callIndex);
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

  it('disables the message input and Send while streaming, and re-enables both once the stream completes', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Working on it.' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const user = userEvent.setup();

    renderPanel();
    const input = screen.getByRole('textbox', { name: 'Message' });
    const sendButton = screen.getByRole('button', { name: 'Send' });
    expect(input).toBeEnabled();
    expect(sendButton).toBeEnabled();

    await askAgent(user, 'How many published pieces do we have on tax planning?');

    // The stream is held open (no frames released yet) — `streaming` is stably `true`, not a
    // narrow race window (see judgment call 4 above).
    await waitFor(() => expect(input).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();

    release();

    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });
});
