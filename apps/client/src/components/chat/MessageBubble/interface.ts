import type { ChatFeedbackValue } from '@/types';

import type { ChatMessage } from '../useChatStream';

export interface MessageBubbleProps {
  message: ChatMessage;
  /**
   * Rendered as the 👍/👎 control under an assistant answer, when the parent has an id to rate
   * (phase-9 task-17). One grouped prop rather than three loose ones: they are meaningless apart,
   * and `undefined` is the single "this turn is not rateable" signal.
   */
  feedback?: {
    value: ChatFeedbackValue | null;
    disabled: boolean;
    onSelect: (value: ChatFeedbackValue) => void;
  };
}
