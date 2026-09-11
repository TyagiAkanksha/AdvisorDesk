import { describe, expect, it } from 'vitest';

import type { AgentTurn } from '@/components/agent/useAgentStream';

import { turnSegments } from './agentTurnSegments';

// phase-8 task-22 (C7, hook half), RED (TDD): `src/lib/agentTurnSegments.ts` does not exist yet —
// the import above fails to resolve, module-resolution RED (same accepted failure mode this
// codebase's other not-yet-existing-module tests document, e.g.
// `apps/admin/src/components/agent/useAgentStream.test.tsx`'s own header comment).
//
// Brief: .superpowers/sdd/phase-8-ui-polish/task-22-brief.md, Interfaces + Steps section — test
// code below is copied verbatim from the brief.

const args = JSON.stringify({ title: 'Roth IRA Conversion Basics' });

describe('turnSegments', () => {
  it('interleaves text and a paired call/result at the recorded offset', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: 'Creating the draft. Done.',
      events: [
        { kind: 'call', tool: 'create_draft', detail: args, textOffset: 20 },
        { kind: 'result', tool: 'create_draft', detail: 'Created d-42.', textOffset: 20 },
      ],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'text', text: 'Creating the draft. ' },
      { kind: 'tool', tool: 'create_draft', args, result: 'Created d-42.' },
      { kind: 'text', text: 'Done.' },
    ]);
  });

  it('a call without a result yet is an open tool segment', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: '',
      events: [{ kind: 'call', tool: 'search_content', detail: '{"q":"roth"}', textOffset: 0 }],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'tool', tool: 'search_content', args: '{"q":"roth"}', result: null },
    ]);
  });

  it('pairs results FIFO when the same tool is called twice', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: '',
      events: [
        { kind: 'call', tool: 'publish', detail: '{"id":"a"}', textOffset: 0 },
        { kind: 'call', tool: 'publish', detail: '{"id":"b"}', textOffset: 0 },
        { kind: 'result', tool: 'publish', detail: 'Published a', textOffset: 0 },
        { kind: 'result', tool: 'publish', detail: 'Published b', textOffset: 0 },
      ],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'tool', tool: 'publish', args: '{"id":"a"}', result: 'Published a' },
      { kind: 'tool', tool: 'publish', args: '{"id":"b"}', result: 'Published b' },
    ]);
  });

  it('a result with no matching call still renders as a tool segment', () => {
    const turn: AgentTurn = {
      role: 'assistant',
      text: 'Hi',
      events: [{ kind: 'result', tool: 'orphan', detail: 'ok', textOffset: 2 }],
    };

    expect(turnSegments(turn)).toEqual([
      { kind: 'text', text: 'Hi' },
      { kind: 'tool', tool: 'orphan', args: '', result: 'ok' },
    ]);
  });

  it('text-only and empty turns', () => {
    expect(turnSegments({ role: 'assistant', text: 'Just text.', events: [] })).toEqual([
      { kind: 'text', text: 'Just text.' },
    ]);
    expect(turnSegments({ role: 'assistant', text: '', events: [] })).toEqual([]);
    expect(turnSegments({ role: 'user', text: 'Hello', events: [] })).toEqual([
      { kind: 'text', text: 'Hello' },
    ]);
  });
});
