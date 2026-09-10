---
id: p8-t12
phase: phase-8-ui-polish
depends_on: [p8-t11]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 12 — Chat screen: welcome, bubbles, sources, composer (apps/client, B4 UI half)

## Goal

Rebuild the chat surface on the primitives from A and the hook controls from task 11: a
welcome state with four clickable suggested questions, navy/outlined bubbles capped at 640px,
a "Thinking…" row before the first token, a **Sources** list with real titles instead of
tooltip-only `[n]` chips, refusals as a warning alert, and a composer with a multiline field
(Enter sends, Shift+Enter newlines), Send/Stop icon button, "New conversation", a helper line,
and an error alert with Retry. Column width `md`.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2 and §4 B4; PRD §7.5 (citations `[1], [2]`,
  refusal copy) and §8.
- `docs/FRONTEND-CONVENTIONS.md` §3 (components dumb; VM hooks colocated `useX.ts`), §7, §9.
- `apps/client/src/components/chat/ChatScreen/{Component.tsx, Component.test.tsx, index.ts}` —
  current screen and its pins (rewritten in this task; the `streamResponse`/`gatedStreamResponse`
  fixture helpers at the top of the test file are reused verbatim).
- `apps/client/src/components/chat/MessageBubble/{Component.tsx, interface.ts, Component.test.tsx}`,
  `CitationList/{Component.tsx, interface.ts, Component.test.tsx}`.
- `apps/client/src/components/chat/useChatStream.ts` — `UseChatStreamResult` now has
  `stop`, `reset`, `retry` (task 11); `ChatMessage`, `Citation` types.
- `apps/client/src/components/common/{Alert,Box,Button,IconButton,Paper,Stack,TextField,Typography,Link,PageContainer}/`,
  `common/Icon/Component.tsx` (registry — add `Send`, `Stop`), `common/index.ts`.
- `apps/client/src/app/chat/page.tsx`, `app/chat/loading.tsx`, `components/chat/ChatSkeleton/`.
- `apps/client/src/lib/copy.ts`.

## Files

**Create**
- `src/components/common/CircularProgress/{Component.tsx, interface.ts, index.ts}` (pass-through, `CircularProgressProps = MuiCircularProgressProps`)
- `src/components/chat/ChatScreen/useChatComposer.ts` (VM hook: draft + keyboard rule + submit)
- `src/components/chat/ChatScreen/components/ChatWelcome/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
- `src/components/chat/ChatScreen/components/ChatComposer/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
- `src/components/chat/ChatScreen/components/ThinkingIndicator/{Component.tsx, index.ts, Component.test.tsx}` (zero-prop)

**Modify**
- `src/components/common/Icon/Component.tsx` — registry gains `Send: SendIcon` (`@mui/icons-material/Send`) and `Stop: StopIcon` (`@mui/icons-material/Stop`).
- `src/components/common/index.ts` — export `CircularProgress`.
- `src/components/chat/ChatScreen/{Component.tsx, Component.test.tsx}`
- `src/components/chat/MessageBubble/{Component.tsx, Component.test.tsx}`
- `src/components/chat/CitationList/{Component.tsx, Component.test.tsx}` (becomes the Sources list; name kept)
- `src/app/chat/page.tsx`, `src/app/chat/loading.tsx` — `PageContainer maxWidth="md"`.
- `src/lib/copy.ts` — constants below.

## Interfaces

**Produces exactly:**

```ts
// src/lib/copy.ts — appended
export const CHAT_TITLE = 'Ask a question';
export const CHAT_DESCRIPTION =
  'Answers come from the published articles and cite their sources.';
export const SUGGESTED_QUESTIONS = [
  'When can I withdraw from a Roth IRA without penalty?',
  'How does Medicare enrollment work if I am still employed at 65?',
  'What is the difference between a 529 plan and a UTMA account?',
  'Do I need umbrella insurance?',
] as const;
export const THINKING_LABEL = 'Thinking…';
export const SOURCES_LABEL = 'Sources';
export const MESSAGE_FIELD_LABEL = 'Message';
export const SEND_LABEL = 'Send';
export const STOP_LABEL = 'Stop';
export const NEW_CONVERSATION_LABEL = 'New conversation';
export const CHAT_HELPER_TEXT =
  'Educational answers grounded in the published articles — not financial advice.';

// ChatScreen/useChatComposer.ts
export interface UseChatComposerArgs {
  disabled: boolean;              // true while streaming
  onSend: (text: string) => void; // the hook's send
}
export interface UseChatComposerResult {
  draft: string;
  setDraft: (value: string) => void;
  canSend: boolean;               // draft.trim().length > 0 && !disabled
  submit: () => void;             // trims, sends if canSend, clears the draft
  onKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void; // Enter → preventDefault + submit; Shift+Enter → default (newline)
}
export function useChatComposer(args: UseChatComposerArgs): UseChatComposerResult;

// ChatWelcome/interface.ts
export interface ChatWelcomeProps {
  onAsk: (question: string) => void; // a suggested question was clicked
}
// ChatComposer/interface.ts
export interface ChatComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown: UseChatComposerResult['onKeyDown'];
  canSend: boolean;
  streaming: boolean;
  onStop: () => void;
  onNewConversation: () => void;
  showNewConversation: boolean;   // messages.length > 0
}
// CitationList/interface.ts — unchanged shape: { citations: Citation[] }
```

**Behaviour:**

- `ChatScreen/Component.tsx` (dumb composition over the two hooks):
  ```tsx
  const { messages, streaming, error, send, stop, reset, retry } = useChatStream();
  const composer = useChatComposer({ disabled: streaming, onSend: send });
  const awaitingFirstToken = streaming && messages[messages.length - 1]?.role === 'user';
  ```
  Layout: `Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '60vh' }}` →
  `messages.length === 0 ? <ChatWelcome onAsk={send} /> : messages.map(<MessageBubble/>)` →
  `awaitingFirstToken && <ThinkingIndicator />` → `error !== null && <Alert severity="error"
  action={<Button size="small" color="inherit" onClick={retry}>{RETRY_LABEL}</Button>}>{error}</Alert>`
  → `<ChatComposer … />` in a `Box sx={{ position: 'sticky', bottom: 0, bgcolor: 'background.default', pt: 2, pb: 1, mt: 'auto' }}`.
- `ChatWelcome`: `Typography h1` `CHAT_TITLE`, `Typography body1 color="text.secondary"`
  `CHAT_DESCRIPTION`, then `Stack direction="row" flexWrap="wrap" useFlexGap spacing={1}` of
  `Button variant="outlined" onClick={() => onAsk(question)}` per `SUGGESTED_QUESTIONS`.
  Wrapper `Box role="region" aria-label={CHAT_TITLE}` (not `role="status"` — it is content,
  not a live announcement).
- `ThinkingIndicator`: `Box role="status" aria-live="polite" sx={{ display: 'flex',
  alignItems: 'center', gap: 1, my: 1 }}` with `<CircularProgress size={16} />` and
  `Typography body2 color="text.secondary"` `THINKING_LABEL`.
- `ChatComposer`: `<form onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>`; `Stack
  direction="row" spacing={1} alignItems="flex-end"` → `TextField label={MESSAGE_FIELD_LABEL}
  value={draft} onChange={onDraftChange} onKeyDown={onKeyDown} multiline minRows={1}
  maxRows={6} fullWidth disabled={streaming}` + (`streaming ? <IconButton name="Stop"
  label={STOP_LABEL} onClick={onStop} color="primary" /> : <IconButton name="Send"
  label={SEND_LABEL} type="submit" disabled={!canSend} color="primary" />`); below:
  `Stack direction="row" justifyContent="space-between" alignItems="center"` →
  `Typography variant="caption" color="text.secondary"` `CHAT_HELPER_TEXT` and, when
  `showNewConversation`, `Button variant="text" size="small" onClick={onNewConversation}`
  `NEW_CONVERSATION_LABEL`.
  (The spec's placeholder text is dropped: a floating MUI label plus a placeholder is
  redundant and the placeholder is only visible while focused — the label "Message" stays the
  accessible name, matching the existing pin.)
- `MessageBubble`: user → `Paper elevation={0} sx={{ bgcolor: 'primary.main', color:
  'primary.contrastText', px: 2, py: 1.5, borderRadius: 2, maxWidth: 'min(100%, 640px)' }}`
  right-aligned; assistant → `Paper variant="outlined" sx={{ px: 2, py: 1.5, borderRadius: 2,
  maxWidth: 'min(100%, 640px)' }}` left-aligned, `<Markdown variant="chat" headingOffset={1}>`
  + `<CitationList citations />`; refusal → `<Alert severity="warning" variant="outlined"
  role="status" sx={{ maxWidth: 'min(100%, 640px)' }}>` wrapping the same answer (keeps the
  pinned `role="status"` + text; drops the old Info icon/`grey.100` styling). Keep
  `role="article"` + `aria-label` "You"/"Assistant" on the outer row.
- `CitationList` → Sources: `nav aria-label={SOURCES_LABEL}` → `Typography variant="overline"
  component="p"` `SOURCES_LABEL` + `Box component="ol" sx={{ pl: 2.5, m: 0 }}` of
  `<li><Link href={`/content/${slug}`}>[{n}] {title}</Link></li>`. Empty → `null` (unchanged).

## Steps (TDD)

- [ ] **RED — test-author.**

  `useChatComposer.test.ts` (jsdom; `renderHook`):

```ts
// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { useChatComposer } from './useChatComposer';

const key = (overrides: Partial<KeyboardEvent<HTMLTextAreaElement>>) =>
  ({ key: 'Enter', shiftKey: false, preventDefault: vi.fn(), ...overrides }) as unknown as KeyboardEvent<HTMLTextAreaElement>;

describe('useChatComposer', () => {
  it('cannot send an empty or whitespace draft, and sends the trimmed draft then clears it', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useChatComposer({ disabled: false, onSend }));

    expect(result.current.canSend).toBe(false);
    act(() => result.current.setDraft('   '));
    expect(result.current.canSend).toBe(false);
    act(() => result.current.setDraft('  Hello  '));
    expect(result.current.canSend).toBe(true);
    act(() => result.current.submit());

    expect(onSend).toHaveBeenCalledWith('Hello');
    expect(result.current.draft).toBe('');
  });

  it('Enter submits and prevents the newline; Shift+Enter is left to the field', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useChatComposer({ disabled: false, onSend }));
    act(() => result.current.setDraft('Q'));

    const enter = key({});
    act(() => result.current.onKeyDown(enter));
    expect(enter.preventDefault).toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledWith('Q');

    act(() => result.current.setDraft('multi'));
    const shiftEnter = key({ shiftKey: true });
    act(() => result.current.onKeyDown(shiftEnter));
    expect(shiftEnter.preventDefault).not.toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('never sends while disabled', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useChatComposer({ disabled: true, onSend }));
    act(() => result.current.setDraft('Q'));
    expect(result.current.canSend).toBe(false);
    act(() => result.current.submit());
    expect(onSend).not.toHaveBeenCalled();
  });
});
```

  `ChatWelcome/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ChatWelcome } from '.';

describe('ChatWelcome', () => {
  it('renders the h1, the description, and four suggested-question buttons that send on click', async () => {
    const onAsk = vi.fn();
    render(<ChatWelcome onAsk={onAsk} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Ask a question' })).toBeInTheDocument();
    expect(screen.getByText(/cite their sources/)).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
    await userEvent.click(buttons[0]!);
    expect(onAsk).toHaveBeenCalledWith('When can I withdraw from a Roth IRA without penalty?');
  });
});
```

  `ThinkingIndicator/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ThinkingIndicator } from '.';

describe('ThinkingIndicator', () => {
  it('announces Thinking… in a polite status region with a progress indicator', () => {
    render(<ThinkingIndicator />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Thinking…');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });
});
```

  `ChatComposer/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ChatComposer } from '.';

const base = {
  draft: '',
  onDraftChange: vi.fn(),
  onSubmit: vi.fn(),
  onKeyDown: vi.fn(),
  canSend: false,
  streaming: false,
  onStop: vi.fn(),
  onNewConversation: vi.fn(),
  showNewConversation: false,
};

describe('ChatComposer', () => {
  it('renders a multiline Message field, a disabled Send button when nothing can be sent, and the helper line', () => {
    render(<ChatComposer {...base} />);

    expect(screen.getByRole('textbox', { name: 'Message' }).tagName).toBe('TEXTAREA');
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(screen.getByText(/not financial advice/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New conversation' })).toBeNull();
  });

  it('submits through the form when Send is enabled and clicked', async () => {
    const onSubmit = vi.fn();
    render(<ChatComposer {...base} draft="Q" canSend onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('swaps Send for Stop while streaming, disables the field, and calls onStop', async () => {
    const onStop = vi.fn();
    render(<ChatComposer {...base} streaming onStop={onStop} />);

    expect(screen.queryByRole('button', { name: 'Send' })).toBeNull();
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('offers New conversation when there are messages', async () => {
    const onNewConversation = vi.fn();
    render(<ChatComposer {...base} showNewConversation onNewConversation={onNewConversation} />);

    await userEvent.click(screen.getByRole('button', { name: 'New conversation' }));
    expect(onNewConversation).toHaveBeenCalledTimes(1);
  });
});
```

  `CitationList/Component.test.tsx` — REWRITE both cases:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { CitationList } from '.';

// phase-8 task-12 (DESIGN.md §B4): sources are a titled list of real links, numbered in server
// order — a reader no longer has to hover a `[n]` chip to learn what it cites.
const citations = [
  { content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' },
  { content_id: 'c-2', title: 'Traditional IRA Basics', slug: 'traditional-ira-basics' },
];

describe('CitationList', () => {
  it('renders a Sources navigation with one numbered, titled link per citation in order', () => {
    render(<CitationList citations={citations} />);

    expect(screen.getByRole('navigation', { name: 'Sources' })).toBeInTheDocument();
    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual(['[1] Roth IRA Basics', '[2] Traditional IRA Basics']);
    expect(links[0]).toHaveAttribute('href', '/content/roth-ira-basics');
    expect(links[1]).toHaveAttribute('href', '/content/traditional-ira-basics');
  });

  it('renders nothing for an empty citations array', () => {
    const { container } = render(<CitationList citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

  `MessageBubble/Component.test.tsx` — keep every existing case; UPDATE the citation-chip
  case ("renders citation chips…") to expect a link named `[1] <title>` with the same href;
  the refusal cases still assert `role="status"` + text (now an `Alert`). Append:

```tsx
  it('renders the refusal as an outlined warning alert in the status region', () => {
    const message: ChatMessage = { role: 'assistant', text: 'No published guidance covers this.', citations: [], refusal: true };
    render(<MessageBubble message={message} />);

    const status = screen.getByRole('status');
    // MUI 9 emits separate `outlined` + `colorWarning` classes (no combined `outlinedWarning`).
    expect(status.className).toContain('MuiAlert-outlined');
    expect(status.className).toContain('MuiAlert-colorWarning');
  });
```

  `ChatScreen/Component.test.tsx` — keep the fixture helpers and the five existing cases with
  these pin updates: the citation case queries `findByRole('link', { name: '[1] Roth IRA Basics' })`
  and `'[2] Traditional IRA Basics'`; the disabled-while-streaming case additionally expects
  `getByRole('button', { name: 'Stop' })` while gated and `getByRole('button', { name: 'Send' })`
  after release, and its initial `expect(sendButton).toBeEnabled()` on a blank form becomes
  `toBeDisabled()` (Send is gated on a non-empty draft), enabled after typing. Append:

```tsx
  it('shows the welcome state with suggested questions, and clicking one sends it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'token', data: { text: 'Answer.' } },
      { event: 'citations', data: { citations: [] } },
      { event: 'done', data: { session_id: 's-9', message_id: 'm-9' } },
    ])));
    const user = userEvent.setup();
    render(<ChatScreen />);

    expect(screen.getByRole('heading', { level: 1, name: 'Ask a question' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Do I need umbrella insurance?' }));

    expect(await screen.findByRole('article', { name: 'You' })).toHaveTextContent('Do I need umbrella insurance?');
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 429, json: async () => ({ error: { code: 'rate_limited', message: 'Slow down' } }) })
      .mockResolvedValueOnce(streamResponse([
        { event: 'token', data: { text: 'Second try.' } },
        { event: 'citations', data: { citations: [] } },
        { event: 'done', data: { session_id: 's-11', message_id: 'm-11' } },
      ]));
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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'token', data: { text: 'Answer.' } },
      { event: 'citations', data: { citations: [] } },
      { event: 'done', data: { session_id: 's-12', message_id: 'm-12' } },
    ])));
    const user = userEvent.setup();
    render(<ChatScreen />);
    await askQuestion(user, 'First');
    await screen.findByText('Answer.');

    await user.click(screen.getByRole('button', { name: 'New conversation' }));

    expect(screen.queryByRole('article')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Ask a question' })).toBeInTheDocument();
  });
```

  (`askQuestion` = the file's existing helper that types into "Message" and clicks "Send";
  `gatedStreamResponse` = the file's existing deferred-stream helper — reuse both, adapting
  their signatures if they differ slightly from the calls above.)

- [ ] **Run RED:** `pnpm -C apps/client test -- chat` → new component/hook files unresolved;
  updated pins fail (chip names, Stop button, welcome heading, alert/Retry, New conversation).

- [ ] **GREEN — implementer:** copy → `CircularProgress` primitive + `Send`/`Stop` icons →
  `useChatComposer` → `ThinkingIndicator` → `ChatWelcome` → `ChatComposer` → `CitationList`
  → `MessageBubble` → `ChatScreen` → chat `page.tsx`/`loading.tsx` `maxWidth="md"`. Type-check;
  full suite.

- [ ] **Screenshots** (iframe technique, 1440 + 390): `/chat` welcome state. For the
  conversation state do NOT send real chat requests — render a throwaway route
  (`app/zz-preview-p8t12/page.tsx`, deleted before commit) showing `MessageBubble`s for a
  user turn, an assistant turn with two citations, and a refusal, plus `ThinkingIndicator` and
  the composer in both idle and streaming (`streaming` prop true) states.

- [ ] **Gates:** `pnpm gates:client` → clean.

- [ ] **Commit:**
  `git add apps/client/src/components/common apps/client/src/components/chat apps/client/src/app/chat apps/client/src/lib/copy.ts`
  `git commit -m "feat(client): chat welcome, sources list, multiline composer with stop/retry/new conversation (p8 t12)"`

## Verify

```bash
pnpm -C apps/client test -- chat
pnpm gates:client
```

## Acceptance

- Welcome state with four clickable questions; Thinking… before the first token; Sources list
  with titled links; refusal = outlined warning `Alert` in `role="status"`; error = `Alert` +
  Retry that re-sends; Enter sends / Shift+Enter newlines; Stop while streaming; New
  conversation resets. All of it behind the two hooks — `ChatScreen/Component.tsx` and the
  leaves contain no business logic.
- No `@mui` import outside `common/`; `ChatScreen/Component.tsx` ≤ ~80 lines.
