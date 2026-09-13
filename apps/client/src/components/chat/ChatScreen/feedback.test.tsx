// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatScreen } from '.';

// phase-9 task-17 (DESIGN §A/D2, demo beat 5): the thumbs appear under a real assistant bubble in
// the real screen, and a click reaches the real endpoint. Only `fetch` is mocked.

function streamResponse(frames: { event: string; data: unknown }[]): Response {
  const body = frames
    .map((frame) => `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`)
    .join('');
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(body));
        controller.close();
      },
    }),
    { status: 200, headers: { 'content-type': 'text/event-stream' } },
  );
}

const ANSWER_FRAMES = [
  { event: 'token', data: { text: 'RSUs are taxed as ordinary income at vest.' } },
  { event: 'citations', data: { citations: [{ content_id: 'c-1', title: 'RSUs', slug: 'rsus' }] } },
  { event: 'done', data: { session_id: 's-1', message_id: 'm-7' } },
];

function mockChatThenFeedback(feedbackStatus: number) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    if (url.includes('/feedback')) {
      return Promise.resolve(new Response(null, { status: feedbackStatus }));
    }
    return Promise.resolve(streamResponse(ANSWER_FRAMES));
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}

async function ask(): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Message'), 'When do my RSUs vest?');
  await user.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Helpful' })).toBeInTheDocument());
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('ChatScreen feedback', () => {
  it('shows no thumbs before an answer has arrived', () => {
    mockChatThenFeedback(204);
    render(<ChatScreen />);

    expect(screen.queryByRole('button', { name: 'Helpful' })).not.toBeInTheDocument();
  });

  it('sends the rating for the answered message when a thumb is clicked', async () => {
    const { calls } = mockChatThenFeedback(204);
    render(<ChatScreen />);
    await ask();

    await userEvent.click(screen.getByRole('button', { name: 'Not helpful' }));

    await waitFor(() =>
      expect(calls.some((url) => url.includes('/api/v1/public/chat/m-7/feedback'))).toBe(true),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Not helpful' })).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
  });

  it('reverts the thumb and shows a friendly notice when the rating fails', async () => {
    mockChatThenFeedback(404);
    render(<ChatScreen />);
    await ask();

    await userEvent.click(screen.getByRole('button', { name: 'Helpful' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Helpful' })).toHaveAttribute(
        'aria-pressed',
        'false',
      ),
    );
    expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();
  });
});
