---
id: p8-t23
phase: phase-8-ui-polish
depends_on: [p8-t22, p8-t15]
status: done
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 23 — Agent panel: header, suggested commands, markdown turns, collapsible tool cards, Stop, Enter-to-send (C7, UI half)

## Goal

Make the agent drawer a finished assistant surface on task 22's hook: a header row (Agent ·
Clear · close), an empty state with three clickable suggested commands, user turns as navy
bubbles and assistant turns rendered as Markdown with **collapsible tool cards placed between
the text they interrupted** ("Ran `create_draft` · Created draft d-42…" / "Running `search`…",
expanding to arguments and result), a "Working…" indicator while streaming, auto-scroll to the
newest turn, Send → Stop swap, a multiline composer (Enter sends, Shift+Enter newlines) with a
helper line, and errors as an inline alert. The shell passes `onClose`.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2, §5 C7; §4 B4 (the client chat composer this
  mirrors).
- `docs/FRONTEND-CONVENTIONS.md` §3, §7, §9.
- `apps/admin/src/components/agent/{AgentPanel/Component.tsx, AgentPanel/Component.test.tsx,
  AgentMessage/*, ToolCallCard/*, useAgentStream.ts}` — current panel + pins (two rewritten,
  see RED); `useAgentStream` now has `stop`/`reset` and `ToolEvent.textOffset` (task 22);
  `src/lib/agentTurnSegments.ts` (`turnSegments`, `ToolSegment`).
- `apps/client/src/components/chat/ChatScreen/useChatComposer.ts` — copy its shape for
  `useAgentComposer` (read-only reference; not imported).
- `apps/admin/src/components/common/{Alert,Box,Button,CircularProgress,EmptyState,IconButton,Paper,
  Stack,TextField,Typography,Icon}/`, `common/index.ts`; `content/MarkdownPreview` (`variant="chat"`).
- `apps/admin/src/components/shell/AppShell/Component.tsx` (task 15: `shell.closeAgent`).
- `apps/admin/src/lib/copy.ts`.

## Files

**Create**
- `src/components/agent/AgentPanel/interface.ts`
- `src/components/agent/AgentPanel/useAgentComposer.ts`, `useAgentComposer.test.ts`
- `src/components/agent/AgentPanel/components/AgentComposer/{Component.tsx, interface.ts, index.ts}`
- `src/components/agent/AgentPanel/components/WorkingIndicator/{Component.tsx, index.ts}`
- `src/components/agent/AgentMessage/Component.test.tsx`
- `src/components/agent/ToolCallCard/Component.test.tsx`

**Modify**
- `src/components/agent/AgentPanel/{Component.tsx, index.ts, Component.test.tsx}`
- `src/components/agent/AgentMessage/Component.tsx`
- `src/components/agent/ToolCallCard/{Component.tsx, interface.ts}`
- `src/components/shell/AppShell/Component.tsx` (`<AgentPanel onClose={shell.closeAgent} />`)
- `src/lib/copy.ts`

## Interfaces

```ts
// src/lib/copy.ts additions
export const AGENT_PANEL_TITLE = 'Agent';
export const AGENT_CLEAR_LABEL = 'Clear';
export const AGENT_CLOSE_LABEL = 'Close agent panel';
export const AGENT_EMPTY_TITLE = 'Ask the agent to work on your content';
export const AGENT_EMPTY_DESCRIPTION = 'It can draft, tag, publish and search articles. Try one of these:';
export const AGENT_SUGGESTED_COMMANDS = [
  'Draft an article on Roth IRA conversion basics and tag it retirement.',
  'List the drafts tagged estate-planning.',
  'How many published articles do we have on tax planning?',
] as const;
export const AGENT_WORKING_LABEL = 'Working…';
export const AGENT_MESSAGE_LABEL = 'Message';
export const AGENT_SEND_LABEL = 'Send';
export const AGENT_STOP_LABEL = 'Stop';
export const AGENT_HELPER_TEXT = 'Enter to send · Shift+Enter for a new line';
export const TOOL_RUNNING_PREFIX = 'Running';
export const TOOL_RAN_PREFIX = 'Ran';
export const TOOL_ARGUMENTS_LABEL = 'Arguments';
export const TOOL_RESULT_LABEL = 'Result';

// AgentPanel/interface.ts
export interface AgentPanelProps {
  /** The shell's `closeAgent` — the panel's own close button. */
  onClose: () => void;
}

// AgentPanel/useAgentComposer.ts (colocated VM hook — same contract as the client's useChatComposer)
export interface UseAgentComposerArgs { disabled: boolean; onSend: (text: string) => void }
export interface UseAgentComposerResult {
  draft: string;
  setDraft: (value: string) => void;
  canSend: boolean;                                  // draft.trim().length > 0 && !disabled
  submit: () => void;                                // trims + sends if canSend, then clears
  onKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void; // Enter (no shift, not composing) → preventDefault + submit
}

// components/AgentComposer/interface.ts (dumb)
export interface AgentComposerProps {
  value: string;
  onChange: (value: string) => void;
  onKeyDown: UseAgentComposerResult['onKeyDown'];
  onSubmit: () => void;
  canSend: boolean;
  streaming: boolean;
  onStop: () => void;
}
// <Box component="form" onSubmit={(e) => { e.preventDefault(); onSubmit(); }} sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
//   <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
//     <TextField label={AGENT_MESSAGE_LABEL} value onChange multiline maxRows={4} fullWidth disabled={streaming} onKeyDown />
//     {streaming
//       ? <IconButton name="Stop" label={AGENT_STOP_LABEL} onClick={onStop} color="primary" />
//       : <IconButton name="Send" label={AGENT_SEND_LABEL} onClick={onSubmit} color="primary" disabled={!canSend} />}
//   </Stack>
//   <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 0.5 }}>{AGENT_HELPER_TEXT}</Typography>
// </Box>

// components/WorkingIndicator — zero-prop:
// <Stack direction="row" spacing={1} role="status" aria-label={AGENT_WORKING_LABEL} sx={{ alignItems: 'center', py: 1 }}>
//   <CircularProgress size={16} aria-hidden /><Typography variant="body2" color="text.secondary">{AGENT_WORKING_LABEL}</Typography></Stack>

// ToolCallCard/interface.ts — REPLACES the `event` prop
export interface ToolCallCardProps { segment: ToolSegment }
// <Paper variant="outlined" sx={{ my: 1 }}>
//   <Button variant="text" fullWidth onClick={toggle} aria-expanded={expanded} startIcon={<Icon name="ExpandMore" />}
//           sx={{ justifyContent: 'flex-start', textAlign: 'left', fontFamily: 'monospace', fontSize: '0.8125rem' }}>
//     {segment.result === null ? `${TOOL_RUNNING_PREFIX} ${segment.tool}…` : `${TOOL_RAN_PREFIX} ${segment.tool} · ${segment.result}`}
//   </Button>
//   {expanded ? (
//     <Box sx={{ px: 2, pb: 2 }}>
//       <Typography variant="caption" color="text.secondary" component="p">{TOOL_ARGUMENTS_LABEL}</Typography>
//       <Box component="pre" sx={{ m: 0, fontSize: '0.8125rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{prettyJson(segment.args)}</Box>
//       {segment.result !== null ? <>
//         <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1 }}>{TOOL_RESULT_LABEL}</Typography>
//         <Box component="pre" sx={{ m: 0, fontSize: '0.8125rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{segment.result}</Box></> : null}
//     </Box>) : null}
// </Paper>
// prettyJson(s): JSON.stringify(JSON.parse(s), null, 2), falling back to `s` when it does not parse ('' → '').
// `expanded` is local UI state (useState(false)).

// AgentMessage — props unchanged { turn }. user: right-aligned `Paper elevation={0}` navy bubble
// (bgcolor primary.main, color primary.contrastText, px 2, py 1, maxWidth '90%', whiteSpace pre-wrap).
// assistant: turnSegments(turn).map → text segment → <MarkdownPreview markdown={text} variant="chat" />,
// tool segment → <ToolCallCard segment />; index keys (append-only). `role="article"` + "You"/"Assistant" labels kept.

// AgentPanel — render (exact structure):
// <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
//   <Stack direction="row" spacing={1} sx={{ alignItems: 'center', px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider' }}>
//     <Typography variant="h6" component="h2" sx={{ flexGrow: 1 }}>{AGENT_PANEL_TITLE}</Typography>
//     <Button variant="text" size="small" onClick={reset} disabled={turns.length === 0 && !streaming}>{AGENT_CLEAR_LABEL}</Button>
//     <IconButton name="Close" label={AGENT_CLOSE_LABEL} onClick={onClose} size="small" />
//   </Stack>
//   <Box ref={listRef} sx={{ flexGrow: 1, overflowY: 'auto', px: 2, py: 2 }}>
//     {turns.length === 0
//       ? <EmptyState icon="SmartToy" title={AGENT_EMPTY_TITLE} description={AGENT_EMPTY_DESCRIPTION}
//           action={<Stack spacing={1}>{AGENT_SUGGESTED_COMMANDS.map((c) => <Button key={c} variant="outlined" size="small" onClick={() => send(c)}>{c}</Button>)}</Stack>} />
//       : turns.map((turn, i) => <AgentMessage key={i} turn={turn} />)}
//     {streaming ? <WorkingIndicator /> : null}
//   </Box>
//   {error !== null ? <Alert severity="error" sx={{ mx: 2, mb: 1 }}>{error}</Alert> : null}
//   <AgentComposer value={composer.draft} onChange={composer.setDraft} onKeyDown={composer.onKeyDown}
//                  onSubmit={composer.submit} canSend={composer.canSend} streaming={streaming} onStop={stop} />
// </Box>
// Auto-scroll: useEffect(() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight; }, [turns]);
// (scrollTop assignment, not scrollIntoView — jsdom lacks the latter.)

// common/Button/interface.ts addition (this task, admin only): `sx?: SxProps<Theme>` — the tool card
// header needs left-aligned monospace text; passed straight through to MuiButton.
```

## Steps (TDD)

- [ ] **RED — test-author.**

**`AgentPanel/useAgentComposer.test.ts`** (`renderHook` needs a DOM — jsdom pragma)

```ts
// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { useAgentComposer } from './useAgentComposer';

function key(k: string, shift = false) {
  return { key: k, shiftKey: shift, preventDefault: vi.fn() } as unknown as KeyboardEvent<HTMLTextAreaElement>;
}

describe('useAgentComposer', () => {
  it('canSend requires a non-blank draft and not disabled', () => {
    const { result } = renderHook(() => useAgentComposer({ disabled: false, onSend: vi.fn() }));
    expect(result.current.canSend).toBe(false);
    act(() => result.current.setDraft('  hi '));
    expect(result.current.canSend).toBe(true);
  });

  it('submit trims, sends once and clears; blocked while disabled', () => {
    const onSend = vi.fn();
    const { result, rerender } = renderHook(
      ({ disabled }) => useAgentComposer({ disabled, onSend }),
      { initialProps: { disabled: false } },
    );
    act(() => result.current.setDraft('  Draft it  '));
    act(() => result.current.submit());
    expect(onSend).toHaveBeenCalledWith('Draft it');
    expect(result.current.draft).toBe('');

    rerender({ disabled: true });
    act(() => result.current.setDraft('again'));
    act(() => result.current.submit());
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it('Enter submits and prevents the newline; Shift+Enter is left to the field', () => {
    const onSend = vi.fn();
    const { result } = renderHook(() => useAgentComposer({ disabled: false, onSend }));
    act(() => result.current.setDraft('go'));

    const shiftEnter = key('Enter', true);
    act(() => result.current.onKeyDown(shiftEnter));
    expect(shiftEnter.preventDefault).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();

    const enter = key('Enter');
    act(() => result.current.onKeyDown(enter));
    expect(enter.preventDefault).toHaveBeenCalled();
    expect(onSend).toHaveBeenCalledWith('go');
  });
});
```

**`ToolCallCard/Component.test.tsx`**

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ToolCallCard } from '.';

describe('ToolCallCard', () => {
  it('collapsed: "Running <tool>…" while there is no result', () => {
    render(<ToolCallCard segment={{ kind: 'tool', tool: 'search_content', args: '{"q":"roth"}', result: null }} />);

    const toggle = screen.getByRole('button', { name: 'Running search_content…' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Arguments')).not.toBeInTheDocument();
  });

  it('collapsed: "Ran <tool> · <summary>"; expanding shows pretty-printed arguments and the result', async () => {
    const user = userEvent.setup();
    render(
      <ToolCallCard
        segment={{ kind: 'tool', tool: 'create_draft', args: '{"title":"Roth IRA Conversion Basics","tags":["retirement"]}', result: 'Created draft d-42 (Roth IRA Conversion Basics).' }}
      />,
    );

    const toggle = screen.getByRole('button', { name: 'Ran create_draft · Created draft d-42 (Roth IRA Conversion Basics).' });
    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Arguments')).toBeInTheDocument();
    expect(screen.getByText(/"title": "Roth IRA Conversion Basics"/)).toBeInTheDocument();
    expect(screen.getByText('Result')).toBeInTheDocument();
    expect(screen.getByText('Created draft d-42 (Roth IRA Conversion Basics).', { selector: 'pre' })).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Arguments')).not.toBeInTheDocument();
  });

  it('shows unparsable arguments verbatim', async () => {
    const user = userEvent.setup();
    render(<ToolCallCard segment={{ kind: 'tool', tool: 't', args: 'not json', result: null }} />);

    await user.click(screen.getByRole('button'));

    expect(screen.getByText('not json')).toBeInTheDocument();
  });
});
```

**`AgentMessage/Component.test.tsx`**

```tsx
// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { AgentMessage } from '.';

describe('AgentMessage', () => {
  it('renders a user turn as an article named "You" preserving newlines', () => {
    render(<AgentMessage turn={{ role: 'user', text: 'line one\nline two', events: [] }} />);

    const article = screen.getByRole('article', { name: 'You' });
    expect(article).toHaveTextContent('line one line two');
    expect(within(article).getByText(/line one/)).toHaveStyle({ whiteSpace: 'pre-wrap' });
  });

  it('renders an assistant turn as markdown with tool cards between the text segments', () => {
    render(
      <AgentMessage
        turn={{
          role: 'assistant',
          text: 'Creating the **draft**. Done.',
          events: [
            { kind: 'call', tool: 'create_draft', detail: '{"title":"X"}', textOffset: 24 },
            { kind: 'result', tool: 'create_draft', detail: 'Created d-42.', textOffset: 24 },
          ],
        }}
      />,
    );

    const article = screen.getByRole('article', { name: 'Assistant' });
    expect(within(article).getByText('draft').tagName).toBe('STRONG');
    const text = article.textContent ?? '';
    expect(text.indexOf('Creating the draft.')).toBeGreaterThanOrEqual(0);
    expect(text.indexOf('Ran create_draft')).toBeGreaterThan(text.indexOf('Creating the draft.'));
    expect(text.indexOf('Done.')).toBeGreaterThan(text.indexOf('Ran create_draft'));
  });
});
```

(`'Creating the **draft**. '` is 24 characters — the offset lands after the trailing space.)

**`AgentPanel/Component.test.tsx`** — `renderPanel` becomes
`function renderPanel(onClose = vi.fn()) { return render(<Providers><AgentPanel onClose={onClose} /></Providers>); }`.
Rewrite pin 1 (`renders a scripted exchange…`): keep its fixture and the "You" assertion; replace
the glyph assertions with:

```tsx
    const assistant = await screen.findByRole('article', { name: 'Assistant' });
    await waitFor(() => expect(assistant).toHaveTextContent('Done — draft created.'));

    const card = within(assistant).getByRole('button', { name: new RegExp(`^Ran create_draft · ${escapedResultSummary}$`) });
    expect(card).toHaveAttribute('aria-expanded', 'false');
    const text = assistant.textContent ?? '';
    expect(text.indexOf('Creating the draft.')).toBeLessThan(text.indexOf('Ran create_draft'));
    expect(text.indexOf('Ran create_draft')).toBeLessThan(text.indexOf('Done — draft created.'));

    await user.click(card);
    expect(within(assistant).getByText(/"title": "Roth IRA Conversion Basics"/)).toBeInTheDocument();
```

Rewrite pin 3 (`disables the message input and Send while streaming…`) as:

```tsx
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
```

Append:

```tsx
  it('header: an h2 "Agent", Clear resets the conversation, the close button calls onClose', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'token', data: { text: 'Hi' } },
      { event: 'done', data: { tool_calls: [] } },
    ])));
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
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      { event: 'token', data: { text: 'Sure.' } },
      { event: 'done', data: { tool_calls: [] } },
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    renderPanel();
    const status = screen.getByRole('status');
    const suggestions = within(status).getAllByRole('button');
    expect(suggestions).toHaveLength(3);

    await user.click(suggestions[1]!);

    await screen.findByRole('article', { name: 'You' });
    const body = JSON.parse((fetchMock.mock.calls[0]?.[1] as RequestInit).body as string) as { messages: { content: string }[] };
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
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      { event: 'token', data: { text: 'Ok' } },
      { event: 'done', data: { tool_calls: [] } },
    ]));
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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      { event: 'error', data: { error: { code: 'agent_failed', message: 'The agent hit a wall.' } } },
    ])));
    const user = userEvent.setup();

    renderPanel();
    await askAgent(user, 'Q');

    expect(await screen.findByRole('alert')).toHaveTextContent('The agent hit a wall.');
  });

  it('renders the helper line under the composer', () => {
    renderPanel();

    expect(screen.getByText('Enter to send · Shift+Enter for a new line')).toBeInTheDocument();
  });
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- agent` → composer hook, ToolCallCard (prop
  shape), AgentMessage cases fail; the two rewritten panel pins + six appended cases fail;
  `AgentPanel` without `onClose` is a TS error at the AppShell call site; the cap-report pin
  stays green.

- [ ] **GREEN — implementer:** copy → `Button.sx` → `useAgentComposer` → `ToolCallCard` →
  `AgentMessage` → `WorkingIndicator` → `AgentComposer` → `AgentPanel` + `interface.ts` →
  AppShell `onClose`.

- [ ] **Run GREEN:** `pnpm -C apps/admin test` (incl. AppShell files); `pnpm -C apps/admin
  type-check`.

- [ ] **Screenshots** (iframe technique, 1440 + 390, real screen, signed in): the empty agent
  panel open over the dashboard; a completed exchange rendered through a throwaway route that
  mounts `AgentPanel` with a scripted `fetch` stub (deleted before commit — no real agent
  request from the screenshot step) showing a collapsed AND an expanded tool card; the phone
  view (full-width drawer). Store as `t23-agent-*.jpg`.

- [ ] **Gates:** `pnpm gates:admin` → clean; `pnpm -C apps/admin build` → exit 0; `git status`
  shows no throwaway route.

- [ ] **Commit:**
  `git add apps/admin/src/components/agent apps/admin/src/components/common/Button apps/admin/src/components/shell/AppShell/Component.tsx apps/admin/src/lib/copy.ts`
  `git commit -m "feat(admin): agent panel — header, suggested commands, markdown turns, collapsible tool cards, Stop (p8 t23)"`

## Verify

```bash
pnpm -C apps/admin test -- agent AppShell
pnpm gates:admin && pnpm -C apps/admin build
```

## Acceptance

- Header row; empty state with three working suggestions; user bubbles; assistant Markdown
  with tool cards interleaved at their offsets, collapsed "Ran/Running" rows that expand to
  arguments + result; Working… indicator; auto-scroll; Stop; Enter/Shift+Enter; helper line;
  inline error alert; close button wired to the shell.
- All prior agent + shell pins green (two rewritten as declared); screenshots at both widths.
