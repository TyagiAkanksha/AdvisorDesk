import type { AgentTurn } from '@/components/agent/useAgentStream';

// phase-8 task-22 (C7, hook half), DESIGN.md §5 C7: render tool cards INTERLEAVED with the text
// segments they interrupted, in arrival order, rather than all text first then a flat list of
// tool events. `turnSegments` is the pure mapping from a turn's `text` + `events` (as recorded by
// `useAgentStream.ts`'s `appendAssistantEvent`) to that ordered, panel-ready list — no UI here.

/** A run of assistant/user text between (or around) tool cards. */
export interface TextSegment {
  kind: 'text';
  text: string;
}

/** One tool call rendered as a card, paired with its result once the result event arrives. */
export interface ToolSegment {
  kind: 'tool';
  tool: string;
  /** The call's `detail` (compact JSON of the arguments); '' for a result with no matching call. */
  args: string;
  /** The result's `detail` (result_summary), or null while the call is still running. */
  result: string | null;
}

export type TurnSegment = TextSegment | ToolSegment;

/**
 * Walk `turn.events` in order. A 'call' closes the current text run at `event.textOffset`
 * (emitting a text segment if non-empty), then opens a tool segment. A 'result' fills the
 * EARLIEST still-open tool segment with the same `tool` (FIFO — results arrive in execution
 * order); a result with no open call cuts the text at ITS offset and opens its own segment with
 * `args: ''`. Trailing text after the last cut becomes the final text segment. A turn with no
 * events → [{ kind: 'text', text }] (or [] when text is ''). Text between a call and its result
 * is attributed AFTER the card. Pure.
 */
export function turnSegments(turn: AgentTurn): TurnSegment[] {
  const { text, events } = turn;

  if (events.length === 0) {
    return text === '' ? [] : [{ kind: 'text', text }];
  }

  const segments: TurnSegment[] = [];
  let cursor = 0;

  const cutTextTo = (offset: number): void => {
    if (offset > cursor) {
      segments.push({ kind: 'text', text: text.slice(cursor, offset) });
      cursor = offset;
    }
  };

  const isOpenSegmentFor =
    (tool: string) =>
    (segment: TurnSegment): segment is ToolSegment =>
      segment.kind === 'tool' && segment.tool === tool && segment.result === null;

  for (const event of events) {
    if (event.kind === 'call') {
      cutTextTo(event.textOffset);
      segments.push({ kind: 'tool', tool: event.tool, args: event.detail, result: null });
      continue;
    }

    const openIndex = segments.findIndex(isOpenSegmentFor(event.tool));
    if (openIndex === -1) {
      cutTextTo(event.textOffset);
      segments.push({ kind: 'tool', tool: event.tool, args: '', result: event.detail });
      continue;
    }
    const open = segments[openIndex] as ToolSegment;
    segments[openIndex] = { ...open, result: event.detail };
  }

  cutTextTo(text.length);

  return segments;
}
