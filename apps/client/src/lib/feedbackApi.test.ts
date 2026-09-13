import { afterEach, describe, expect, it, vi } from 'vitest';

import { sendMessageFeedback } from './feedbackApi';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('sendMessageFeedback', () => {
  it('POSTs the value as JSON to the message feedback endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await sendMessageFeedback('11111111-2222-3333-4444-555555555555', -1);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/public/chat/11111111-2222-3333-4444-555555555555/feedback');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'content-type': 'application/json' });
    expect(JSON.parse(init.body as string)).toEqual({ value: -1 });
  });

  it('rejects on a non-2xx response so the caller can revert its optimistic update', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 404 })));

    await expect(sendMessageFeedback('gone', 1)).rejects.toThrow(/404/);
  });
});
