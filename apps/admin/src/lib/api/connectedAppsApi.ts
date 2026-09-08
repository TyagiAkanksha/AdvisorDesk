import type { ConnectedAppsResponseDto } from '@/types/api/connectedApps';

import { baseApi } from './baseApi';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md: the "Connected apps" admin page's
// list + revoke endpoints, backed by task-08's admin-management API
// (`GET`/`DELETE /api/v1/oauth/clients[/{client_id}]`).
export const connectedAppsApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getConnectedApps: builder.query<ConnectedAppsResponseDto, void>({
      query: () => '/api/v1/oauth/clients',
      providesTags: ['ConnectedApps'],
    }),
    revokeConnectedApp: builder.mutation<void, string>({
      query: (clientId) => ({
        url: `/api/v1/oauth/clients/${encodeURIComponent(clientId)}`,
        method: 'DELETE',
      }),
      // Function form (not a bare array) — a bare array invalidates on both success AND
      // failure, and a failed DELETE revoked nothing server-side (same idiom as
      // contentApi's `deleteContent`).
      invalidatesTags: (_result, error) => (error ? [] : ['ConnectedApps']),
    }),
  }),
});

export const { useGetConnectedAppsQuery, useRevokeConnectedAppMutation } = connectedAppsApi;
