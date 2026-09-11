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
  //
  // p8 final (I-3): only restore focus when the user hasn't moved elsewhere in the meantime —
  // either focus is still inside this form, or it's sitting on `document.body` (the field was
  // disabled while streaming, which is where a browser parks focus). If the user has clicked into
  // some other control (nav, another form), leave their focus alone.
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const wasStreamingRef = useRef(streaming);

  useEffect(() => {
    if (
      wasStreamingRef.current &&
      !streaming &&
      (document.activeElement === document.body ||
        formRef.current?.contains(document.activeElement))
    ) {
      inputRef.current?.focus({ preventScroll: true });
    }
    wasStreamingRef.current = streaming;
  }, [streaming]);

  const handleNewConversation = () => {
    onNewConversation();
    inputRef.current?.focus();
  };

  return (
    <form
      ref={formRef}
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
