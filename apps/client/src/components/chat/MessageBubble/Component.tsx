import { Typography } from '@/components/common';
import { Markdown } from '@/components/content/Markdown';

import { CitationList } from '../CitationList';
import type { MessageBubbleProps } from './interface';

// task-05 (phase-4), PRD §2.2/§5.3. Dumb, one purpose: render one turn. `role="article"` named
// "You"/"Assistant" per message (test-author judgment call, `p4-t05-test-author.md`) — native
// `<article>` carries that role implicitly. A refusal (`refusal: true`, PRD §7.4/§7.5) wraps its
// content in `role="status"`, mirroring `common/EmptyState`'s existing precedent
// (docs/FRONTEND-CONVENTIONS.md §9) rather than inventing a new pattern; a normal assistant
// answer renders the same content with no such wrapper.
export default function Component({ message }: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <article aria-label="You">
        <Typography component="p">{message.text}</Typography>
      </article>
    );
  }

  const citations = message.citations ?? [];
  const answer = (
    <>
      <Markdown markdown={message.text} />
      <CitationList citations={citations} />
    </>
  );

  return (
    <article aria-label="Assistant">
      {message.refusal ? <div role="status">{answer}</div> : answer}
    </article>
  );
}
