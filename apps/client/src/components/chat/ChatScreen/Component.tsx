'use client';

import { Alert, Box, Button } from '@/components/common';
import { RETRY_LABEL } from '@/lib/copy';

import { MessageBubble } from '../MessageBubble';
import { useChatStream } from '../useChatStream';
import { ChatComposer } from './components/ChatComposer';
import { ChatWelcome } from './components/ChatWelcome';
import { ThinkingIndicator } from './components/ThinkingIndicator';
import { useChatComposer } from './useChatComposer';

// task-05 (phase-4), PRD §2.2. phase-8 task-12 (DESIGN.md §B4): rebuilt as a dumb composition
// over two hooks — `useChatStream` (the conversation) and `useChatComposer` (the draft/keyboard
// rule) — with no business logic of its own. The client island: unlike the RSC `content/`
// screens, it owns its VM hooks and takes no props (a zero-prop component has no
// `interface.ts`, docs/FRONTEND-CONVENTIONS.md §3).
export default function Component() {
  const { messages, streaming, error, send, stop, reset, retry } = useChatStream();
  const composer = useChatComposer({ disabled: streaming, onSend: send });
  const awaitingFirstToken = streaming && messages[messages.length - 1]?.role === 'user';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '60vh' }}>
      {messages.length === 0 ? (
        <ChatWelcome onAsk={send} />
      ) : (
        messages.map((message, index) => (
          // fix round 1 (M-3): index-as-key is safe here because every surviving index keeps
          // identical content across re-renders — `retry` (task 11) slices the array back to
          // (but not including) the last user message and then re-sends that exact same text,
          // so indices 0..n-1 are untouched and only new indices are appended; `reset` empties
          // the array outright, so no stale index survives at all. Neither path reorders or
          // mutates content in place at an existing index.
          <MessageBubble key={index} message={message} />
        ))
      )}
      {awaitingFirstToken && <ThinkingIndicator />}
      {error !== null && (
        <Alert
          severity="error"
          action={
            // fix round 1 (M-4): disabled while streaming — a retry can only fire once the
            // failed request has actually finished unwinding (matches `useChatStream.retry`'s
            // own re-entrancy guard, which is a silent no-op mid-stream).
            <Button size="small" color="inherit" onClick={retry} disabled={streaming}>
              {RETRY_LABEL}
            </Button>
          }
        >
          {error}
        </Alert>
      )}
      <Box
        sx={{
          position: 'sticky',
          bottom: 0,
          bgcolor: 'background.default',
          pt: 2,
          pb: 1,
          mt: 'auto',
        }}
      >
        <ChatComposer
          draft={composer.draft}
          onDraftChange={composer.setDraft}
          onSubmit={composer.submit}
          onKeyDown={composer.onKeyDown}
          canSend={composer.canSend}
          streaming={streaming}
          onStop={stop}
          onNewConversation={reset}
          showNewConversation={messages.length > 0}
        />
      </Box>
    </Box>
  );
}
