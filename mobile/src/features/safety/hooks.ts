/**
 * Server state for Safety Monitoring, SOS and caregiver alerts (PRD 10).
 *
 * Four things worth reading rather than skimming.
 *
 * **The status query is the one that polls.** While a safety check or an
 * escalation is live the app refetches every few seconds, because the thing
 * it is showing has a deadline on the server and a screen that went stale
 * during one would be worse than useless. When nothing is happening it does
 * not poll at all: section 95 says not to interrupt somebody continuously,
 * and that applies to their battery as much as to their attention.
 *
 * **Nothing here counts down on its own authority.** The countdown comes from
 * `responseDeadlineAt`, which is a server timestamp (section 28). The screen
 * renders the difference; it never decides that time is up, and reloading the
 * app mid-countdown shows the same number it would have shown.
 *
 * **An SOS carries a client id generated before the first attempt.** A
 * request that timed out after the server stored it comes back as the same
 * event, so a retry cannot raise a second emergency (section 77).
 *
 * **Caregiver alerts are keyed by profile.** A caregiver may support two
 * people, and a cache keyed only by `safety-alerts` would show one person's
 * alerts under the other's name.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef } from 'react';

import { useOwnProfileId } from '../caregivers/hooks';
import { useAppStore } from '../../store/appStore';
import { deviceTimezone } from '../medications/schedule';
import {
  acknowledgeSafetyAlert,
  cancelSafetyEvent,
  fetchCapabilities,
  fetchSafetyAlerts,
  fetchSafetyEvent,
  fetchSafetyEvents,
  fetchSafetyStatus,
  markFalseAlarm,
  raiseSos,
  respondToSafetyEvent,
  startMonitoring,
  stopMonitoring,
} from './api';
import type {
  Capabilities,
  FalsePositiveReason,
  MonitoringSession,
  MonitoringStartInput,
  SafetyAlert,
  SafetyAlertList,
  SafetyEvent,
  SafetyEventDetail,
  SafetyStatus,
  UserResponse,
} from './types';

export const safetyStatusKey = (profileId: string) =>
  ['safety-status', profileId] as const;
export const capabilitiesKey = (profileId: string) =>
  ['safety-capabilities', profileId] as const;
export const safetyEventsKey = (profileId: string) =>
  ['safety-events', profileId] as const;
export const safetyEventKey = (profileId: string, eventId: string) =>
  ['safety-event', profileId, eventId] as const;
export const safetyAlertsKey = (profileId: string) =>
  ['safety-alerts', profileId] as const;

/**
 * How often to re-read the status while something is live.
 *
 * Three seconds, which is short enough that a 15-second timeout still shows a
 * moving countdown and long enough not to be a loop. Nothing depends on this
 * for correctness -- the deadlines are server-side and the worker is what
 * makes escalation timely (section 80) -- it only keeps the screen honest.
 */
const LIVE_POLL_MS = 3000;

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

export function useSafetyStatus() {
  const profileId = useOwnProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<SafetyStatus>({
    queryKey: safetyStatusKey(profileId ?? 'none'),
    queryFn: () => fetchSafetyStatus(profileId as string),
    enabled,
    // Only while something is happening. A phone idling on the Safety screen
    // with monitoring off has nothing to refetch.
    refetchInterval: (query) => (query.state.data?.activeEvent ? LIVE_POLL_MS : false),
  });
}

export function useSafetyCapabilities() {
  const profileId = useOwnProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<Capabilities>({
    queryKey: capabilitiesKey(profileId ?? 'none'),
    queryFn: () => fetchCapabilities(profileId as string),
    enabled,
  });
}

export function useSafetyEvents() {
  const profileId = useOwnProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<SafetyEvent[]>({
    queryKey: safetyEventsKey(profileId ?? 'none'),
    queryFn: () => fetchSafetyEvents(profileId as string),
    enabled,
  });
}

export function useSafetyEvent(eventId: string | null) {
  const profileId = useOwnProfileId();
  const enabled = useEnabled(profileId) && eventId !== null;
  return useQuery<SafetyEventDetail>({
    queryKey: safetyEventKey(profileId ?? 'none', eventId ?? 'none'),
    queryFn: () => fetchSafetyEvent(profileId as string, eventId as string),
    enabled,
  });
}

function useInvalidateSafety() {
  const client = useQueryClient();
  const profileId = useOwnProfileId();
  return useCallback(() => {
    if (profileId === null) return;
    void client.invalidateQueries({ queryKey: safetyStatusKey(profileId) });
    void client.invalidateQueries({ queryKey: safetyEventsKey(profileId) });
  }, [client, profileId]);
}

export function useStartMonitoring() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateSafety();
  return useMutation<MonitoringSession, Error, Omit<MonitoringStartInput, 'timezone'>>({
    // The phone's own zone, never the server's guess: "until bedtime" is a
    // wall-clock time and only the phone knows which one (section 6).
    mutationFn: (input) =>
      startMonitoring(profileId as string, { ...input, timezone: deviceTimezone() }),
    onSuccess: invalidate,
  });
}

export function useStopMonitoring() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateSafety();
  return useMutation<SafetyStatus, Error, { confirmActiveEvent?: boolean } | void>({
    mutationFn: (options) => stopMonitoring(profileId as string, options ?? {}),
    onSuccess: invalidate,
  });
}

/**
 * An emergency request (sections 12 and 77).
 *
 * The client id is generated once per hook instance and reused on every
 * attempt, so a retry after a timeout resolves to the event that already
 * exists rather than a second emergency.
 */
export function useRaiseSos() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateSafety();
  const clientEventId = useRef(newSosId());
  return useMutation<SafetyEventDetail, Error, void>({
    mutationFn: () => raiseSos(profileId as string, clientEventId.current),
    onSuccess: invalidate,
  });
}

export function useRespondToSafetyEvent() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateSafety();
  return useMutation<
    SafetyEventDetail,
    Error,
    { eventId: string; response: UserResponse }
  >({
    mutationFn: ({ eventId, response }) =>
      respondToSafetyEvent(profileId as string, eventId, response),
    onSuccess: invalidate,
  });
}

export function useCancelSafetyEvent() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateSafety();
  return useMutation<SafetyEventDetail, Error, string>({
    mutationFn: (eventId) => cancelSafetyEvent(profileId as string, eventId),
    onSuccess: invalidate,
  });
}

export function useMarkFalseAlarm() {
  const profileId = useOwnProfileId();
  const client = useQueryClient();
  const invalidate = useInvalidateSafety();
  return useMutation<
    SafetyEventDetail,
    Error,
    { eventId: string; falsePositive: boolean; reason: FalsePositiveReason | null }
  >({
    mutationFn: ({ eventId, falsePositive, reason }) =>
      markFalseAlarm(profileId as string, eventId, falsePositive, reason),
    onSuccess: (event) => {
      invalidate();
      if (profileId !== null) {
        void client.invalidateQueries({ queryKey: safetyEventKey(profileId, event.id) });
      }
    },
  });
}

// --- the caregiver side ------------------------------------------------------

/**
 * Safety alerts about one supported person (sections 83 and 97).
 *
 * Takes the profile id rather than reading the caregiver context, because
 * every caregiver screen already knows which person it is showing -- and a
 * hook that worked it out for itself would be a second place that decision
 * could be wrong.
 */
export function useSafetyAlerts(profileId: string | null) {
  const enabled = useEnabled(profileId);
  return useQuery<SafetyAlertList>({
    queryKey: safetyAlertsKey(profileId ?? 'none'),
    queryFn: () => fetchSafetyAlerts(profileId as string),
    enabled,
  });
}

export function useAcknowledgeSafetyAlert(profileId: string | null) {
  const client = useQueryClient();
  return useMutation<SafetyAlert, Error, string>({
    mutationFn: (alertId) => acknowledgeSafetyAlert(profileId as string, alertId),
    onSuccess: () => {
      if (profileId === null) return;
      void client.invalidateQueries({ queryKey: safetyAlertsKey(profileId) });
      void client.invalidateQueries({ queryKey: ['caregiver-home', profileId] });
    },
  });
}

/** A client id for one emergency request. Generated before the first attempt. */
export function newSosId(): string {
  const random = Math.random().toString(36).slice(2, 10);
  return `sos-${Date.now().toString(36)}-${random}`;
}

/**
 * Seconds left before a deadline, floored at zero.
 *
 * The deadline is the server's (section 28); this only subtracts. A screen
 * that decided time was up on its own would disagree with the backend the
 * moment a clock drifted, and the backend is the one that escalates.
 */
export function secondsUntil(deadline: string | null, now: Date): number | null {
  if (deadline === null) return null;
  const at = Date.parse(deadline);
  if (Number.isNaN(at)) return null;
  return Math.max(0, Math.round((at - now.getTime()) / 1000));
}
