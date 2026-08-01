'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';

import { Button, ErrorState, TextField } from '@/components/common';

import { MessageBubble } from '../MessageBubble';
import { useChatStream } from '../useChatStream';

// task-05 (phase-4), PRD §2.2. The client island: unlike the RSC `content/` screens, this
// screen owns its own VM hook (docs/FRONTEND-CONVENTIONS.md §6) and takes no props — a zero-prop
// component has no `interface.ts` (§3). Input is disabled while streaming to prevent overlapping
// sends; a stream/rate-limit error (PRD §9) surfaces through `ErrorState`'s existing friendly-copy
// contract, never a raw envelope.
export default function Component() {
  const { messages, streaming, error, send } = useChatStream();
  const [draft, setDraft] = useState('');

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = draft.trim();
    if (question.length === 0 || streaming) {
      return;
    }
    send(question);
    setDraft('');
  };

  return (
    <div>
      <div>
        {messages.map((message, index) => (
          // Index-as-key is safe here: `messages` is append-only, never reordered or spliced.
          <MessageBubble key={index} message={message} />
        ))}
      </div>
      {error !== null && <ErrorState message={error} />}
      <form onSubmit={handleSubmit}>
        <TextField
          label="Message"
          value={draft}
          onChange={setDraft}
          disabled={streaming}
          fullWidth
        />
        <Button type="submit" disabled={streaming}>
          Send
        </Button>
      </form>
    </div>
  );
}
