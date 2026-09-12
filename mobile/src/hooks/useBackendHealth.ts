/**
 * Server state for the backend liveness check (PRD 0, section 14).
 *
 * TanStack Query owns the fetching, caching, retries and loading/error state.
 * The Today screen uses this to show its development-only connection
 * indicator, and it must degrade gracefully when the backend is down
 * (PRD 0, section 39).
 */
import { useQuery } from '@tanstack/react-query';

import { fetchHealth } from '../services/api';
import type { HealthResponse } from '../types/api';

export const backendHealthQueryKey = ['system', 'health'] as const;

export function useBackendHealth() {
  return useQuery<HealthResponse>({
    queryKey: backendHealthQueryKey,
    queryFn: ({ signal }) => fetchHealth(signal),
    // The backend being down is an expected state during development, not
    // something to hammer. One retry is enough to ride out a blip.
    retry: 1,
    staleTime: 30_000,
  });
}
