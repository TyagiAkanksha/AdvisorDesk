import type { ToolSegment } from '@/lib/agentTurnSegments';

/** Renders one tool-call segment (PRD §5.4/§2.2: "renders each tool call live as it happens") as
 * a collapsible card — collapsed to a one-line summary, expanding to arguments + result. */
export interface ToolCallCardProps {
  segment: ToolSegment;
}
