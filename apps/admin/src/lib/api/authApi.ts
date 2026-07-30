import type { MeDto } from '@/types/api/auth';

import { baseApi } from './baseApi';

// task-04 / PRD §5.1: session rehydration (`getMe`) + sign-out (`logout`).
// `getMe` provides the `Me` tag; `logout` invalidates every tag so the next
// screen a signed-in-again user visits refetches from a clean cache.
export const authApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getMe: builder.query<MeDto, void>({
      query: () => '/api/v1/auth/me',
      providesTags: ['Me'],
    }),
    logout: builder.mutation<void, void>({
      query: () => ({
        url: '/api/v1/auth/logout',
        method: 'POST',
      }),
      invalidatesTags: ['Content', 'Tags', 'Stats', 'Me'],
    }),
  }),
});

export const { useGetMeQuery, useLogoutMutation } = authApi;
