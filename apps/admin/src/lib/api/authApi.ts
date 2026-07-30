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
      // Final review, finding C-8: matches the error-guard function form every
      // contentApi mutation uses (lib/api/contentApi.ts) — a bare array
      // invalidates on both success AND failure, and a failed logout changed
      // nothing server-side (the session cookie is still live), so nothing
      // should be invalidated (and no unnecessary getMe/list refetch race
      // right after the failure).
      invalidatesTags: (_result, error) => (error ? [] : ['Content', 'Tags', 'Stats', 'Me']),
    }),
  }),
});

export const { useGetMeQuery, useLogoutMutation } = authApi;
