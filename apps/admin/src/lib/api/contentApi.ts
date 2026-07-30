import type {
  ContentCreateDto,
  ContentDto,
  ContentListDto,
  ContentStatus,
  ContentUpdateDto,
} from '@/types/api/content';

import { baseApi } from './baseApi';

// task-05 / PRD §5.2: the content list + delete endpoints the dashboard and content-list
// screens read from. Params are forwarded as-is to `fetchBaseQuery`'s `params` option, which
// strips `undefined` entries before building the querystring — a caller who omits a filter
// never sends it as an empty-string param (contentApi.test.ts).
export interface ListContentParams {
  status?: ContentStatus;
  tag?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

// task-06 / PRD §5.2: `.initiate()`/the generated hook always takes exactly one argument, so
// `updateContent(id, patch)`'s prose in the brief becomes this single-arg shape. `patch` is
// nested (not merged with `id`) so it stays an unmodified pass-through of the PATCH body —
// see contentApiEditor.test.ts's tri-state test (omitted keys never appear in the request).
export interface UpdateContentArgs {
  id: string;
  patch: ContentUpdateDto;
}

export const contentApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    listContent: builder.query<ContentListDto, ListContentParams>({
      query: (params) => ({ url: '/api/v1/content', params }),
      providesTags: ['Content'],
    }),
    deleteContent: builder.mutation<void, string>({
      query: (id) => ({ url: `/api/v1/content/${id}`, method: 'DELETE' }),
      // PRD §2.2/§12: deletion is permanent — invalidating Stats + Tags too keeps the
      // dashboard counts and tag-usage counts correct without a manual reload.
      invalidatesTags: ['Content', 'Stats', 'Tags'],
    }),
    // task-06 / PRD §5.2, §4: the editor's read/write endpoints. `getContent` shares the
    // plain `'Content'` tag with `listContent` (no id-scoped tags anywhere in this slice
    // yet) so any of the mutations below refreshes it too.
    getContent: builder.query<ContentDto, string>({
      query: (id) => `/api/v1/content/${id}`,
      providesTags: ['Content'],
    }),
    // `invalidatesTags` is the function form (not a bare array) on every mutation below —
    // RTK Query evaluates a static array on BOTH success and failure, so a bare array here
    // would refetch `getContent`/`listContent`/etc. even after a failed write. A failed
    // write changed nothing server-side, so nothing should be invalidated (also avoids an
    // unnecessary, error-prone extra fetch race right after the failure toast).
    createContent: builder.mutation<ContentDto, ContentCreateDto>({
      query: (body) => ({ url: '/api/v1/content', method: 'POST', body }),
      invalidatesTags: (_result, error) => (error ? [] : ['Content', 'Stats', 'Tags']),
    }),
    // Tri-state PATCH: `patch` is passed straight through as the request body — the caller
    // (useContentEditor's dirty tracking) decides which keys are present at all; this
    // endpoint never injects an `undefined` key of its own.
    updateContent: builder.mutation<ContentDto, UpdateContentArgs>({
      query: ({ id, patch }) => ({ url: `/api/v1/content/${id}`, method: 'PATCH', body: patch }),
      invalidatesTags: (_result, error) => (error ? [] : ['Content', 'Stats', 'Tags']),
    }),
    publishContent: builder.mutation<ContentDto, string>({
      query: (id) => ({ url: `/api/v1/content/${id}/publish`, method: 'POST' }),
      invalidatesTags: (_result, error) => (error ? [] : ['Content', 'Stats', 'Tags']),
    }),
    archiveContent: builder.mutation<ContentDto, string>({
      query: (id) => ({ url: `/api/v1/content/${id}/archive`, method: 'POST' }),
      invalidatesTags: (_result, error) => (error ? [] : ['Content', 'Stats', 'Tags']),
    }),
  }),
});

export const {
  useListContentQuery,
  useDeleteContentMutation,
  useGetContentQuery,
  useCreateContentMutation,
  useUpdateContentMutation,
  usePublishContentMutation,
  useArchiveContentMutation,
} = contentApi;
