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
          // Index-as-key is safe here: `messages` is append-only, never reordered or spliced.
          <MessageBubble key={index} message={message} />
        ))
      )}
      {awaitingFirstToken && <ThinkingIndicator />}
      {error !== null && (
        <Alert
          severity="error"
          action={
            <Button size="small" color="inherit" onClick={retry}>
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
