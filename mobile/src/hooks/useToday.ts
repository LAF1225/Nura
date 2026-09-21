/**
 * Server state for Today (PRD 3, sections 31, 32, 55 and 56).
 *
 * One request fills the screen (`/api/v1/today`), and it is refreshed when the
 * screen is focused or pulled down -- never on a timer. A dashboard that polls
 * every few seconds costs battery to tell the user something that changes
 * every few minutes at most (PRD 3, section 56).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback } from 'react';

import {
  fetchDashboardPreferences,
  fetchTodaySummaryWithBody,
  saveDashboardPreferences,
} from '../services/api/today';
import { loadTodaySnapshot, saveTodaySnapshot } from '../services/today/cache';
import {
  loadPendingCheckIn,
  submitOrQueue,
  syncPendingCheckIn,
  type PendingCheckIn,
  type SubmitOutcome,
} from '../services/checkins/pendingCheckIn';
import { useAppStore } from '../store/appStore';
import type {
  DashboardCardKey,
  DashboardPreferences,
  TodaySummary,
  WellbeingLevel,
} from '../types/today';
import { localDateString } from '../utils/date';
import { useOnReconnect } from './useNetworkStatus';

export const todayQueryKey = (localDate: string) => ['today', localDate] as const;
export const todaySnapshotQueryKey = ['today', 'snapshot'] as const;
export const pendingCheckInQueryKey = ['daily-checkin', 'pending'] as const;
export const dashboardPreferencesQueryKey = ['dashboard-preferences'] as const;

/**
 * How long a Today summary stays fresh. Well inside the 90-second window the
 * backend uses to call a robot online, so a focused screen is never showing a
 * status that has already lapsed.
 */
const STALE_MS = 30_000;

export function useToday() {
  const authStatus = useAppStore((state) => state.authStatus);
  // Stable for the whole day, so the cache key changes exactly when the user's
  // day does -- including for someone using the app across midnight.
  const localDate = localDateString();

  const query = useQuery<TodaySummary>({
    queryKey: todayQueryKey(localDate),
    queryFn: async ({ signal }) => {
      const { summary, raw } = await fetchTodaySummaryWithBody(localDate, signal);
      // Kept so a later launch with no signal can still show the user their
      // day rather than an error (PRD 3, section 26).
      void saveTodaySnapshot(raw);
      return summary;
    },
    enabled: authStatus === 'authenticated',
    staleTime: STALE_MS,
  });

  return { ...query, localDate };
}

/**
 * The last Today the backend gave us, for when it cannot be reached.
 *
 * Only useful for the day it was fetched on -- the screen checks that before
 * showing it, because yesterday’s check-in presented as today’s would be a
 * lie.
 */
export function useTodaySnapshot() {
  return useQuery<TodaySummary | null>({
    queryKey: todaySnapshotQueryKey,
    queryFn: () => loadTodaySnapshot(),
    staleTime: Infinity,
  });
}

/**
 * Refetches when the screen regains focus, but only if the data has gone
 * stale. Coming back from a two-second detour should not fire a request.
 */
export function useRefreshOnFocus(refetch: () => void, dataUpdatedAt: number) {
  useFocusEffect(
    useCallback(() => {
      if (dataUpdatedAt === 0 || Date.now() - dataUpdatedAt > STALE_MS) {
        refetch();
      }
    }, [refetch, dataUpdatedAt])
  );
}

/** The check-in saved on this phone but not yet accepted by the backend. */
export function usePendingCheckIn() {
  return useQuery<PendingCheckIn | null>({
    queryKey: pendingCheckInQueryKey,
    queryFn: () => loadPendingCheckIn(),
    // Local storage; it only changes when this app changes it, and every such
    // change invalidates the key.
    staleTime: Infinity,
  });
}

export interface CheckInInput {
  wellbeingLevel: WellbeingLevel;
  note?: string | null;
}

/**
 * Submits today's check-in, falling back to the on-device queue.
 *
 * The mutation resolves either way: "saved on this phone" is a success from
 * the user's point of view, and the card says which happened. It only rejects
 * when the server refuses the answer itself.
 */
export function useSubmitCheckIn() {
  const queryClient = useQueryClient();
  const localDate = localDateString();

  return useMutation<SubmitOutcome, unknown, CheckInInput>({
    mutationFn: (input) =>
      submitOrQueue({
        localDate,
        wellbeingLevel: input.wellbeingLevel,
        note: input.note ?? null,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: todayQueryKey(localDate) }),
        queryClient.invalidateQueries({ queryKey: pendingCheckInQueryKey }),
      ]);
    },
  });
}

/**
 * Sends anything queued: once when Today mounts, and again whenever the phone
 * comes back online (PRD 3, section 27).
 */
export function useSyncPendingCheckIn() {
  const queryClient = useQueryClient();
  const authStatus = useAppStore((state) => state.authStatus);
  const localDate = localDateString();

  const sync = useCallback(async () => {
    if (authStatus !== 'authenticated') return;
    const result = await syncPendingCheckIn();
    if (result.status === 'idle' || result.status === 'pending') return;
    // Synced or discarded: both change what the screen should show.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: todayQueryKey(localDate) }),
      queryClient.invalidateQueries({ queryKey: pendingCheckInQueryKey }),
    ]);
  }, [authStatus, localDate, queryClient]);

  useOnReconnect(() => void sync());

  useFocusEffect(
    useCallback(() => {
      void sync();
    }, [sync])
  );

  return sync;
}

export function useDashboardPreferences() {
  const authStatus = useAppStore((state) => state.authStatus);
  return useQuery<DashboardPreferences>({
    queryKey: dashboardPreferencesQueryKey,
    queryFn: ({ signal }) => fetchDashboardPreferences(signal),
    enabled: authStatus === 'authenticated',
  });
}

export function useSaveDashboardPreferences() {
  const queryClient = useQueryClient();
  const localDate = localDateString();

  return useMutation({
    mutationFn: (cards: { key: DashboardCardKey; visible: boolean }[]) =>
      saveDashboardPreferences(cards),
    onSuccess: async (preferences) => {
      // Write the server's answer straight into the cache so the customization
      // screen does not flicker back to the old order while a refetch lands.
      queryClient.setQueryData(dashboardPreferencesQueryKey, preferences);
      await queryClient.invalidateQueries({ queryKey: todayQueryKey(localDate) });
    },
  });
}
