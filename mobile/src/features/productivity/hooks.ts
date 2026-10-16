/**
 * Server state for tasks, reminders, alarms and routines (PRD 12).
 *
 * Four things worth reading rather than skimming.
 *
 * **Nothing polls.** None of this has a deadline on the server: a task is due
 * at a time the phone already knows, a reminder's notification is held by the
 * operating system, and a routine run is open all day. Queries refresh when a
 * screen is focused or pulled down, which is PRD 3 section 56's rule and costs
 * nothing to keep.
 *
 * **Every key carries the profile.** A caregiver may support two people, and a
 * cache keyed only by `tasks` would show one person's list under the other's
 * name -- the mistake PRD 10's hooks call out by name.
 *
 * **Mutations replace the cache from the response.** The server's answer is
 * authoritative because it carries the derived parts a client cannot compute:
 * `overdue`, `dueLabel`, `progressLabel`, `nextFireAt`. Invalidating instead
 * would make a tick flicker back to its old position while a refetch ran.
 *
 * **The phone's notifications are rebuilt from server state, never from a
 * mutation's side effect.** `useDailyLifeNotifications` takes the rows a
 * screen is already showing and makes the operating system agree with them,
 * which is section 34's reconciliation. A mutation that scheduled its own
 * notification would be a second source of truth, and the first thing to
 * drift.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo } from 'react';

import { useOwnProfileId } from '../caregivers/hooks';
import { useAppStore } from '../../store/appStore';
import { deviceTimezone } from '../medications/schedule';
import {
  archiveRoutine,
  clearStep,
  createAlarm,
  createRoutine,
  deleteAlarm,
  deleteReminder,
  deleteRoutine,
  deleteTask,
  fetchAlarms,
  fetchCareRoutines,
  fetchDailyLifeSummary,
  fetchExternalCapabilities,
  fetchOccurrences,
  fetchReminders,
  fetchRoutine,
  fetchRoutines,
  fetchRun,
  fetchTasks,
  fetchTodayRuns,
  occurrenceAction,
  runAction,
  setReminderPaused,
  setRoutinePaused,
  snoozeOccurrence,
  updateAlarm,
  updateReminder,
  updateRoutine,
  updateTask,
} from './api';
import { hasPermission } from '../notifications/scheduler';
import { rebuildAlarmNotifications, rebuildReminderNotifications } from './notifications';
import {
  completeStepOrQueue,
  createReminderOrQueue,
  createTaskOrQueue,
  loadPendingTaskActions,
  submitTaskActionOrQueue,
  syncPendingDailyLife,
  withPendingTasks,
  type Outcome,
} from './pending';
import type {
  Alarm,
  AlarmInput,
  AlarmList,
  CaregiverRoutineList,
  DailyLifeSummary,
  ExternalCapabilities,
  PendingTaskAction,
  Reminder,
  ReminderInput,
  ReminderList,
  ReminderOccurrence,
  Routine,
  RoutineEdit,
  RoutineInput,
  RoutineList,
  RoutineRun,
  RoutineStepState,
  SnoozeMinutes,
  Task,
  TaskEdit,
  TaskInput,
  TaskList,
} from './types';
import { localDateString } from '../../utils/date';
import { useOnReconnect } from '../../hooks/useNetworkStatus';

export const tasksKey = (profileId: string, scope: string) =>
  ['tasks', profileId, scope] as const;
export const remindersKey = (profileId: string) => ['reminders', profileId] as const;
export const occurrencesKey = (profileId: string) =>
  ['reminder-occurrences', profileId] as const;
export const alarmsKey = (profileId: string) => ['alarms', profileId] as const;
export const routinesKey = (profileId: string) => ['routines', profileId] as const;
export const routineKey = (profileId: string, routineId: string) =>
  ['routine', profileId, routineId] as const;
export const todayRunsKey = (profileId: string) => ['routine-runs', profileId] as const;
export const runKey = (profileId: string, runId: string) =>
  ['routine-run', profileId, runId] as const;
export const dailyLifeSummaryKey = (profileId: string, localDate: string) =>
  ['daily-life', profileId, localDate] as const;
export const externalCapabilitiesKey = (profileId: string) =>
  ['external-capabilities', profileId] as const;
export const careRoutinesKey = (profileId: string) =>
  ['care-routines', profileId] as const;
export const pendingTaskActionsKey = ['productivity', 'pending-actions'] as const;
export const notificationPermissionKey = ['notifications', 'permission'] as const;

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

/** The profile every daily-life request is about. */
export function useDailyLifeProfileId(): string | null {
  return useOwnProfileId();
}

// --- tasks ------------------------------------------------------------------

export function useTasks(scope: 'open' | 'completed' | 'archived' = 'open') {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  const pending = usePendingTaskActions();

  const query = useQuery<TaskList>({
    queryKey: tasksKey(profileId ?? 'none', scope),
    queryFn: () => fetchTasks(profileId as string, scope),
    enabled,
  });

  // Overlaid so a queued Done shows at once rather than reverting on the next
  // refresh (section 37).
  const data = useMemo(() => {
    if (query.data === undefined) return query.data;
    const actions = pending.data ?? [];
    if (actions.length === 0) return query.data;
    return {
      ...query.data,
      tasks: withPendingTasks<Task>(query.data.tasks, actions),
    };
  }, [query.data, pending.data]);

  return { ...query, data };
}

export function usePendingTaskActions() {
  return useQuery<PendingTaskAction[]>({
    queryKey: pendingTaskActionsKey,
    queryFn: () => loadPendingTaskActions(),
  });
}

function useInvalidateDailyLife() {
  const client = useQueryClient();
  const profileId = useDailyLifeProfileId();
  return useCallback(() => {
    if (profileId === null) return;
    // Both the plural list keys and the singular detail keys: `['routines']`
    // does not match `['routine', id]`, and a detail screen that was not
    // invalidated is a screen that still shows yesterday's progress.
    for (const key of [
      ['tasks', profileId],
      ['reminders', profileId],
      ['reminder-occurrences', profileId],
      ['alarms', profileId],
      ['routines', profileId],
      ['routine', profileId],
      ['routine-runs', profileId],
      ['routine-run', profileId],
      ['daily-life', profileId],
    ]) {
      void client.invalidateQueries({ queryKey: key });
    }
    void client.invalidateQueries({ queryKey: pendingTaskActionsKey });
    // Today carries the counts, so it goes stale with them.
    void client.invalidateQueries({ queryKey: ['today'] });
  }, [client, profileId]);
}

export function useCreateTask() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<Outcome<{ task: Task; created: boolean }>, Error, TaskInput>({
    mutationFn: (input) =>
      createTaskOrQueue(profileId as string, {
        timezone: deviceTimezone(),
        ...input,
      }),
    onSuccess: invalidate,
  });
}

export function useUpdateTask() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    { task: Task; applied: boolean },
    Error,
    { taskId: string; edit: TaskEdit }
  >({
    mutationFn: ({ taskId, edit }) =>
      updateTask(profileId as string, taskId, {
        // Section 40: the edit says when it was made, so a stale one loses.
        clientUpdatedAt: new Date().toISOString(),
        ...edit,
      }),
    onSuccess: invalidate,
  });
}

export function useTaskAction() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    Outcome<{ task: Task; applied: boolean }>,
    Error,
    { taskId: string; action: PendingTaskAction['action'] }
  >({
    mutationFn: ({ taskId, action }) =>
      submitTaskActionOrQueue(profileId as string, taskId, action),
    onSuccess: invalidate,
  });
}

export function useDeleteTask() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<void, Error, string>({
    mutationFn: (taskId) => deleteTask(profileId as string, taskId),
    onSuccess: invalidate,
  });
}

// --- reminders --------------------------------------------------------------

export function useReminders() {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<ReminderList>({
    queryKey: remindersKey(profileId ?? 'none'),
    queryFn: () => fetchReminders(profileId as string),
    enabled,
  });
}

export function useReminderOccurrences(range?: { from?: string; to?: string }) {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<ReminderOccurrence[]>({
    queryKey: [...occurrencesKey(profileId ?? 'none'), range?.from, range?.to],
    queryFn: () => fetchOccurrences(profileId as string, range),
    enabled,
  });
}

export function useCreateReminder() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    Outcome<{ reminder: Reminder; created: boolean }>,
    Error,
    ReminderInput
  >({
    mutationFn: (input) =>
      createReminderOrQueue(profileId as string, {
        timezone: deviceTimezone(),
        ...input,
      }),
    onSuccess: invalidate,
  });
}

export function useUpdateReminder() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    Reminder,
    Error,
    { reminderId: string; input: Partial<ReminderInput> }
  >({
    mutationFn: ({ reminderId, input }) =>
      updateReminder(profileId as string, reminderId, input),
    onSuccess: invalidate,
  });
}

export function useSetReminderPaused() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<Reminder, Error, { reminderId: string; paused: boolean }>({
    mutationFn: ({ reminderId, paused }) =>
      setReminderPaused(profileId as string, reminderId, paused),
    onSuccess: invalidate,
  });
}

export function useDeleteReminder() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<void, Error, string>({
    mutationFn: (reminderId) => deleteReminder(profileId as string, reminderId),
    onSuccess: invalidate,
  });
}

export function useOccurrenceAction() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    { occurrence: ReminderOccurrence; applied: boolean },
    Error,
    { occurrenceId: string; action: 'complete' | 'dismiss' }
  >({
    mutationFn: ({ occurrenceId, action }) =>
      occurrenceAction(
        profileId as string,
        occurrenceId,
        action,
        new Date().toISOString()
      ),
    onSuccess: invalidate,
  });
}

export function useSnoozeOccurrence() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    { occurrence: ReminderOccurrence; applied: boolean },
    Error,
    { occurrenceId: string; minutes: SnoozeMinutes }
  >({
    mutationFn: ({ occurrenceId, minutes }) =>
      snoozeOccurrence(profileId as string, occurrenceId, minutes),
    onSuccess: invalidate,
  });
}

// --- alarms -----------------------------------------------------------------

export function useAlarms() {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<AlarmList>({
    queryKey: alarmsKey(profileId ?? 'none'),
    queryFn: () => fetchAlarms(profileId as string),
    enabled,
  });
}

export function useCreateAlarm() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<{ alarm: Alarm; created: boolean }, Error, AlarmInput>({
    mutationFn: (input) =>
      createAlarm(profileId as string, { timezone: deviceTimezone(), ...input }),
    onSuccess: invalidate,
  });
}

export function useUpdateAlarm() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<Alarm, Error, { alarmId: string; input: Partial<AlarmInput> }>({
    mutationFn: ({ alarmId, input }) => updateAlarm(profileId as string, alarmId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteAlarm() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<void, Error, string>({
    mutationFn: (alarmId) => deleteAlarm(profileId as string, alarmId),
    onSuccess: invalidate,
  });
}

// --- routines ---------------------------------------------------------------

export function useRoutines() {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<RoutineList>({
    queryKey: routinesKey(profileId ?? 'none'),
    queryFn: () => fetchRoutines(profileId as string),
    enabled,
  });
}

export function useRoutine(routineId: string | null) {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId) && routineId !== null;
  return useQuery<Routine>({
    queryKey: routineKey(profileId ?? 'none', routineId ?? 'none'),
    queryFn: () => fetchRoutine(profileId as string, routineId as string),
    enabled,
  });
}

export function useTodayRuns() {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<RoutineRun[]>({
    queryKey: todayRunsKey(profileId ?? 'none'),
    queryFn: () => fetchTodayRuns(profileId as string),
    enabled,
  });
}

export function useRun(runId: string | null) {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId) && runId !== null;
  return useQuery<RoutineRun>({
    queryKey: runKey(profileId ?? 'none', runId ?? 'none'),
    queryFn: () => fetchRun(profileId as string, runId as string),
    enabled,
  });
}

export function useCreateRoutine() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<{ routine: Routine; created: boolean }, Error, RoutineInput>({
    mutationFn: (input) =>
      createRoutine(profileId as string, { timezone: deviceTimezone(), ...input }),
    onSuccess: invalidate,
  });
}

export function useUpdateRoutine() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<Routine, Error, { routineId: string; edit: RoutineEdit }>({
    mutationFn: ({ routineId, edit }) =>
      updateRoutine(profileId as string, routineId, edit),
    onSuccess: invalidate,
  });
}

export function useSetRoutinePaused() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<Routine, Error, { routineId: string; paused: boolean }>({
    mutationFn: ({ routineId, paused }) =>
      setRoutinePaused(profileId as string, routineId, paused),
    onSuccess: invalidate,
  });
}

export function useArchiveRoutine() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<Routine, Error, string>({
    mutationFn: (routineId) => archiveRoutine(profileId as string, routineId),
    onSuccess: invalidate,
  });
}

export function useDeleteRoutine() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<void, Error, string>({
    mutationFn: (routineId) => deleteRoutine(profileId as string, routineId),
    onSuccess: invalidate,
  });
}

export function useCompleteStep() {
  const profileId = useDailyLifeProfileId();
  const client = useQueryClient();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    Outcome<RoutineRun>,
    Error,
    { runId: string; stepId: string; state?: RoutineStepState }
  >({
    mutationFn: ({ runId, stepId, state }) =>
      completeStepOrQueue(profileId as string, runId, stepId, state),
    onSuccess: (outcome, variables) => {
      // The server's run replaces the cache rather than invalidating it, so a
      // ticked step does not flicker back while a refetch runs.
      if (outcome.result !== null && profileId !== null) {
        client.setQueryData(runKey(profileId, variables.runId), outcome.result);
      }
      invalidate();
    },
  });
}

export function useClearStep() {
  const profileId = useDailyLifeProfileId();
  const client = useQueryClient();
  const invalidate = useInvalidateDailyLife();
  return useMutation<RoutineRun, Error, { runId: string; stepId: string }>({
    mutationFn: ({ runId, stepId }) => clearStep(profileId as string, runId, stepId),
    onSuccess: (run, variables) => {
      if (profileId !== null) {
        client.setQueryData(runKey(profileId, variables.runId), run);
      }
      invalidate();
    },
  });
}

export function useRunAction() {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  return useMutation<
    { run: RoutineRun; applied: boolean },
    Error,
    { runId: string; action: 'complete' | 'skip' }
  >({
    mutationFn: ({ runId, action }) => runAction(profileId as string, runId, action),
    onSuccess: invalidate,
  });
}

// --- the summary, the capability map and the caregiver's view ----------------

export function useDailyLifeSummary() {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  const localDate = localDateString(new Date());
  return useQuery<DailyLifeSummary>({
    queryKey: dailyLifeSummaryKey(profileId ?? 'none', localDate),
    queryFn: () => fetchDailyLifeSummary(profileId as string, localDate),
    enabled,
  });
}

export function useExternalCapabilities() {
  const profileId = useDailyLifeProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<ExternalCapabilities>({
    queryKey: externalCapabilitiesKey(profileId ?? 'none'),
    queryFn: () => fetchExternalCapabilities(profileId as string),
    enabled,
  });
}

/** For Caregiver Mode: the routines this caregiver may see (section 16). */
export function useCareRoutines(profileId: string | null) {
  const enabled = useEnabled(profileId);
  return useQuery<CaregiverRoutineList>({
    queryKey: careRoutinesKey(profileId ?? 'none'),
    queryFn: () => fetchCareRoutines(profileId as string),
    enabled,
  });
}

// --- the phone's own notifications (section 34) ------------------------------

/**
 * Whether the operating system has agreed to show notifications.
 *
 * A query rather than component state, and that is not an implementation
 * detail: it is asynchronous state about something outside the app, which is
 * what the query cache is for. It also means a screen reading it re-renders
 * when the answer arrives -- a plain `useState` inside a hook does not, in
 * this stack, which would leave section 9's sentence invisible until something
 * else happened to redraw the screen.
 */
export function useNotificationPermission() {
  const authStatus = useAppStore((state) => state.authStatus);
  return useQuery<boolean>({
    queryKey: notificationPermissionKey,
    queryFn: () => hasPermission(),
    enabled: authStatus === 'authenticated',
    // Asking the operating system is cheap, and the answer changes outside
    // the app -- somebody may have gone to Settings and back.
    staleTime: 0,
  });
}

/**
 * Keeps the phone's pending notifications in step with the server's rows.
 *
 * Reconciliation, not notification: the screens that list reminders and alarms
 * call this with what they are already showing, and it makes the operating
 * system agree. A mutation that scheduled its own would be a second source of
 * truth and the first thing to drift.
 *
 * Returns nothing. Whether notifications are permitted is
 * `useNotificationPermission`, so a screen asks one question of one hook.
 */
export function useDailyLifeNotifications(
  occurrences: ReminderOccurrence[] | undefined,
  alarms: Alarm[] | undefined,
  enabledReminderIds?: ReadonlySet<string>
): void {
  const signature = useMemo(
    () =>
      JSON.stringify([
        (occurrences ?? []).map((row) => [row.id, row.status, row.snoozedUntil]),
        (alarms ?? []).map((row) => [row.id, row.enabled, row.nextFireAt]),
      ]),
    [occurrences, alarms]
  );

  useEffect(() => {
    void (async () => {
      if (occurrences === undefined && alarms === undefined) return;
      await rebuildReminderNotifications(occurrences ?? [], { enabledReminderIds });
      await rebuildAlarmNotifications(alarms ?? []);
    })();
    // `signature` collapses the rows into one comparable value, so this runs
    // when something that matters changed rather than on every render.
  }, [signature, enabledReminderIds, occurrences, alarms]);
}

/**
 * Sends anything queued while offline, when the phone reconnects.
 *
 * Mounted by the daily-life screens, which are where somebody lands after
 * being offline -- the same shape PRD 5's and PRD 7's sync hooks use.
 */
export function useSyncPendingDailyLife(): void {
  const profileId = useDailyLifeProfileId();
  const invalidate = useInvalidateDailyLife();
  const enabled = useEnabled(profileId);

  const sync = useCallback(() => {
    if (!enabled || profileId === null) return;
    void syncPendingDailyLife(profileId).then((summary) => {
      if (summary.sent > 0 || summary.discarded > 0) invalidate();
    });
  }, [enabled, profileId, invalidate]);

  useEffect(sync, [sync]);
  useOnReconnect(sync);
}
