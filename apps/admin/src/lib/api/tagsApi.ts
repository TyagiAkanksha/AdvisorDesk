import type { TagDto } from '@/types/api/tags';

import { baseApi } from './baseApi';

// task-05 / PRD §5.2: the non-deleted tag list (with usage counts) backing the content-list
// tag filter.
export const tagsApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    listTags: builder.query<TagDto[], void>({
      query: () => '/api/v1/tags',
      providesTags: ['Tags'],
    }),
  }),
});

export const { useListTagsQuery } = tagsApi;
