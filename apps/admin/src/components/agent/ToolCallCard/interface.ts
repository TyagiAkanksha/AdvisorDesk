import type { ToolEvent } from '../useAgentStream';

/** Renders one tool-call or tool-result event, in the order it arrived (PRD §5.4/§2.2: "renders
 * each tool call live as it happens"). */
export interface ToolCallCardProps {
  event: ToolEvent;
}
