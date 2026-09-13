import { resolveBrowserApiBaseUrl } from './browserApiBase';
import type { ChatFeedbackRequest, ChatFeedbackValue } from '@/types';

/**
 * The network edge for `POST /api/v1/public/chat/{message_id}/feedback` (phase-9 DESIGN §A/D2).
 *
 * A plain async function, not a hook and not RTK Query: `apps/client` uses RSC + hand-rolled
 * hooks and has no RTK store (docs/FRONTEND-CONVENTIONS.md §6). The one thing this module owns is
 * "what goes on the wire"; all state, optimism and error copy live in `useMessageFeedback`.
 *
 * @throws Error on any non-2xx response — including the 404 a pruned/unknown `message_id` gives.
 *   The caller turns that into friendly copy (§9: raw bodies are never rendered); this function
 *   deliberately does not read the body, since 204 has none and the failure modes here are not
 *   user-actionable.
 */
export async function sendMessageFeedback(
  messageId: string,
  value: ChatFeedbackValue,
): Promise<void> {
  const body: ChatFeedbackRequest = { value };
  const response = await fetch(
    `${resolveBrowserApiBaseUrl()}/api/v1/public/chat/${encodeURIComponent(messageId)}/feedback`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    throw new Error(`Feedback request failed: ${response.status}`);
  }
}
