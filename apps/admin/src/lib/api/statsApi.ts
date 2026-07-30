import type { StatsDto } from '@/types/api/stats';

import { baseApi } from './baseApi';

// task-05 / PRD §5.2: content counts by status/tag backing the dashboard cards.
export const statsApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getStats: builder.query<StatsDto, void>({
      query: () => '/api/v1/stats',
      providesTags: ['Stats'],
    }),
  }),
});

export const { useGetStatsQuery } = statsApi;
