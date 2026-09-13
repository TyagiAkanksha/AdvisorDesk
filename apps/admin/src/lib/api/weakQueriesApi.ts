import type { WeakQueriesDto } from '@/types/api/weakQueries';

import { baseApi } from './baseApi';

// phase-9 task-19: the dashboard's weak-queries card backing query — `GET /api/v1/weak-queries`.
export interface WeakQueriesArgs {
  days: number;
  limit: number;
}

export const weakQueriesApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getWeakQueries: builder.query<WeakQueriesDto, WeakQueriesArgs>({
      query: ({ days, limit }) => `/api/v1/weak-queries?days=${days}&limit=${limit}`,
      providesTags: ['WeakQueries'],
    }),
  }),
});

export const { useGetWeakQueriesQuery } = weakQueriesApi;
