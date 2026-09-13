import type { ChatFeedbackValue } from '@/types';

/**
 * phase-9 task-17 (DESIGN §A/D2): the 👍/👎 control under an assistant answer — the only human
 * ground truth this app collects. Dumb leaf (docs/FRONTEND-CONVENTIONS.md §3): renders the
 * current rating and raises a choice; no state, no fetching.
 */
export interface FeedbackButtonsProps {
  /** The current rating, or `null` when the reader hasn't rated this answer. */
  value: ChatFeedbackValue | null;
  /** Disables both buttons (a request for this message is in flight). */
  disabled?: boolean;
  onSelect: (value: ChatFeedbackValue) => void;
}
