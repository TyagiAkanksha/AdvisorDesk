import type { ContentListDto, ContentStatus } from '@/types/api/content';

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
  }),
});

export const { useListContentQuery, useDeleteContentMutation } = contentApi;
