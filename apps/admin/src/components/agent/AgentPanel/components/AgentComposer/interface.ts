import type { UseAgentComposerResult } from '../../useAgentComposer';

/** Dumb composer leaf: the draft value, the Enter/Shift+Enter key rule, and the Send/Stop swap
 * are all owned by `useAgentComposer`/`useAgentStream` — this component only renders them. */
export interface AgentComposerProps {
  value: string;
  onChange: (value: string) => void;
  onKeyDown: UseAgentComposerResult['onKeyDown'];
  onSubmit: () => void;
  canSend: boolean;
  streaming: boolean;
  onStop: () => void;
}
