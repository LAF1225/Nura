/**
 * Server state for medications (PRD 5, sections 43, 55, 62 and 65).
 *
 * Every query key carries the profile id, for the same reason the health
 * record's do: an account can hold more than one profile, and a cache keyed
 * only by "doses" would happily show one person's medication under another's
 * name (PRD 4, section 25).
 *
 * Three things here are worth reading rather than skimming:
 *
 * `useDoseAction` never rejects for a network failure -- it queues. "Saved on
 * this phone" is a success from the user's point of view, and the row says
 * which happened (PRD 5, section 62).
 *
 * `useSyncPendingDoseActions` drains that queue when the app regains focus or
 * the phone comes back online, which is also what makes a new phone work: the
 * schedules are on the server, so signing in and opening the screen is all
 * that is needed (section 43).
 *
 * `useMedicationReminders` mirrors whatever doses are on screen into the OS
 * scheduler. It runs after every change and every focus, and is idempotent,
 * which is how a schedule edit, a pause and an inactivated medication all
 * cancel the right reminders without a special case each (sections 42, 55).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useMemo } from 'react';

import { useOnReconnect } from '../../hooks/useNetworkStatus';
import { todayQueryKey } from '../../hooks/useToday';
import { useAppStore } from '../../store/appStore';
import { localDateString } from '../../utils/date';
import { useHealthProfileId } from '../health/hooks';
import {
  createSchedule,
  deleteSchedule,
  fetchAdherence,
  fetchDoses,
  fetchSchedules,
  fetchSupply,
  fetchTodayDoses,
  recordRefill,
  setSchedulePaused,
  updateSchedule,
  updateSupply,
  type SupplyPatch,
} from './api';
import { rebuildReminders } from './notifications';
import {
  loadPendingActions,
  submitOrQueueAction,
  syncPendingActions,
  withPendingActions,
} from './pendingActions';
import type {
  Adherence,
  DoseActionInput,
  MedicationDose,
  MedicationSchedule,
  MedicationSupply,
  PendingDoseAction,
  SchedulePayload,
} from './types';

/**
 * Whose medications these are.
 *
 * The same person the health record belongs to -- a medication schedule is a
 * reminder about a PRD 4 medication record, so it cannot be about anybody
 * else (PRD 5, section 4).
 */
export const useMedicationProfileId = useHealthProfileId;

export const schedulesQueryKey = (profileId: string) =>
  ['medication-schedules', profileId] as const;
export const todayDosesQueryKey = (profileId: string, localDate: string) =>
  ['medication-doses', profileId, localDate] as const;
export const historyQueryKey = (profileId: string, days: number, medicationId?: string) =>
  ['medication-history', profileId, days, medicationId ?? 'all'] as const;
export const adherenceQueryKey = (profileId: string, days: number) =>
  ['medication-adherence', profileId, days] as const;
export const supplyQueryKey = (profileId: string) =>
  ['medication-supply', profileId] as const;
export const pendingActionsQueryKey = ['medication-doses', 'pending'] as const;

/** The history window the screens open on (PRD 5, section 26). */
export const HISTORY_RANGES = [7, 30] as const;
export const DEFAULT_HISTORY_DAYS = 7;

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - (days - 1));
  return localDateString(date);
}

// --- reading ----------------------------------------------------------------

export function useMedicationSchedules(medicationId?: string) {
  const profileId = useMedicationProfileId();
  const enabled = useEnabled(profileId);

  const query = useQuery<MedicationSchedule[]>({
    queryKey: schedulesQueryKey(profileId ?? ''),
    queryFn: ({ signal }) => fetchSchedules(profileId ?? '', signal),
    enabled,
  });

  // Filtered here rather than on the server so the schedule list and one
  // medication's schedules share a cache entry instead of racing each other.
  const data = useMemo(
    () =>
      medicationId === undefined
        ? query.data
        : query.data?.filter((schedule) => schedule.medicationId === medicationId),
    [query.data, medicationId]
  );

  return { ...query, data, profileId };
}

/** The doses on the user's own local day, with anything queued applied. */
export function useTodayDoses(localDate = localDateString()) {
  const profileId = useMedicationProfileId();
  const enabled = useEnabled(profileId);
  const pending = usePendingDoseActions();

  const query = useQuery<MedicationDose[]>({
    queryKey: todayDosesQueryKey(profileId ?? '', localDate),
    queryFn: ({ signal }) => fetchTodayDoses(profileId ?? '', localDate, signal),
    enabled,
  });

  const data = useMemo(
    () => withPendingActions(query.data ?? [], pending.data ?? []),
    [query.data, pending.data]
  );

  return { ...query, data, profileId };
}

export function useDoseHistory(days = DEFAULT_HISTORY_DAYS, medicationId?: string) {
  const profileId = useMedicationProfileId();
  const enabled = useEnabled(profileId);
  const pending = usePendingDoseActions();

  const query = useQuery<MedicationDose[]>({
    queryKey: historyQueryKey(profileId ?? '', days, medicationId),
    queryFn: ({ signal }) =>
      fetchDoses(
        profileId ?? '',
        { fromDate: daysAgo(days), toDate: localDateString(), medicationId },
        signal
      ),
    enabled,
  });

  const data = useMemo(
    () => withPendingActions(query.data ?? [], pending.data ?? []),
    [query.data, pending.data]
  );

  return { ...query, data, profileId };
}

export function useAdherence(days = DEFAULT_HISTORY_DAYS) {
  const profileId = useMedicationProfileId();
  const enabled = useEnabled(profileId);

  return useQuery<Adherence>({
    queryKey: adherenceQueryKey(profileId ?? '', days),
    queryFn: ({ signal }) => fetchAdherence(profileId ?? '', days, signal),
    enabled,
  });
}

export function useMedicationSupply() {
  const profileId = useMedicationProfileId();
  const enabled = useEnabled(profileId);

  const query = useQuery<MedicationSupply[]>({
    queryKey: supplyQueryKey(profileId ?? ''),
    queryFn: ({ signal }) => fetchSupply(profileId ?? '', signal),
    enabled,
  });

  return { ...query, profileId };
}

/** Actions saved on this phone but not yet accepted by the backend. */
export function usePendingDoseActions() {
  return useQuery<PendingDoseAction[]>({
    queryKey: pendingActionsQueryKey,
    queryFn: () => loadPendingActions(),
    // Local storage; it only changes when this app changes it, and every such
    // change invalidates the key.
    staleTime: Infinity,
  });
}

// --- writing ----------------------------------------------------------------

/**
 * Everything a medication change can affect.
 *
 * Deliberately broad. A schedule edit moves future doses, which changes
 * Today, the history, the adherence figure and the reminders -- refreshing
 * only the obvious one is how a screen ends up disagreeing with itself.
 */
function useRefreshMedications(profileId: string | null) {
  const queryClient = useQueryClient();
  const localDate = localDateString();

  return useCallback(async () => {
    if (profileId === null) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: schedulesQueryKey(profileId) }),
      queryClient.invalidateQueries({
        queryKey: todayDosesQueryKey(profileId, localDate),
      }),
      queryClient.invalidateQueries({ queryKey: ['medication-history', profileId] }),
      queryClient.invalidateQueries({ queryKey: ['medication-adherence', profileId] }),
      queryClient.invalidateQueries({ queryKey: supplyQueryKey(profileId) }),
      queryClient.invalidateQueries({ queryKey: pendingActionsQueryKey }),
      queryClient.invalidateQueries({ queryKey: todayQueryKey(localDate) }),
    ]);
  }, [profileId, localDate, queryClient]);
}

export function useSaveSchedule() {
  const profileId = useMedicationProfileId();
  const refresh = useRefreshMedications(profileId);

  return useMutation({
    mutationFn: ({
      scheduleId,
      payload,
    }: {
      /** Absent for a new schedule. */
      scheduleId?: string;
      payload: SchedulePayload;
    }) =>
      scheduleId
        ? updateSchedule(profileId ?? '', scheduleId, payload)
        : createSchedule(profileId ?? '', payload),
    onSuccess: refresh,
  });
}

export function useSetSchedulePaused() {
  const profileId = useMedicationProfileId();
  const refresh = useRefreshMedications(profileId);

  return useMutation({
    mutationFn: ({ scheduleId, paused }: { scheduleId: string; paused: boolean }) =>
      setSchedulePaused(profileId ?? '', scheduleId, paused),
    onSuccess: refresh,
  });
}

export function useDeleteSchedule() {
  const profileId = useMedicationProfileId();
  const refresh = useRefreshMedications(profileId);

  return useMutation({
    mutationFn: (scheduleId: string) => deleteSchedule(profileId ?? '', scheduleId),
    onSuccess: refresh,
  });
}

/**
 * Taken, Snooze or Skip.
 *
 * Resolves whether the action reached the backend or was queued; it rejects
 * only when the server refuses the action itself, which is a rule the user
 * needs to hear about rather than a failure to retry.
 */
export function useDoseAction() {
  const profileId = useMedicationProfileId();
  const refresh = useRefreshMedications(profileId);

  return useMutation({
    mutationFn: ({ doseId, input }: { doseId: string; input: DoseActionInput }) =>
      submitOrQueueAction(profileId ?? '', doseId, input),
    onSuccess: refresh,
  });
}

export function useUpdateSupply() {
  const profileId = useMedicationProfileId();
  const refresh = useRefreshMedications(profileId);

  return useMutation({
    mutationFn: ({ medicationId, patch }: { medicationId: string; patch: SupplyPatch }) =>
      updateSupply(profileId ?? '', medicationId, patch),
    onSuccess: refresh,
  });
}

export function useRecordRefill() {
  const profileId = useMedicationProfileId();
  const refresh = useRefreshMedications(profileId);

  return useMutation({
    mutationFn: ({
      medicationId,
      remainingDoses,
    }: {
      medicationId: string;
      remainingDoses: number;
    }) => recordRefill(profileId ?? '', medicationId, remainingDoses, localDateString()),
    onSuccess: refresh,
  });
}

// --- background work --------------------------------------------------------

/**
 * Sends anything queued: when a medication screen is focused, and again
 * whenever the phone comes back online (PRD 5, sections 62 and 63).
 */
export function useSyncPendingDoseActions() {
  const profileId = useMedicationProfileId();
  const refresh = useRefreshMedications(profileId);
  const authStatus = useAppStore((state) => state.authStatus);

  const sync = useCallback(async () => {
    if (authStatus !== 'authenticated' || profileId === null) return;
    const summary = await syncPendingActions(profileId);
    if (summary.sent > 0 || summary.discarded > 0) {
      await refresh();
    }
  }, [authStatus, profileId, refresh]);

  useOnReconnect(() => void sync());

  useFocusEffect(
    useCallback(() => {
      void sync();
    }, [sync])
  );

  return sync;
}

/**
 * Rebuilds reminders from Today, for somebody who has schedules.
 *
 * This is what PRD 5 sections 43 and 55 ask for -- a new phone, a reinstall,
 * or simply an app that has been closed for a week ends up with the right
 * notifications without the user going anywhere. It shares the cache entry
 * `useTodayDoses` uses, so opening the medication screen afterwards costs
 * nothing extra, and it fetches nothing at all for the many people who have
 * not set a reminder up.
 */
export function useMedicationReminderRefresh(hasSchedules: boolean): void {
  const profileId = useMedicationProfileId();
  const enabled = useEnabled(profileId) && hasSchedules;
  const localDate = localDateString();

  const query = useQuery<MedicationDose[]>({
    queryKey: todayDosesQueryKey(profileId ?? '', localDate),
    queryFn: ({ signal }) => fetchTodayDoses(profileId ?? '', localDate, signal),
    enabled,
  });

  useMedicationReminders(query.data ?? []);
}

/**
 * Keeps the phone's pending reminders in step with these doses.
 *
 * Signature-keyed rather than run on every render: rebuilding is idempotent,
 * but a rebuild per render would still cancel and recreate notifications for
 * no reason. The signature changes exactly when a reminder would have to.
 */
export function useMedicationReminders(doses: MedicationDose[]): void {
  const signature = doses
    .filter((dose) => dose.status === 'scheduled' || dose.status === 'snoozed')
    .map((dose) => `${dose.id}:${dose.snoozedUntil ?? dose.scheduledFor}`)
    .join('|');

  useEffect(() => {
    // Empty is meaningful: a paused schedule or an inactivated medication
    // leaves no doses, and the reminders for them have to come down.
    void rebuildReminders(doses);
    // `doses` is intentionally not a dependency: it is a new array on every
    // render, while the signature changes only when a reminder must.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);
}
