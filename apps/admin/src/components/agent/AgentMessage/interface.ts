import type { AgentTurn } from '../useAgentStream';

/** Renders one full turn — a user command or an assistant reply with its interleaved tool
 * events. */
export interface AgentMessageProps {
  turn: AgentTurn;
}
