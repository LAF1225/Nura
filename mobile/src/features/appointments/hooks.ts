/**
 * Server state for appointments (PRD 7, sections 48-54).
 *
 * Every query key carries the profile id, for the same reason the health record,
 * medication and symptom keys do: an account can hold more than one profile, and
 * a cache keyed only by "appointments" would happily show one person's visit
 * under another's name.
 *
 * Four things here are worth reading rather than skimming.
 *
 * `useSaveAppointment` never rejects for a network failure -- it queues. "Saved on
 * this phone" is a success from the user's point of view, and the outcome says
 * which happened (PRD 7, section 53).
 *
 * `useAddQuestion` does the same for a question, which is the draft PRD 7
 * section 53 names explicitly.
 *
 * `useSyncPendingAppointments` drains both queues when an appointment screen is
 * focused or the phone comes back online. Every send carries the same client id,
 * so the queue can retry as often as it likes without creating a second record.
 *
 * `useAppointmentReminders` is the one place reminders are rebuilt. Every write
 * below invalidates the upcoming list, and this hook rebuilds from that list, so
 * a time change, a cancellation and a reminders-off switch all reschedule through
 * one path (PRD 7, section 54).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect } from 'react';

import { useOnReconnect } from '../../hooks/useNetworkStatus';
import { todayQueryKey } from '../../hooks/useToday';
import { useAppStore } from '../../store/appStore';
import { localDateString } from '../../utils/date';
import { useHealthProfileId, useHealthRecords } from '../health/hooks';
import { SECTIONS } from '../health/sections';
import {
  cancelAppointment,
  completeAppointment,
  deleteAppointment,
  deleteQuestion,
  deleteReport,
  fetchAppointment,
  fetchAppointments,
  fetchAppointmentSummary,
  fetchPreparation,
  fetchReport,
  fetchReports,
  generateReport,
  reopenAppointment,
  reorderQuestions,
  selectionPayload,
  updateAppointment,
  updateQuestion,
  type PeriodRequest,
} from './api';
import { appointmentPatch, appointmentPayload, newClientId } from './draft';
import { rebuildAppointmentReminders } from './notifications';
import {
  loadPendingAppointments,
  loadPendingQuestions,
  submitOrQueueAppointment,
  submitOrQueueQuestion,
  syncPending,
  type SaveOutcome,
} from './pending';
import { exportAndShareReport, type ExportOutcome } from './reportExport';
import type {
  Appointment,
  AppointmentDraft,
  AppointmentReport,
  AppointmentScope,
  AppointmentSummary,
  ClinicianBrief,
  PendingAppointment,
  PendingQuestion,
  Preparation,
  ReportPeriodPreset,
  ReportSelection,
} from './types';

/**
 * Whose appointments these are.
 *
 * The same person the health record belongs to. An appointment is a visit that
 * person is making, so it cannot be about anybody else (PRD 7, section 51).
 */
export const useAppointmentProfileId = useHealthProfileId;

export const appointmentsQueryKey = (profileId: string, scope = 'all') =>
  ['appointments', profileId, scope] as const;
export const appointmentQueryKey = (profileId: string, appointmentId: string) =>
  ['appointment', profileId, appointmentId] as const;
export const appointmentSummaryQueryKey = (profileId: string) =>
  ['appointment-summary', profileId] as const;
export const preparationQueryKey = (
  profileId: string,
  appointmentId: string,
  scope: string
) => ['appointment-preparation', profileId, appointmentId, scope] as const;
export const reportsQueryKey = (profileId: string, appointmentId: string) =>
  ['appointment-reports', profileId, appointmentId] as const;
export const reportQueryKey = (profileId: string, reportId: string) =>
  ['appointment-report', profileId, reportId] as const;
export const pendingAppointmentsQueryKey = ['appointments', 'pending'] as const;
export const pendingQuestionsQueryKey = ['appointment-questions', 'pending'] as const;

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

/** A stable cache key for one period choice. */
function periodScope(period: PeriodRequest): string {
  const preset = period.preset ?? 'since_last_visit';
  if (preset !== 'custom') return preset;
  return `custom:${period.periodStart ?? ''}:${period.periodEnd ?? ''}`;
}

// --- reading ----------------------------------------------------------------

export function useAppointments(scope?: AppointmentScope) {
  const profileId = useAppointmentProfileId();
  const enabled = useEnabled(profileId);

  const query = useQuery<Appointment[]>({
    queryKey: appointmentsQueryKey(profileId ?? '', scope ?? 'all'),
    queryFn: ({ signal }) => fetchAppointments(profileId ?? '', scope, signal),
    enabled,
  });

  return { ...query, profileId };
}

export function useUpcomingAppointments() {
  return useAppointments('upcoming');
}

export function useAppointment(appointmentId: string | undefined) {
  const profileId = useAppointmentProfileId();
  const enabled = useEnabled(profileId) && Boolean(appointmentId);

  const query = useQuery<Appointment>({
    queryKey: appointmentQueryKey(profileId ?? '', appointmentId ?? ''),
    queryFn: ({ signal }) =>
      fetchAppointment(profileId ?? '', appointmentId ?? '', signal),
    enabled,
  });

  return { ...query, profileId };
}

export function useAppointmentSummary() {
  const profileId = useAppointmentProfileId();
  const enabled = useEnabled(profileId);

  return useQuery<AppointmentSummary>({
    queryKey: appointmentSummaryQueryKey(profileId ?? ''),
    queryFn: ({ signal }) => fetchAppointmentSummary(profileId ?? '', signal),
    enabled,
  });
}

/**
 * The whole preparation review for one period (PRD 7, section 49).
 *
 * The period is part of the cache key, so moving from 30 days to 7 is a separate
 * entry rather than one that keeps being refetched -- and going back to 30 is
 * instant.
 */
export function usePreparation(
  appointmentId: string | undefined,
  period: PeriodRequest = {}
) {
  const profileId = useAppointmentProfileId();
  const enabled = useEnabled(profileId) && Boolean(appointmentId);

  const query = useQuery<Preparation>({
    queryKey: preparationQueryKey(
      profileId ?? '',
      appointmentId ?? '',
      periodScope(period)
    ),
    queryFn: ({ signal }) =>
      fetchPreparation(profileId ?? '', appointmentId ?? '', period, signal),
    enabled,
  });

  return { ...query, profileId };
}

export function useReports(appointmentId: string | undefined) {
  const profileId = useAppointmentProfileId();
  const enabled = useEnabled(profileId) && Boolean(appointmentId);

  const query = useQuery<AppointmentReport[]>({
    queryKey: reportsQueryKey(profileId ?? '', appointmentId ?? ''),
    queryFn: ({ signal }) => fetchReports(profileId ?? '', appointmentId ?? '', signal),
    enabled,
  });

  return { ...query, profileId };
}

/** One version, with its frozen content, for the preview (PRD 7, section 32). */
export function useReport(
  appointmentId: string | undefined,
  reportId: string | undefined
) {
  const profileId = useAppointmentProfileId();
  const enabled = useEnabled(profileId) && Boolean(appointmentId) && Boolean(reportId);

  const query = useQuery<AppointmentReport>({
    queryKey: reportQueryKey(profileId ?? '', reportId ?? ''),
    queryFn: ({ signal }) =>
      fetchReport(profileId ?? '', appointmentId ?? '', reportId ?? '', signal),
    enabled,
    // A snapshot is frozen, so there is nothing to refetch for.
    staleTime: Infinity,
  });

  return { ...query, profileId };
}

/** Appointments saved on this phone but not yet accepted by the backend. */
export function usePendingAppointments() {
  return useQuery<PendingAppointment[]>({
    queryKey: pendingAppointmentsQueryKey,
    queryFn: () => loadPendingAppointments(),
    // Local storage; it only changes when this app changes it, and every such
    // change invalidates the key.
    staleTime: Infinity,
  });
}

export function usePendingQuestions() {
  return useQuery<PendingQuestion[]>({
    queryKey: pendingQuestionsQueryKey,
    queryFn: () => loadPendingQuestions(),
    staleTime: Infinity,
  });
}

/**
 * The user's own clinicians, as the appointment form offers them (s6).
 *
 * Read from the PRD 4 health record rather than a directory: the clinician list
 * is theirs, typed by them, and linking an appointment to one is what lets the
 * report period mean "since I last saw this doctor" (PRD 7, section 14).
 */
export function useClinicianOptions() {
  const query = useHealthRecords(SECTIONS.clinicians);
  const options: ClinicianBrief[] = (query.data ?? []).map((record) => ({
    id: record.id,
    name: typeof record.name === 'string' ? record.name : 'Clinician',
    specialty: typeof record.specialty === 'string' ? record.specialty : null,
  }));
  return { ...query, options };
}

// --- writing ----------------------------------------------------------------

/**
 * Everything an appointment change can affect.
 *
 * Deliberately broad. Saving an appointment changes the list, the summary, the
 * Today response and -- once questions or a report exist -- the preparation
 * review. Refreshing only the obvious one is how a screen ends up disagreeing
 * with itself.
 */
function useRefreshAppointments(profileId: string | null) {
  const queryClient = useQueryClient();

  return useCallback(async () => {
    if (profileId === null) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['appointments', profileId] }),
      queryClient.invalidateQueries({ queryKey: ['appointment', profileId] }),
      queryClient.invalidateQueries({ queryKey: ['appointment-preparation', profileId] }),
      queryClient.invalidateQueries({ queryKey: ['appointment-reports', profileId] }),
      queryClient.invalidateQueries({ queryKey: appointmentSummaryQueryKey(profileId) }),
      queryClient.invalidateQueries({ queryKey: pendingAppointmentsQueryKey }),
      queryClient.invalidateQueries({ queryKey: pendingQuestionsQueryKey }),
      queryClient.invalidateQueries({ queryKey: todayQueryKey(localDateString()) }),
    ]);
  }, [profileId, queryClient]);
}

/** Turns a draft into the record the queue and the API both work from. */
export function pendingRecordFor(
  draft: AppointmentDraft,
  options: { savedAt?: Date } = {}
): PendingAppointment {
  return {
    clientAppointmentId: draft.clientAppointmentId,
    payload: appointmentPayload(draft),
    savedAt: (options.savedAt ?? new Date()).toISOString(),
    displayTitle: draft.title.trim() || 'Appointment',
  };
}

/**
 * Saves a new appointment, queueing it if the phone cannot reach the backend.
 *
 * Resolves whether the save reached the server or was queued; it rejects only
 * when the server refuses the appointment itself, which is something the user
 * needs to hear about rather than a failure to retry (PRD 7, section 53).
 */
export function useSaveAppointment() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation<SaveOutcome<Appointment>, unknown, { draft: AppointmentDraft }>({
    mutationFn: ({ draft }) =>
      submitOrQueueAppointment(profileId ?? '', pendingRecordFor(draft)),
    onSuccess: refresh,
  });
}

export function useUpdateAppointment() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: ({
      appointmentId,
      draft,
    }: {
      appointmentId: string;
      draft: AppointmentDraft;
    }) => updateAppointment(profileId ?? '', appointmentId, appointmentPatch(draft)),
    onSuccess: refresh,
  });
}

/** The reminder switch on its own, so the form is not needed to change it (s36). */
export function useSetReminders() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: ({
      appointmentId,
      enabled,
    }: {
      appointmentId: string;
      enabled: boolean;
    }) =>
      updateAppointment(profileId ?? '', appointmentId, { reminders_enabled: enabled }),
    onSuccess: refresh,
  });
}

export function useCancelAppointment() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: (appointmentId: string) =>
      cancelAppointment(profileId ?? '', appointmentId),
    onSuccess: refresh,
  });
}

export function useCompleteAppointment() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: ({
      appointmentId,
      visitNotes,
      followUpDate,
    }: {
      appointmentId: string;
      visitNotes?: string | null;
      followUpDate?: string | null;
    }) =>
      completeAppointment(profileId ?? '', appointmentId, {
        visit_notes: visitNotes,
        follow_up_date: followUpDate,
      }),
    onSuccess: refresh,
  });
}

export function useReopenAppointment() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: (appointmentId: string) =>
      reopenAppointment(profileId ?? '', appointmentId),
    onSuccess: refresh,
  });
}

export function useDeleteAppointment() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: (appointmentId: string) =>
      deleteAppointment(profileId ?? '', appointmentId),
    onSuccess: refresh,
  });
}

// --- questions --------------------------------------------------------------

/**
 * Adds a question, keeping it on the phone if that is not possible.
 *
 * The offline draft PRD 7 section 53 names. The client id is generated here so a
 * retry cannot add the question twice.
 */
export function useAddQuestion(appointmentId: string) {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: ({ text }: { text: string }) =>
      submitOrQueueQuestion(profileId ?? '', {
        clientQuestionId: newClientId('question'),
        appointmentId,
        text: text.trim(),
        savedAt: new Date().toISOString(),
      }),
    onSuccess: refresh,
  });
}

export function useUpdateQuestion(appointmentId: string) {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: ({
      questionId,
      patch,
    }: {
      questionId: string;
      patch: { text?: string; is_answered?: boolean; answer_note?: string | null };
    }) => updateQuestion(profileId ?? '', appointmentId, questionId, patch),
    onSuccess: refresh,
  });
}

export function useDeleteQuestion(appointmentId: string) {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: (questionId: string) =>
      deleteQuestion(profileId ?? '', appointmentId, questionId),
    onSuccess: refresh,
  });
}

export function useReorderQuestions(appointmentId: string) {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation({
    mutationFn: (questionIds: string[]) =>
      reorderQuestions(profileId ?? '', appointmentId, questionIds),
    onSuccess: refresh,
  });
}

// --- reports ----------------------------------------------------------------

/**
 * Generates one report version (PRD 7, sections 29-31).
 *
 * Never queued. A PDF is built by the backend, so there is nothing useful to keep
 * on the phone, and PRD 7 section 53 says plainly not to pretend generation
 * succeeded while offline -- so this rejects and the screen says so. The
 * selections are in a persisted store, so nothing the user chose is lost.
 */
export function useGenerateReport(appointmentId: string) {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);

  return useMutation<
    AppointmentReport,
    unknown,
    {
      selection: ReportSelection;
      preset: ReportPeriodPreset;
      periodStart?: string | null;
      periodEnd?: string | null;
    }
  >({
    mutationFn: ({ selection, preset, periodStart, periodEnd }) =>
      generateReport(profileId ?? '', appointmentId, {
        period_preset: preset,
        period_start: periodStart ?? null,
        period_end: periodEnd ?? null,
        selection: selectionPayload(selection),
        // A fresh id per press, so a double tap makes one version -- but
        // pressing Regenerate deliberately makes a new one (section 31).
        client_report_id: newClientId('report'),
      }),
    onSuccess: refresh,
  });
}

export function useDeleteReport(appointmentId: string) {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reportId: string) =>
      deleteReport(profileId ?? '', appointmentId, reportId),
    onSuccess: async (_result, reportId) => {
      queryClient.removeQueries({
        queryKey: reportQueryKey(profileId ?? '', reportId),
      });
      await refresh();
    },
  });
}

/**
 * Downloads a report and opens the share sheet (PRD 7, sections 34 and 35).
 *
 * Only ever on a press. PRD 7 section 13 ends its sequence at "Export / Share"
 * with no automatic export.
 */
export function useShareReport(appointmentId: string) {
  const profileId = useAppointmentProfileId();

  return useMutation<ExportOutcome, unknown, AppointmentReport>({
    mutationFn: (report) => exportAndShareReport(profileId ?? '', appointmentId, report),
  });
}

// --- background work --------------------------------------------------------

/**
 * Sends anything queued: when an appointment screen is focused, and again
 * whenever the phone comes back online (PRD 7, section 53).
 */
export function useSyncPendingAppointments() {
  const profileId = useAppointmentProfileId();
  const refresh = useRefreshAppointments(profileId);
  const authStatus = useAppStore((state) => state.authStatus);

  const sync = useCallback(async () => {
    if (authStatus !== 'authenticated' || profileId === null) return;
    const summary = await syncPending(profileId);
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
 * Keeps the phone's reminders in step with the upcoming appointments (s54).
 *
 * One place, driven by the upcoming list. Every write above invalidates that
 * list, so a time change, a cancellation and a reminders-off switch all
 * reschedule through here rather than each having its own cancel logic.
 */
export function useAppointmentReminders(appointments: Appointment[] | undefined) {
  useEffect(() => {
    if (appointments === undefined) return;
    void rebuildAppointmentReminders(appointments);
  }, [appointments]);
}
