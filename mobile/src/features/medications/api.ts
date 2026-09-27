/**
 * Medication endpoints (PRD 5, sections 51 and 52).
 *
 * Every path is nested under the profile the records belong to, because that
 * is what they belong to -- not to the account that is signed in.
 *
 * Responses are parsed rather than cast. The fields the app actually reasons
 * about -- a dose's status and window, whether it can be snoozed, what is left
 * of a supply -- are checked and given safe fallbacks, so a field the server
 * renames cannot turn into a screen that silently offers the wrong button.
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  Adherence,
  DoseActionInput,
  DoseActionResult,
  DoseSource,
  DoseStatus,
  DoseWindow,
  MedicationDose,
  MedicationSchedule,
  MedicationSupply,
  ScheduleType,
  SchedulePayload,
  SkipReasonCode,
  TodayMedications,
} from './types';

const DOSE_STATUSES: readonly DoseStatus[] = [
  'scheduled',
  'snoozed',
  'taken',
  'skipped',
  'missed',
  'cancelled',
];
const DOSE_WINDOWS: readonly DoseWindow[] = ['upcoming', 'due', 'overdue', 'completed'];
const DOSE_SOURCES: readonly DoseSource[] = ['app', 'robot_voice', 'caregiver', 'system'];
const SKIP_REASONS: readonly SkipReasonCode[] = [
  'none',
  'feeling_unwell',
  'ran_out',
  'clinician_advised',
  'too_late',
  'other',
];
const SCHEDULE_TYPES: readonly ScheduleType[] = ['daily', 'specific_days'];

function object(value: unknown, endpoint: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('server', `Unexpected response shape from ${endpoint}.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(
  body: Record<string, unknown>,
  key: string,
  endpoint: string
): string {
  const value = body[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new ApiError('server', `${endpoint} response is missing ${key}.`);
  }
  return value;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function nullableCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function maybeOneOf<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

// --- parsing ----------------------------------------------------------------

export function parseDose(raw: unknown, endpoint: string): MedicationDose {
  const body = object(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    medicationId: requiredString(body, 'medication_id', endpoint),
    medicationName: text(body.medication_name) ?? 'Medication',
    medicationDose: text(body.medication_dose),
    scheduleId: text(body.schedule_id),
    scheduledFor: requiredString(body, 'scheduled_for', endpoint),
    localDate: requiredString(body, 'local_date', endpoint),
    status: oneOf(body.status, DOSE_STATUSES, 'scheduled'),
    window: oneOf(body.window, DOSE_WINDOWS, 'upcoming'),
    actionAt: text(body.action_at),
    source: maybeOneOf(body.source, DOSE_SOURCES),
    skipReasonCode: maybeOneOf(body.skip_reason_code, SKIP_REASONS),
    skipReasonText: text(body.skip_reason_text),
    snoozedUntil: text(body.snoozed_until),
    snoozeCount: count(body.snooze_count),
    late: body.late === true,
    canSnooze: body.can_snooze === true,
    syncStatus: 'synced',
  };
}

export function parseSchedule(raw: unknown, endpoint: string): MedicationSchedule {
  const body = object(raw, endpoint);
  const times = Array.isArray(body.times) ? body.times : [];
  return {
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    medicationId: requiredString(body, 'medication_id', endpoint),
    medicationName: text(body.medication_name) ?? 'Medication',
    medicationDose: text(body.medication_dose),
    scheduleType: oneOf(body.schedule_type, SCHEDULE_TYPES, 'daily'),
    timezone: text(body.timezone) ?? 'UTC',
    startDate: requiredString(body, 'start_date', endpoint),
    endDate: text(body.end_date),
    isActive: body.is_active !== false,
    pausedAt: text(body.paused_at),
    times: times.map((entry) => {
      const slot = object(entry, endpoint);
      return {
        id: text(slot.id) ?? undefined,
        timeOfDay: text(slot.time_of_day) ?? '08:00:00',
        weekday: nullableCount(slot.weekday),
      };
    }),
  };
}

export function parseActionResult(raw: unknown, endpoint: string): DoseActionResult {
  const body = object(raw, endpoint);
  return {
    dose: parseDose(body.dose, endpoint),
    applied: body.applied === true,
    supplyRemaining: nullableCount(body.supply_remaining),
    lowSupply: body.low_supply === true,
  };
}

export function parseAdherence(raw: unknown, endpoint: string): Adherence {
  const body = object(raw, endpoint);
  return {
    fromDate: requiredString(body, 'from_date', endpoint),
    toDate: requiredString(body, 'to_date', endpoint),
    taken: count(body.taken),
    skipped: count(body.skipped),
    missed: count(body.missed),
    total: count(body.total),
    percent: nullableCount(body.percent),
  };
}

export function parseSupply(raw: unknown, endpoint: string): MedicationSupply {
  const body = object(raw, endpoint);
  return {
    medicationId: requiredString(body, 'medication_id', endpoint),
    medicationName: text(body.medication_name) ?? 'Medication',
    trackingEnabled: body.tracking_enabled === true,
    remainingDoses: nullableCount(body.remaining_doses),
    refillThresholdDoses: nullableCount(body.refill_threshold_doses),
    lastRefillDate: text(body.last_refill_date),
    low: body.low === true,
  };
}

export function parseTodayMedications(raw: unknown): TodayMedications | null {
  if (raw === null || raw === undefined) return null;
  const endpoint = '/api/v1/today';
  const body = object(raw, endpoint);
  const next = body.next_due;
  const low = Array.isArray(body.low_supply) ? body.low_supply : [];

  return {
    nextDue:
      next === null || next === undefined
        ? null
        : (() => {
            const due = object(next, endpoint);
            return {
              doseId: requiredString(due, 'dose_id', endpoint),
              medicationId: requiredString(due, 'medication_id', endpoint),
              medicationName: text(due.medication_name) ?? 'Medication',
              medicationDose: text(due.medication_dose),
              scheduledFor: requiredString(due, 'scheduled_for', endpoint),
              status: oneOf(due.status, DOSE_STATUSES, 'scheduled'),
              window: oneOf(due.window, DOSE_WINDOWS, 'upcoming'),
              canSnooze: due.can_snooze === true,
            };
          })(),
    dueTodayCount: count(body.due_today_count),
    overdueCount: count(body.overdue_count),
    remainingTodayCount: count(body.remaining_today_count),
    lowSupply: low.map((entry) => {
      const item = object(entry, endpoint);
      return {
        medicationId: requiredString(item, 'medication_id', endpoint),
        medicationName: text(item.medication_name) ?? 'Medication',
        remainingDoses: count(item.remaining_doses),
      };
    }),
    hasSchedules: body.has_schedules === true,
  };
}

// --- requests ---------------------------------------------------------------

function base(profileId: string): string {
  return `/api/v1/profiles/${encodeURIComponent(profileId)}`;
}

export async function fetchSchedules(
  profileId: string,
  signal?: AbortSignal
): Promise<MedicationSchedule[]> {
  const url = `${base(profileId)}/medication-schedules`;
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseSchedule(entry, url));
}

function schedulePayloadBody(payload: SchedulePayload): Record<string, unknown> {
  return {
    medication_id: payload.medicationId,
    schedule_type: payload.scheduleType,
    timezone: payload.timezone,
    start_date: payload.startDate,
    end_date: payload.endDate,
    times: payload.times.map((entry) => ({
      time_of_day: entry.timeOfDay,
      weekday: entry.weekday,
    })),
  };
}

export async function createSchedule(
  profileId: string,
  payload: SchedulePayload
): Promise<MedicationSchedule> {
  const url = `${base(profileId)}/medication-schedules`;
  return parseSchedule(
    await apiRequest<unknown>(url, {
      method: 'POST',
      body: schedulePayloadBody(payload),
    }),
    url
  );
}

export async function updateSchedule(
  profileId: string,
  scheduleId: string,
  payload: SchedulePayload
): Promise<MedicationSchedule> {
  const url = `${base(profileId)}/medication-schedules/${encodeURIComponent(scheduleId)}`;
  // `medication_id` is deliberately left out: a schedule stays attached to the
  // medication it was made for. Moving reminders to a different medication is
  // a new schedule, not an edit.
  const { medication_id: _ignored, ...body } = schedulePayloadBody(payload);
  return parseSchedule(await apiRequest<unknown>(url, { method: 'PATCH', body }), url);
}

export async function setSchedulePaused(
  profileId: string,
  scheduleId: string,
  paused: boolean
): Promise<MedicationSchedule> {
  const url = `${base(profileId)}/medication-schedules/${encodeURIComponent(
    scheduleId
  )}/pause`;
  return parseSchedule(
    await apiRequest<unknown>(url, { method: 'POST', body: { paused } }),
    url
  );
}

export async function deleteSchedule(
  profileId: string,
  scheduleId: string
): Promise<void> {
  await apiRequest<void>(
    `${base(profileId)}/medication-schedules/${encodeURIComponent(scheduleId)}`,
    { method: 'DELETE' }
  );
}

export async function fetchDoses(
  profileId: string,
  range: { fromDate: string; toDate: string; medicationId?: string },
  signal?: AbortSignal
): Promise<MedicationDose[]> {
  const query = new URLSearchParams({
    from_date: range.fromDate,
    to_date: range.toDate,
  });
  if (range.medicationId) query.set('medication_id', range.medicationId);

  const url = `${base(profileId)}/medication-doses?${query.toString()}`;
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseDose(entry, url));
}

export async function fetchTodayDoses(
  profileId: string,
  localDate: string,
  signal?: AbortSignal
): Promise<MedicationDose[]> {
  const url = `${base(profileId)}/medication-doses/today?local_date=${localDate}`;
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseDose(entry, url));
}

/** The body for one of the three actions. Never sends a status or a source. */
export function actionBody(input: DoseActionInput): Record<string, unknown> {
  if (input.action === 'snooze') {
    return { minutes: input.minutes ?? 10 };
  }
  if (input.action === 'skip') {
    return {
      reason_code: input.reasonCode ?? 'none',
      reason_text: input.reasonText ?? null,
      action_at: input.actionAt ?? null,
    };
  }
  return { action_at: input.actionAt ?? null };
}

export async function submitDoseAction(
  profileId: string,
  doseId: string,
  input: DoseActionInput
): Promise<DoseActionResult> {
  const url = `${base(profileId)}/medication-doses/${encodeURIComponent(doseId)}/${
    input.action
  }`;
  return parseActionResult(
    await apiRequest<unknown>(url, { method: 'POST', body: actionBody(input) }),
    url
  );
}

export async function fetchAdherence(
  profileId: string,
  days: number,
  signal?: AbortSignal
): Promise<Adherence> {
  const url = `${base(profileId)}/medication-adherence?days=${days}`;
  return parseAdherence(await apiRequest<unknown>(url, { signal }), url);
}

export async function fetchSupply(
  profileId: string,
  signal?: AbortSignal
): Promise<MedicationSupply[]> {
  const url = `${base(profileId)}/medication-supply`;
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseSupply(entry, url));
}

export interface SupplyPatch {
  trackingEnabled?: boolean;
  remainingDoses?: number;
  refillThresholdDoses?: number | null;
}

export async function updateSupply(
  profileId: string,
  medicationId: string,
  patch: SupplyPatch
): Promise<MedicationSupply> {
  const url = `${base(profileId)}/medication-supply/${encodeURIComponent(medicationId)}`;
  const body: Record<string, unknown> = {};
  if (patch.trackingEnabled !== undefined) body.tracking_enabled = patch.trackingEnabled;
  if (patch.remainingDoses !== undefined) body.remaining_doses = patch.remainingDoses;
  if (patch.refillThresholdDoses !== undefined) {
    body.refill_threshold_doses = patch.refillThresholdDoses;
  }
  return parseSupply(await apiRequest<unknown>(url, { method: 'PATCH', body }), url);
}

export async function recordRefill(
  profileId: string,
  medicationId: string,
  remainingDoses: number,
  refilledOn: string
): Promise<MedicationSupply> {
  const url = `${base(profileId)}/medication-supply/${encodeURIComponent(
    medicationId
  )}/refill`;
  return parseSupply(
    await apiRequest<unknown>(url, {
      method: 'POST',
      body: { remaining_doses: remainingDoses, refilled_on: refilledOn },
    }),
    url
  );
}
