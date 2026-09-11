// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { PREVIEW_EMPTY_MESSAGE } from '@/lib/copy';
import { formatDate } from '@/lib/format';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// task-06 / PRD §2.2 (editor story), §4 (slug immutable — display-only, never editable),
// §5.2 (PATCH tri-state + transition endpoints). `ContentEditorScreen` does not exist yet —
// every test below is RED until the implementer creates it (task-06 Step 3/4). Mock ONLY the
// network edge (fetch) and the next/navigation framework seam
// (docs/FRONTEND-CONVENTIONS.md §7), mirroring RequireSession/AppShell's Component.test.tsx
// idiom exactly.
const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

// --- Contract pinned by this file (test-author decision, task-06 Interfaces) -------------
// `ContentEditorScreenProps { contentId?: string }` — omitted/`undefined` => NEW mode (blank
// form; submitting POSTs and routes to the created item's page); a string id => EDIT mode
// (loads via `getContent`, prefills, submitting PATCHes). This mirrors the thin-page split in
// the brief's Files list: `content/new/page.tsx` renders `<ContentEditorScreen/>`;
// `content/[id]/page.tsx` reads `useParams().id` and renders
// `<ContentEditorScreen contentId={id}/>` (thin pages are not under test here — only the
// screen they render).
//
// Accessible-name contract pinned by this file:
//   textbox  "Title"
//   textbox  "Body" (label text: "Body (Markdown)" — the raw markdown source, not rendered)
//   combobox "Tags" — MUI Autocomplete, freeSolo, multiple, normalizing entries to
//                     lowercase-hyphen (mirrors app.services.tags._normalize_tag_name)
//   button   "Create" (NEW mode submit) / "Save" (EDIT mode submit)
//   button   "Publish" / "Archive" / "Delete" / "Preview" — enabled per the status matrix
//   region   "Markdown preview" (aria-label) — appears once "Preview" is activated
//   alert    surfaces a failed save's §9 envelope `message` (never the raw body)
// -------------------------------------------------------------------------------------------

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

function pathnameOf(input: RequestInfo | URL): string {
  return new URL(requestUrl(input)).pathname;
}

async function requestJson(input: RequestInfo | URL): Promise<unknown> {
  if (input instanceof Request) {
    return input.clone().json();
  }
  return undefined;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const NEW_CONTENT_ID = '99999999-9999-9999-9999-999999999999';

const draftFixture: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics\n\nBody.',
  created_at: '2026-01-01T00:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-01-02T00:00:00Z',
  updated_by: null,
};

const publishedFixture: ContentDto = {
  ...draftFixture,
  id: '22222222-2222-2222-2222-222222222222',
  slug: 'estate-planning-101',
  status: 'published',
  published_at: '2025-12-05T00:00:00Z',
  title: 'Estate Planning 101',
};

const archivedFixture: ContentDto = {
  ...draftFixture,
  id: '33333333-3333-3333-3333-333333333333',
  slug: 'social-security-timing',
  status: 'archived',
  title: 'Social Security Timing',
};

interface MockFetchOptions {
  getContentResponse?: Response;
  createContentResponse?: Response;
  updateContentResponse?: Response;
  publishContentResponse?: Response;
  archiveContentResponse?: Response;
  tagsResponse?: Response;
}

function mockFetch(options: MockFetchOptions = {}) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'POST') {
        return (
          options.createContentResponse ??
          jsonResponse({ ...draftFixture, id: NEW_CONTENT_ID }, 201)
        );
      }
      if (pathname.endsWith('/publish') && method === 'POST') {
        return (
          options.publishContentResponse ??
          jsonResponse({
            ...draftFixture,
            status: 'published',
            published_at: '2026-04-01T00:00:00Z',
          })
        );
      }
      if (pathname.endsWith('/archive') && method === 'POST') {
        return (
          options.archiveContentResponse ?? jsonResponse({ ...draftFixture, status: 'archived' })
        );
      }
      if (pathname.startsWith('/api/v1/content/') && method === 'GET') {
        return options.getContentResponse ?? jsonResponse(draftFixture);
      }
      if (pathname.startsWith('/api/v1/content/') && method === 'PATCH') {
        return options.updateContentResponse ?? jsonResponse(draftFixture);
      }
      if (pathname === '/api/v1/tags' && method === 'GET') {
        return options.tagsResponse ?? jsonResponse([]);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderNew() {
  return render(
    <Providers>
      <ContentEditorScreen />
    </Providers>,
  );
}

function renderEdit(contentId: string) {
  return render(
    <Providers>
      <ContentEditorScreen contentId={contentId} />
    </Providers>,
  );
}

describe('ContentEditorScreen', () => {
  beforeEach(() => {
    pushMock.mockClear();
    replaceMock.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('NEW mode: renders labeled Title, Body, and Tags fields with nothing prefilled', async () => {
    mockFetch();

    renderNew();

    expect(await screen.findByRole('textbox', { name: /title/i })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: /body/i })).toHaveValue('');
    expect(screen.getByRole('combobox', { name: /tags/i })).toBeInTheDocument();
  });

  it('NEW mode: submitting the form POSTs {title, body_md, tags} and routes to /content/{id}', async () => {
    const fetchMock = mockFetch({
      createContentResponse: jsonResponse(
        {
          ...draftFixture,
          id: NEW_CONTENT_ID,
          title: 'New Piece',
          body_md: '# New body',
          tags: ['retirement'],
        },
        201,
      ),
    });
    const user = userEvent.setup();

    renderNew();

    await user.type(screen.getByRole('textbox', { name: /title/i }), 'New Piece');
    await user.type(screen.getByRole('textbox', { name: /body/i }), '# New body');
    await user.type(screen.getByRole('combobox', { name: /tags/i }), 'retirement');
    await user.keyboard('{Enter}');

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'POST',
      );
      expect(call).toBeDefined();
    });
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'POST',
    )!;
    const body = await requestJson(createCall[0]);
    expect(body).toEqual({ title: 'New Piece', body_md: '# New body', tags: ['retirement'] });

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(`/content/${NEW_CONTENT_ID}`);
    });
  });

  // MUI Autocomplete-testing caveat (see the test-author report for the full note): embedding
  // `{Enter}` inside the SAME `user.type()` string that types the tag text was unreliable —
  // `useAutocomplete`'s keydown handler treats Enter differently depending on the popup's
  // highlighted-option state mid-keystroke. Typing the text and THEN issuing a separate
  // `user.keyboard('{Enter}')` once the input holds the full string is the freeSolo
  // "commit as a new option" path (`selectNewValue(..., 'createOption', 'freeSolo')` in MUI's
  // `useAutocomplete.js`) — reliable regardless of typing speed/timing.
  it('NEW mode: typing "Tax Planning" then Enter in Tags normalizes to lowercase-hyphen before submit', async () => {
    const fetchMock = mockFetch({
      createContentResponse: jsonResponse(
        { ...draftFixture, id: NEW_CONTENT_ID, title: 'Ambiguity', tags: ['tax-planning'] },
        201,
      ),
    });
    const user = userEvent.setup();

    renderNew();

    await user.type(screen.getByRole('textbox', { name: /title/i }), 'Ambiguity');
    await user.type(screen.getByRole('textbox', { name: /body/i }), 'Body text');

    const tagsInput = screen.getByRole('combobox', { name: /tags/i });
    await user.type(tagsInput, 'Tax Planning');
    await user.keyboard('{Enter}');

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'POST',
      );
      expect(call).toBeDefined();
    });
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'POST',
    )!;
    const body = (await requestJson(createCall[0])) as { tags: string[] };
    expect(body.tags).toContain('tax-planning');
  });

  it('EDIT mode: Title, Body, and Tags are prefilled from the loaded content', async () => {
    mockFetch({ getContentResponse: jsonResponse(draftFixture) });

    renderEdit(draftFixture.id);

    expect(await screen.findByRole('textbox', { name: /title/i })).toHaveValue(draftFixture.title);
    expect(screen.getByRole('textbox', { name: /body/i })).toHaveValue(draftFixture.body_md);
    for (const tag of draftFixture.tags) {
      expect(screen.getByText(tag)).toBeInTheDocument();
    }
  });

  it('EDIT mode: slug is visible read-only text — no textbox control named "slug"', async () => {
    mockFetch({ getContentResponse: jsonResponse(draftFixture) });

    renderEdit(draftFixture.id);

    expect(await screen.findByText(draftFixture.slug)).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /slug/i })).not.toBeInTheDocument();
  });

  it('status=draft: Publish is enabled, Archive is absent-or-disabled, Delete is present; clicking Publish POSTs the publish transition URL', async () => {
    const fetchMock = mockFetch({ getContentResponse: jsonResponse(draftFixture) });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);

    const publishButton = await screen.findByRole('button', { name: /publish/i });
    expect(publishButton).toBeEnabled();

    const archiveButton = screen.queryByRole('button', { name: /archive/i });
    if (archiveButton) {
      expect(archiveButton).toBeDisabled();
    }

    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();

    await user.click(publishButton);

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === `/api/v1/content/${draftFixture.id}/publish` &&
          requestMethod(input, init) === 'POST',
      );
      expect(call).toBeDefined();
    });
  });

  it('status=published: Archive is enabled, Publish is absent-or-disabled, Delete is present', async () => {
    mockFetch({ getContentResponse: jsonResponse(publishedFixture) });

    renderEdit(publishedFixture.id);

    const archiveButton = await screen.findByRole('button', { name: /archive/i });
    expect(archiveButton).toBeEnabled();

    const publishButton = screen.queryByRole('button', { name: /publish/i });
    if (publishButton) {
      expect(publishButton).toBeDisabled();
    }

    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });

  it('status=archived: Publish (re-publish) is enabled, Delete is present', async () => {
    mockFetch({ getContentResponse: jsonResponse(archivedFixture) });

    renderEdit(archivedFixture.id);

    const publishButton = await screen.findByRole('button', { name: /publish/i });
    expect(publishButton).toBeEnabled();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });

  it('a failed save (PATCH -> 500 envelope) surfaces the envelope message as an alert, never the raw JSON body', async () => {
    const FAILURE_MESSAGE = 'Could not save due to a validation conflict.';
    mockFetch({
      getContentResponse: jsonResponse(draftFixture),
      updateContentResponse: jsonResponse(
        { error: { code: 'conflict', message: FAILURE_MESSAGE } },
        500,
      ),
    });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);

    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed Title');
    await user.click(screen.getByRole('button', { name: /save/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(FAILURE_MESSAGE);

    // Never the raw envelope body (docs/FRONTEND-CONVENTIONS.md §9) — not the serialized
    // JSON string, and not the `error.code` value, anywhere in the rendered document.
    const rawEnvelope = JSON.stringify({ error: { code: 'conflict', message: FAILURE_MESSAGE } });
    expect(document.body.textContent).not.toContain(rawEnvelope);
    expect(document.body.textContent).not.toContain('"code":"conflict"');
  });

  it('desktop: the live preview renders beside the form, with no Preview toggle, and mirrors the body', async () => {
    mockFetch();

    renderEdit(draftFixture.id);

    await screen.findByRole('textbox', { name: /title/i });
    const previewRegion = screen.getByRole('region', { name: 'Preview' });
    expect(previewRegion).toHaveTextContent('Body.');
    expect(screen.queryByRole('button', { name: /^preview$/i })).not.toBeInTheDocument();
  });

  it('edit mode: the header shows the saved title as h1 with status chip, slug and dates', async () => {
    mockFetch();

    renderEdit(draftFixture.id);

    expect(
      await screen.findByRole('heading', { level: 1, name: draftFixture.title }),
    ).toBeInTheDocument();
    const header = screen.getByRole('banner');
    expect(within(header).getByText('Draft')).toBeInTheDocument();
    expect(within(header).getByText(draftFixture.slug)).toBeInTheDocument();
    expect(
      within(header).getByText(`Created ${formatDate(draftFixture.created_at)}`),
    ).toBeInTheDocument();
    expect(
      within(header).getByText(`Updated ${formatDate(draftFixture.updated_at)}`),
    ).toBeInTheDocument();
    expect(within(header).queryByText(/^Published /)).not.toBeInTheDocument();
  });

  it('edit mode: the h1 keeps the SAVED title while the Title field is edited', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Renamed');

    expect(screen.getByRole('heading', { level: 1, name: draftFixture.title })).toBeInTheDocument();
  });

  it('new mode: the h1 is "New content" and Publish is disabled with a "Save first" tooltip', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderNew();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'New content' }),
    ).toBeInTheDocument();
    const publish = screen.getByRole('button', { name: /publish/i });
    expect(publish).toBeDisabled();
    await user.hover(publish.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Save first');
  });

  it('new mode: the preview region shows the empty-preview message before any content is typed', async () => {
    mockFetch();

    renderNew();

    const region = await screen.findByRole('region', { name: 'Preview' });
    expect(within(region).getByText(PREVIEW_EMPTY_MESSAGE)).toBeInTheDocument();
  });

  it('published: Publish is disabled with an "Already published" tooltip; Archive is enabled', async () => {
    mockFetch({ getContentResponse: jsonResponse(publishedFixture) });
    const user = userEvent.setup();

    renderEdit(publishedFixture.id);

    const publish = await screen.findByRole('button', { name: /publish/i });
    expect(publish).toBeDisabled();
    await user.hover(publish.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Already published');
    expect(screen.getByRole('button', { name: /archive/i })).toBeEnabled();
  });

  it('the preview strips a leading "# Title" matching the title and demotes the remaining headings', async () => {
    mockFetch({
      getContentResponse: jsonResponse({
        ...draftFixture,
        body_md: '# Roth IRA Conversion Basics\n\n## Section\n\nText.',
      }),
    });

    renderEdit(draftFixture.id);

    const region = await screen.findByRole('region', { name: 'Preview' });
    expect(within(region).queryByRole('heading', { level: 1 })).not.toBeInTheDocument();
    expect(
      within(region).queryByRole('heading', { name: 'Roth IRA Conversion Basics' }),
    ).not.toBeInTheDocument();
    expect(within(region).getByRole('heading', { level: 3, name: 'Section' })).toBeInTheDocument();
  });

  it('Delete uses the error colour and opens a destructive confirm', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    const deleteButton = await screen.findByRole('button', { name: /^delete$/i });
    expect(deleteButton).toHaveClass('MuiButton-colorError');

    await user.click(deleteButton);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: /delete/i })).toHaveClass(
      'MuiButton-colorError',
    );
  });

  it('a blank Title shows "Title is required" after blur and blocks submit', async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();

    renderNew();
    const title = screen.getByRole('textbox', { name: /title/i });
    await user.click(title);
    await user.tab();

    expect(screen.getByText('Title is required')).toBeInTheDocument();
    expect(title).toBeInvalid();
    expect(
      fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'POST'),
    ).toBe(false);
  });

  it('pressing Enter in the Title field submits the form', async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    const title = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(title);
    await user.type(title, 'Renamed{Enter}');

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'PATCH'),
      ).toBe(true),
    );
  });

  it('the Body field is monospace and Tags suggest existing tag names', async () => {
    mockFetch({ tagsResponse: jsonResponse([{ id: 't1', name: 'retirement', count: 2 }]) });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);

    expect(await screen.findByRole('textbox', { name: /body/i })).toHaveStyle({
      fontFamily: 'monospace',
    });
    await user.click(screen.getByRole('combobox', { name: /tags/i }));
    expect(await screen.findByRole('option', { name: 'retirement' })).toBeInTheDocument();
  });

  it('edit mode: shows an editor-shaped skeleton (labelled Loading, no spinner) while loading', () => {
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderEdit(draftFixture.id);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });
});
