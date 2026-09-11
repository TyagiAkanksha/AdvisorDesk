---
id: p8-t20
phase: phase-8-ui-polish
depends_on: [p8-t19]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 20 — Editor screen: header meta, split live preview, action row, destructive delete (C5, screen half)

## Goal

Rebuild the editor on task 19's hook: `PageHeader` showing the saved title (or "New content"),
a status chip and slug/created/updated/published meta; at `md`+ a two-column layout — the form
left, a sticky live preview right (`MarkdownPreview` with `stripLeadingHeading` +
`headingOffset={1}` so the preview matches the public article page); below `md` a
Preview/Edit toggle in the header swaps the two; a real `<form>` (Enter in Title submits) with a
required Title (error + helper text), a monospace Body, Tags with suggestions; an action row —
Save/Create (contained), Publish (tooltip explains why when disabled), Archive (only when
published), spacer, Delete (`color="error"` → destructive confirm); an editor-shaped skeleton
while loading.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2, §5 C5, §3 A2 (Markdown `headingOffset`
  semantics: DOM level shifts by the offset; a `##` renders as `<h3>`).
- `docs/FRONTEND-CONVENTIONS.md` §3 (leaf components; ≤150-line split rule), §7, §9.
- `apps/admin/src/components/content/ContentEditorScreen/{Component.tsx, useContentEditor.ts,
  interface.ts, Component.test.tsx}` — the hook's full result (task 19) and the pins listed
  below. The other five test files in the folder are untouched and must stay green.
- `apps/client/src/lib/{markdown.ts, markdown.test.ts}` — copied VERBATIM into
  `apps/admin/src/lib/` (sub-phase A shipped the helper only in the client).
- `apps/admin/src/components/content/MarkdownPreview/{interface.ts}` (`variant`,
  `headingOffset`).
- `apps/admin/src/components/common/{PageHeader,Grid,Paper,Stack,Divider,Box,Button,TextField,
  Autocomplete,StatusChip,Tooltip,Typography,Skeleton,ConfirmDialog,ErrorState}/`,
  `common/useBreakpointDown/`, `apps/admin/src/testing/matchMedia.ts`.
- `apps/admin/src/lib/{format.ts, copy.ts}`.

## Files

**Create**
- `src/lib/markdown.ts`, `src/lib/markdown.test.ts` (verbatim copies of the client files)
- `src/components/content/ContentEditorScreen/components/EditorMeta/{Component.tsx, interface.ts, index.ts}`
- `src/components/content/ContentEditorScreen/components/EditorForm/{Component.tsx, interface.ts, index.ts}`
- `src/components/content/ContentEditorScreen/components/EditorPreview/{Component.tsx, interface.ts, index.ts}`
- `src/components/content/ContentEditorScreen/components/EditorSkeleton/{Component.tsx, index.ts}`
- `src/components/content/ContentEditorScreen/responsivePreview.test.tsx`

**Modify**
- `src/components/content/ContentEditorScreen/Component.tsx`
- `src/components/content/ContentEditorScreen/Component.test.tsx` (one pin rewritten, cases
  appended — see RED)
- `src/lib/copy.ts`

## Interfaces

```ts
// src/lib/copy.ts additions
// NEW_CONTENT_LABEL ('New content'), EDIT_LABEL ('Edit'), DELETE_LABEL ('Delete') already exist (task 18)
export const PREVIEW_LABEL = 'Preview';
export const TITLE_FIELD_LABEL = 'Title';
export const BODY_FIELD_LABEL = 'Body (Markdown)';
export const TAGS_FIELD_LABEL = 'Tags';
export const PUBLISH_LABEL = 'Publish';
export const ARCHIVE_LABEL = 'Archive';
export const PUBLISH_SAVE_FIRST_TOOLTIP = 'Save first';
export const PUBLISH_ALREADY_TOOLTIP = 'Already published';
export const META_CREATED_PREFIX = 'Created';
export const META_UPDATED_PREFIX = 'Updated';
export const META_PUBLISHED_PREFIX = 'Published';

// components/EditorMeta/interface.ts — the header's second line (edit mode only)
export interface EditorMetaProps {
  slug: string;
  status: ContentStatus;
  createdAt: string;
  updatedAt: string;
  publishedAt: string | null;
}
// Render: <Stack direction="row" spacing={1} divider={<Divider orientation="vertical" flexItem />}
//   sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
//   <StatusChip status={status} />
//   <Typography variant="body2" color="text.secondary" component="span">{slug}</Typography>
//   <Typography …>{`${META_CREATED_PREFIX} ${formatDate(createdAt)}`}</Typography>
//   <Typography …>{`${META_UPDATED_PREFIX} ${formatDate(updatedAt)}`}</Typography>
//   {publishedAt ? <Typography …>{`${META_PUBLISHED_PREFIX} ${formatDate(publishedAt)}`}</Typography> : null}
// </Stack>   — each value is its OWN element (the existing "slug is visible" pin uses an exact-text query)

// components/EditorForm/interface.ts — the form + action row. Takes the hook RESULT as its one
// prop (a type import, not a hook call — the leaf stays dumb; ruled at plan time to keep the
// prop list sane).
export interface EditorFormProps {
  editor: UseContentEditorResult;
  onDelete: () => void;
}
// Render: <Box component="form" noValidate onSubmit={(e) => { e.preventDefault(); editor.onSubmit(); }}>
//   <Stack spacing={2}>
//     <TextField label={TITLE_FIELD_LABEL} value onChange required error={editor.titleError !== null}
//                helperText={editor.titleError ?? undefined} onBlur={editor.onTitleBlur} fullWidth />
//     <TextField label={BODY_FIELD_LABEL} value onChange multiline minRows={16} monospace fullWidth />
//     <Autocomplete label={TAGS_FIELD_LABEL} value onChange options={editor.tagOptions} />
//     <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
//       <Button type="submit" variant="contained" disabled={!editor.canSubmit || editor.isSaving}>{editor.submitLabel}</Button>
//       {publishButton}
//       {editor.canArchive ? <Button variant="outlined" onClick={editor.onArchive} disabled={editor.isTransitioning || editor.isSaving}>{ARCHIVE_LABEL}</Button> : null}
//       <Box sx={{ flexGrow: 1 }} />
//       {editor.mode === 'edit' ? <Button variant="outlined" color="error" onClick={onDelete}>{DELETE_LABEL}</Button> : null}
//     </Stack>
//   </Stack>
// </Box>
// publishButton: const reason = editor.mode === 'new' ? PUBLISH_SAVE_FIRST_TOOLTIP
//   : editor.status === 'published' ? PUBLISH_ALREADY_TOOLTIP : null;
//   const button = <Button variant="outlined" onClick={editor.onPublish}
//     disabled={reason !== null || !editor.canPublish || editor.isTransitioning || editor.isSaving}>{PUBLISH_LABEL}</Button>;
//   reason ? <Tooltip title={reason} describeChild><span>{button}</span></Tooltip> : button
//   (a disabled button cannot receive pointer events — MUI's documented `<span>` wrapper idiom)

// components/EditorPreview/interface.ts
export interface EditorPreviewProps {
  title: string;
  body: string;
}
// Render: <Paper variant="outlined" sx={{ p: 3, position: { md: 'sticky' }, top: { md: 88 } }}>
//   <Box component="section" aria-label={PREVIEW_LABEL}>
//     <MarkdownPreview markdown={stripLeadingHeading(body, title)} variant="article" headingOffset={1} />
//   </Box></Paper>
// (88 = 64px AppBar + 24px main padding at md+.)

// components/EditorSkeleton — zero-prop: <Box role="status" aria-label={LOADING_LABEL}> with a
// text skeleton (title, width 40%, height 40) then Grid 7/5: left = Skeleton rectangular 40, 320, 40
// stacked; right = Skeleton rectangular 400.
```

**Screen render (exact structure):**

```tsx
const editor = useContentEditor({ contentId });
const isNarrow = useBreakpointDown('md');

if (editor.mode === 'edit' && editor.isLoading) return <EditorSkeleton />;
if (editor.mode === 'edit' && editor.isError && !editor.hasContent) return <ErrorState message={EDITOR_LOAD_ERROR} />;

const showForm = !isNarrow || !editor.previewOpen;
const showPreview = !isNarrow || editor.previewOpen;
const headerTitle = editor.mode === 'edit' ? (editor.savedTitle ?? '') : NEW_CONTENT_LABEL;

return (
  <Box>
    <PageHeader
      title={headerTitle}
      meta={editor.mode === 'edit' && editor.status && editor.createdAt && editor.updatedAt && editor.slug ? (
        <EditorMeta slug={editor.slug} status={editor.status} createdAt={editor.createdAt} updatedAt={editor.updatedAt} publishedAt={editor.publishedAt} />
      ) : undefined}
      actions={isNarrow ? (
        <Button variant="outlined" onClick={editor.togglePreview}>{editor.previewOpen ? EDIT_LABEL : PREVIEW_LABEL}</Button>
      ) : undefined}
    />
    <Grid container spacing={3}>
      {showForm ? <Grid size={{ xs: 12, md: 7 }}><EditorForm editor={editor} onDelete={editor.openDeleteDialog} /></Grid> : null}
      {showPreview ? <Grid size={{ xs: 12, md: 5 }}><EditorPreview title={editor.title} body={editor.body} /></Grid> : null}
    </Grid>
    <ConfirmDialog
      open={editor.deleteDialogOpen}
      title="Delete content"
      body={`“${editor.savedTitle ?? editor.title}” will be permanently deleted — there is no restore.`}
      confirmLabel={DELETE_LABEL}
      onConfirm={editor.confirmDelete}
      onClose={editor.closeDeleteDialog}
      isPending={editor.isDeleting}
      errorMessage={editor.deleteError ?? undefined}
      destructive
    />
  </Box>
);
```

(The dialog names the SAVED title, not a half-edited field; the "permanent/no restore" copy is
pinned by an existing test.)

## Steps (TDD)

- [ ] **RED — test-author.**

**Copy `apps/client/src/lib/markdown.test.ts` → `apps/admin/src/lib/markdown.test.ts`
verbatim** (it fails to resolve `./markdown` until GREEN).

**`Component.test.tsx` — rewrite the pin** `activating Preview shows the body markdown text
inside a labeled preview region` as:

```tsx
  it('desktop: the live preview renders beside the form, with no Preview toggle, and mirrors the body', async () => {
    mockFetch();

    renderEdit(draftFixture.id);

    await screen.findByRole('textbox', { name: /title/i });
    const previewRegion = screen.getByRole('region', { name: 'Preview' });
    expect(previewRegion).toHaveTextContent('Body.');
    expect(screen.queryByRole('button', { name: /^preview$/i })).not.toBeInTheDocument();
  });
```

**Fixture change in the same file:** `draftFixture.body_md` becomes
`'# Roth IRA Conversion Basics\n\nBody.'` (today it is the bare heading, which the preview now
strips to nothing). The "EDIT mode: prefilled" pin reads the fixture, so it stays green. Add
`tagsResponse?: Response` to `MockFetchOptions` and return it from the `/api/v1/tags` branch
(default `jsonResponse([])`).

**Append to `Component.test.tsx`** (`formatDate` from `@/lib/format`, `within` imported):

```tsx
  it('edit mode: the header shows the saved title as h1 with status chip, slug and dates', async () => {
    mockFetch();

    renderEdit(draftFixture.id);

    expect(await screen.findByRole('heading', { level: 1, name: draftFixture.title })).toBeInTheDocument();
    const header = screen.getByRole('banner');
    expect(within(header).getByText('Draft')).toBeInTheDocument();
    expect(within(header).getByText(draftFixture.slug)).toBeInTheDocument();
    expect(within(header).getByText(`Created ${formatDate(draftFixture.created_at)}`)).toBeInTheDocument();
    expect(within(header).getByText(`Updated ${formatDate(draftFixture.updated_at)}`)).toBeInTheDocument();
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

    expect(await screen.findByRole('heading', { level: 1, name: 'New content' })).toBeInTheDocument();
    const publish = screen.getByRole('button', { name: /publish/i });
    expect(publish).toBeDisabled();
    await user.hover(publish.parentElement!);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Save first');
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
    expect(within(region).queryByRole('heading', { name: 'Roth IRA Conversion Basics' })).not.toBeInTheDocument();
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
    expect(within(dialog).getByRole('button', { name: /delete/i })).toHaveClass('MuiButton-colorError');
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
    expect(fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'POST')).toBe(false);
  });

  it('pressing Enter in the Title field submits the form', async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    const title = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(title);
    await user.type(title, 'Renamed{Enter}');

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'PATCH')).toBe(true),
    );
  });

  it('the Body field is monospace and Tags suggest existing tag names', async () => {
    mockFetch({ tagsResponse: jsonResponse([{ id: 't1', name: 'retirement', count: 2 }]) });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);

    expect(await screen.findByRole('textbox', { name: /body/i })).toHaveStyle({ fontFamily: 'monospace' });
    await user.click(screen.getByRole('combobox', { name: /tags/i }));
    expect(await screen.findByRole('option', { name: 'retirement' })).toBeInTheDocument();
  });

  it('edit mode: shows an editor-shaped skeleton (labelled Loading, no spinner) while loading', () => {
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderEdit(draftFixture.id);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });
```

(`requestMethod`, `jsonResponse`, `renderNew`, `renderEdit`, `publishedFixture` all exist in
the file already.)

**`responsivePreview.test.tsx`** (new one-behaviour file — copy the `draftFixture` (with the
new body), `mockFetch`, `renderEdit` helpers and the `vi.mock('next/navigation', …)` block
from `Component.test.tsx`; import `stubMatchMedia` from `@/testing/matchMedia`)

```tsx
describe('ContentEditorScreen below the md breakpoint', () => {
  let restore: (() => void) | null = null;

  beforeEach(() => {
    restore = stubMatchMedia(true);
  });

  afterEach(() => {
    restore?.();
    restore = null;
    vi.restoreAllMocks();
  });

  it('a header Preview button swaps the form for the preview, and Edit swaps back', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    await screen.findByRole('textbox', { name: /title/i });
    expect(screen.queryByRole('region', { name: 'Preview' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Preview' }));
    expect(screen.getByRole('region', { name: 'Preview' })).toHaveTextContent('Body.');
    expect(screen.queryByRole('textbox', { name: /title/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('textbox', { name: /title/i })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Preview' })).not.toBeInTheDocument();
  });
});
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- ContentEditorScreen markdown` → `lib/markdown`
  unresolved; the rewritten preview pin and every appended case fail (no header h1, preview
  always behind a toggle today, gold delete, no validation copy, no tooltip, monospace/options
  absent, spinner instead of skeleton); `responsivePreview` fails; the other five files green.

- [ ] **GREEN — implementer:** copy `lib/markdown.ts` → copy strings → `EditorMeta` →
  `EditorPreview` → `EditorSkeleton` → `EditorForm` → screen. Keep `Component.tsx` under
  ~80 lines (the leaves carry the markup).

- [ ] **Run GREEN:** `pnpm -C apps/admin test`; `pnpm -C apps/admin type-check`.

- [ ] **Screenshots** (iframe technique, 1440 + 390, real screen, signed in, local API seed):
  `/content/<id>` of a published article (desktop two-column with the sticky preview; phone
  form, then phone preview after the toggle); `/content/new` desktop; the Publish tooltip on
  hover (desktop). Store as `t20-editor-*.jpg`.

- [ ] **Gates:** `pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/admin/src/components/content/ContentEditorScreen apps/admin/src/lib/markdown.ts apps/admin/src/lib/markdown.test.ts apps/admin/src/lib/copy.ts`
  `git commit -m "feat(admin): editor screen — header meta, split live preview, action row, destructive delete (p8 t20)"`

## Verify

```bash
pnpm -C apps/admin test -- ContentEditorScreen markdown
pnpm gates:admin
```

## Acceptance

- Header h1 = saved title / "New content"; meta line with chip, slug, dates; two columns at
  `md`+ with a sticky preview that matches the public article (no doubled title, `##` → h3);
  Preview/Edit toggle below `md`.
- Real form: Enter submits; required Title with error/helper text; monospace Body; Tags with
  suggestions; Publish tooltips; Archive only when published; red Delete → destructive confirm.
- Editor skeleton while loading; all eight pre-existing editor test files green.
