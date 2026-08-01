// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import type { Citation } from '../useChatStream';
import { CitationList } from '.';

// task-05 (phase-4), RED (TDD): `CitationList/Component.tsx` and `../useChatStream` do not exist
// yet — both imports above fail to resolve, the expected RED failure (test-author brief STOP
// RULE).
//
// Brief Interfaces (docs/plans/phase-4-rag-assistant/task-05-client-chat-ui.md): "`CitationList`:
// numbered `[n]` chips linking to `/content/{slug}` (the p3-t04 route), order = server order
// (first use)." The server has already deduped-and-ordered the array
// (apps/api/tests/test_public_chat.py::test_citation_asymmetry_wire_deduped_content_level_row_chunk_level_from_one_exchange)
// — `CitationList` is a pure, order-preserving renderer over whatever array it receives, no
// re-sorting or deduping of its own.
//
// Judgment call (test-author, flagged for controller review, consistent with
// `ChatScreen/Component.test.tsx` and `MessageBubble/Component.test.tsx`): each chip's accessible
// name is its visible numbering text alone (`'[1]'`, `'[2]'`, ...) — simplest literal reading of
// "numbered `[n]` chips" from the brief; the citation's `title` is available in the DOM (assumed
// visible/tooltip text) but not part of the pinned accessible name this test locks in.

describe('CitationList', () => {
  it('renders one numbered [n] chip per citation, in the given order, each linking to /content/{slug}', () => {
    const citations: Citation[] = [
      { content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' },
      { content_id: 'c-2', title: 'Traditional IRA Basics', slug: 'traditional-ira-basics' },
    ];

    render(<CitationList citations={citations} />);

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAccessibleName('[1]');
    expect(links[0]).toHaveAttribute('href', '/content/roth-ira-basics');
    expect(links[1]).toHaveAccessibleName('[2]');
    expect(links[1]).toHaveAttribute('href', '/content/traditional-ira-basics');
  });

  it('renders no links for an empty citations array', () => {
    render(<CitationList citations={[]} />);

    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });
});
