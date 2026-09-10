// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import type { ChatMessage } from '../useChatStream';
import { MessageBubble } from '.';

// task-05 (phase-4), RED (TDD): `MessageBubble/Component.tsx` and `../useChatStream` do not
// exist yet — both imports above fail to resolve, the expected RED failure (test-author brief
// STOP RULE).
//
// Brief Step 5 (docs/plans/phase-4-rag-assistant/task-05-client-chat-ui.md): "user/assistant
// bubbles by role"; "assistant text rendered through Markdown"; "citation chips ... link to
// /content/{slug}"; "refusal styled distinctly (queried by role/status)". `MessageBubble` is the
// per-message dumb leaf component `ChatScreen` composes over `useChatStream().messages`
// (docs/FRONTEND-CONVENTIONS.md §3: "Components are dumb... each component serves one purpose").
//
// Judgment calls (test-author, flagged for controller review — same conventions as
// `ChatScreen/Component.test.tsx` and `CitationList/Component.test.tsx`, kept consistent across
// all three): `role="article"` named "You"/"Assistant" per message; a refusal wraps its content
// in `role="status"` (mirrors `common/EmptyState`'s existing role="status" precedent); assistant
// text renders through the existing `content/Markdown` component (verified here via
// `container.querySelector('strong')`, matching `content/Markdown/Component.test.tsx`'s own
// query style for structural claims a role query can't express); citations, when present, render
// through `CitationList` (verified here only as "a citation link exists with the right href" —
// `CitationList/Component.test.tsx` owns the numbering/order/empty-array contract in full).

describe('MessageBubble', () => {
  it("renders a user message in a role=article region labeled 'You' with the plain message text", () => {
    const message: ChatMessage = { role: 'user', text: 'What is a Roth IRA?' };

    render(<MessageBubble message={message} />);

    expect(screen.getByRole('article', { name: 'You' })).toHaveTextContent('What is a Roth IRA?');
  });

  it("renders an assistant message in a role=article region labeled 'Assistant', with markdown rendered (bold -> <strong>)", () => {
    const message: ChatMessage = {
      role: 'assistant',
      text: 'A Roth IRA offers **tax-free** growth.',
      citations: [{ content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' }],
    };

    const { container } = render(<MessageBubble message={message} />);

    expect(screen.getByRole('article', { name: 'Assistant' })).toBeInTheDocument();
    expect(container.querySelector('strong')?.textContent).toBe('tax-free');
  });

  it('renders citation chips for an assistant message that carries citations', () => {
    const message: ChatMessage = {
      role: 'assistant',
      text: 'A Roth IRA is a retirement account.',
      citations: [{ content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' }],
    };

    render(<MessageBubble message={message} />);

    // phase-8 task-12 (DESIGN.md §B4): Sources links are now titled ('[1] <title>'), not bare
    // '[n]' chips — a reader no longer has to hover to learn what a citation points to.
    const link = screen.getByRole('link', { name: '[1] Roth IRA Basics' });
    expect(link).toHaveAttribute('href', '/content/roth-ira-basics');
  });

  it('renders the message in a status region when the assistant message is flagged as a refusal', () => {
    const message: ChatMessage = {
      role: 'assistant',
      text: 'No published guidance covers this.',
      citations: [],
      refusal: true,
    };

    render(<MessageBubble message={message} />);

    expect(screen.getByRole('status')).toHaveTextContent('No published guidance covers this.');
  });

  it('does not render a status region for a normal (non-refusal) assistant message', () => {
    const message: ChatMessage = {
      role: 'assistant',
      text: 'A Roth IRA is a retirement account.',
      citations: [{ content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' }],
    };

    render(<MessageBubble message={message} />);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  // phase-8 task-03 (DESIGN.md §A2): assistant answers switch the shared Markdown renderer to
  // the compact `chat` variant (body2, tighter margins). RED until `MessageBubble` passes
  // `variant="chat"` to `<Markdown>`.
  it('renders assistant markdown in the compact chat variant (body2 paragraphs)', () => {
    const message: ChatMessage = { role: 'assistant', text: 'Short answer.' };

    render(<MessageBubble message={message} />);

    expect(screen.getByText('Short answer.').className).toContain('MuiTypography-body2');
  });

  // p8 final: a `#` heading in an assistant answer must never emit a page-level `<h1>` — the
  // screen already owns that. `headingOffset={1}` shifts it down to `<h2>`.
  it('shifts a markdown heading in an answer down to h2 and emits no page-level h1', () => {
    const message: ChatMessage = { role: 'assistant', text: '# Heading' };

    render(<MessageBubble message={message} />);

    expect(screen.getByRole('heading', { level: 2, name: 'Heading' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument();
  });

  // phase-8 task-12 (DESIGN.md §B4): a refusal now renders as a real `common/Alert`
  // (`severity="warning"`, `variant="outlined"`) rather than a hand-styled bordered `Box` +
  // `Info` icon — same pinned `role="status"` + text, now with MUI's own warning styling.
  it('renders the refusal as an outlined warning alert in the status region', () => {
    const message: ChatMessage = {
      role: 'assistant',
      text: 'No published guidance covers this.',
      citations: [],
      refusal: true,
    };
    render(<MessageBubble message={message} />);

    const status = screen.getByRole('status');
    // MUI 9 emits separate `outlined` + `colorWarning` classes (no combined `outlinedWarning`).
    expect(status.className).toContain('MuiAlert-outlined');
    expect(status.className).toContain('MuiAlert-colorWarning');
  });
});
