import { configureStore } from '@reduxjs/toolkit';

import { baseApi } from './api/baseApi';

// Server cache (baseApi) + UI state only — the admin session is never
// persisted client-side, it is rehydrated from `GET /auth/me` on every load
// (docs/FRONTEND-CONVENTIONS.md §6).
export const store = configureStore({
  reducer: {
    [baseApi.reducerPath]: baseApi.reducer,
  },
  middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(baseApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
