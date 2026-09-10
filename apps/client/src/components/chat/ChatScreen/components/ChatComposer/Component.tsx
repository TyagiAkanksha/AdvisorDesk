import { useEffect, useRef } from 'react';

import { Button, IconButton, Stack, TextField, Typography } from '@/components/common';
import {
  CHAT_HELPER_TEXT,
  MESSAGE_FIELD_LABEL,
  NEW_CONVERSATION_LABEL,
  SEND_LABEL,
  STOP_LABEL,
} from '@/lib/copy';

import type { ChatComposerProps } from './interface';

// phase-8 task-12 (DESIGN.md §B4). The message field + Send/Stop control + helper line + New
// conversation — a dumb form over `useChatComposer`'s draft/keyboard-rule/submit and
// `useChatStream`'s streaming/new-conversation controls, wired up by `ChatScreen`.
export default function Component({
  draft,
  onDraftChange,
  onSubmit,
  onKeyDown,
  canSend,
  streaming,
  onStop,
  onNewConversation,
  showNewConversation,
}: ChatComposerProps) {
  // fix round 1 (M-2): a Stop click or a stream finishing both leave focus nowhere obvious (the
  // Stop/Send icon button swaps out from under the pointer, or the field was disabled the whole
  // time) — restore focus to the message field so the user can keep typing without reaching for
  // the mouse. `wasStreamingRef` remembers the *previous* render's `streaming` so the effect can
  // detect the true -> false transition instead of firing on every render.
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const wasStreamingRef = useRef(streaming);

  useEffect(() => {
    if (wasStreamingRef.current && !streaming) {
      inputRef.current?.focus();
    }
    wasStreamingRef.current = streaming;
  }, [streaming]);

  const handleNewConversation = () => {
    onNewConversation();
    inputRef.current?.focus();
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      {/* MUI 9's Stack no longer exposes alignItems/justifyContent as direct props — see
          ChatWelcome's Component.tsx for the same note. */}
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
        <TextField
          label={MESSAGE_FIELD_LABEL}
          value={draft}
          onChange={onDraftChange}
          onKeyDown={onKeyDown}
          multiline
          minRows={1}
          maxRows={6}
          fullWidth
          disabled={streaming}
          inputRef={inputRef}
        />
        {streaming ? (
          <IconButton name="Stop" label={STOP_LABEL} onClick={onStop} color="primary" />
        ) : (
          <IconButton
            name="Send"
            label={SEND_LABEL}
            type="submit"
            disabled={!canSend}
            color="primary"
          />
        )}
      </Stack>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'center', mt: 0.5 }}
      >
        <Typography variant="caption" color="text.secondary">
          {CHAT_HELPER_TEXT}
        </Typography>
        {showNewConversation && (
          <Button variant="text" size="small" onClick={handleNewConversation}>
            {NEW_CONVERSATION_LABEL}
          </Button>
        )}
      </Stack>
    </form>
  );
}
