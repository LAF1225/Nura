/**
 * The appointment form's draft, and what it becomes (PRD 7, sections 8 and 53).
 *
 * One draft representation, one validator, one payload builder -- used by the new
 * appointment form and by the edit form, so the two can never disagree about
 * what a valid appointment is.
 *
 * Three decisions worth knowing.
 *
 * **Only the title, the date and the time are required.** PRD 7 section 8 asks
 * for the optional fields to stay optional, and somebody noting down a date
 * should not be stopped by a form.
 *
 * **The id is generated when the draft starts, not when it is sent.** That is
 * what makes a retry safe: the same `clientAppointmentId` reaches the server
 * however many times the request is attempted, and the second one is answered
 * with the appointment the first one created (PRD 7, section 53).
 *
 * **The time zone is the phone's, and it is stored.** A date and a time are
 * meaningless without one, and PRD 7 section 42 wants the zone the appointment
 * was arranged in -- which is where the person was when they typed it.
 */
import * as Crypto from 'expo-crypto';
import * as Localization from 'expo-localization';

import { localDateString } from '../../utils/date';
import type {
  Appointment,
  AppointmentDraft,
  AppointmentPayload,
  AppointmentType,
} from './types';

/** Mirrors the API's own limits, so a refusal is not the first the user hears. */
export const TITLE_MAX_LENGTH = 120;
export const NAME_MAX_LENGTH = 120;
export const SHORT_TEXT_MAX_LENGTH = 200;
export const PHONE_MAX_LENGTH = 40;
export const NOTES_MAX_LENGTH = 2000;

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_PATTERN = /^([01]\d|2[0-3]):([0-5]\d)$/;

function randomHex(byteCount: number): string {
  try {
    return Array.from(Crypto.getRandomBytes(byteCount), (byte) =>
      byte.toString(16).padStart(2, '0')
    ).join('');
  } catch {
    // No native crypto module, which happens under a test runner. An
    // idempotency key only has to be unique within one profile, so a timestamp
    // and a random suffix is a correct fallback -- it is not a secret and
    // nothing authenticates with it.
    return `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
  }
}

/**
 * A fresh id for a draft.
 *
 * Prefixed so a value in a log or a database row is recognisable as a client id
 * rather than being mistaken for one of ours.
 */
export function newClientId(prefix = 'appointment'): string {
  return `${prefix}-${randomHex(12)}`;
}

/** The phone's own IANA zone, or UTC if the platform will not say. */
export function deviceTimezone(): string {
  try {
    const zone = Localization.getCalendars()[0]?.timeZone;
    return typeof zone === 'string' && zone.length > 0 ? zone : 'UTC';
  } catch {
    return 'UTC';
  }
}

/** `HH:MM` for a Date, on a 24-hour clock, in the device's zone. */
export function localTimeString(date: Date = new Date()): string {
  const hours = `${date.getHours()}`.padStart(2, '0');
  const minutes = `${date.getMinutes()}`.padStart(2, '0');
  return `${hours}:${minutes}`;
}

export function newDraft(options: { now?: Date } = {}): AppointmentDraft {
  const now = options.now ?? new Date();
  return {
    clientAppointmentId: newClientId(),
    title: '',
    date: localDateString(now),
    // A round hour, so the commonest edit is the hour rather than the minutes.
    time: '09:00',
    timezone: deviceTimezone(),
    appointmentType: 'other',
    clinicianId: null,
    locationName: '',
    address: '',
    phone: '',
    notes: '',
    remindersEnabled: true,
  };
}

/**
 * A draft that edits an existing appointment.
 *
 * The date and the time are taken from the stored labels rather than recomputed
 * from the instant: the server already resolved them in the appointment's own
 * zone, and doing it again here in JavaScript is exactly the duplication PRD 7
 * section 42 is easiest to get wrong in.
 */
export function draftFrom(appointment: Appointment): AppointmentDraft {
  return {
    clientAppointmentId: newClientId(),
    title: appointment.title,
    date: appointment.localDate,
    time: timeFromLabel(appointment.timeLabel),
    timezone: appointment.timezone,
    appointmentType: appointment.appointmentType,
    clinicianId: appointment.clinician?.id ?? null,
    locationName: appointment.locationName ?? '',
    address: appointment.address ?? '',
    phone: appointment.phone ?? '',
    notes: appointment.notes ?? '',
    remindersEnabled: appointment.remindersEnabled,
  };
}

/** "3:30 PM" -> "15:30". Returns "09:00" for anything unparseable. */
export function timeFromLabel(label: string): string {
  const match = /^(\d{1,2}):(\d{2})\s*(AM|PM)$/i.exec(label.trim());
  if (match === null) return '09:00';
  const twelve = Number(match[1]) % 12;
  const minutes = match[2];
  const isPm = match[3]!.toUpperCase() === 'PM';
  const hours = `${twelve + (isPm ? 12 : 0)}`.padStart(2, '0');
  return `${hours}:${minutes}`;
}

export interface DraftErrors {
  title?: string;
  date?: string;
  time?: string;
}

/**
 * What is wrong with the draft, if anything.
 *
 * Only the three required fields are checked. A date in the past is *not* an
 * error: people record appointments they have already been to, and PRD 7
 * section 41 has a list for them.
 */
export function validateDraft(draft: AppointmentDraft): DraftErrors {
  const errors: DraftErrors = {};
  const title = draft.title.trim();

  if (title.length === 0) {
    errors.title = 'Give the appointment a name, like “Cardiology follow-up”.';
  } else if (title.length > TITLE_MAX_LENGTH) {
    errors.title = `Keep this under ${TITLE_MAX_LENGTH} characters.`;
  }

  if (!DATE_PATTERN.test(draft.date.trim())) {
    errors.date = 'Use a date like 2026-10-02.';
  } else if (Number.isNaN(Date.parse(`${draft.date.trim()}T00:00:00`))) {
    errors.date = 'That date does not exist.';
  }

  if (!TIME_PATTERN.test(draft.time.trim())) {
    errors.time = 'Use a 24-hour time like 15:30.';
  }

  return errors;
}

export function isSavable(draft: AppointmentDraft): boolean {
  return Object.keys(validateDraft(draft)).length === 0;
}

function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length === 0 ? null : trimmed;
}

/**
 * The instant a local date and time refer to, in a named zone.
 *
 * The zone is sent to the server *as well as* the instant, and the server is
 * what resolves the two into a displayed time (PRD 7, section 42). What this has
 * to get right is the instant, and it does so using the device's own offset --
 * correct whenever the appointment is in the zone the phone is in, which is the
 * case for essentially every appointment somebody types in.
 *
 * Someone entering an appointment in a *different* zone from the one they are
 * standing in would get an instant offset by the difference. Fixing that needs a
 * time-zone-aware date picker, which PRD 7 does not ask for; the zone travels
 * with the record either way, so nothing is lost and it can be corrected later.
 */
export function instantFor(date: string, time: string): string {
  const parsed = new Date(`${date.trim()}T${time.trim()}:00`);
  return Number.isNaN(parsed.getTime()) ? new Date().toISOString() : parsed.toISOString();
}

export function appointmentPayload(
  draft: AppointmentDraft,
  options: { withClientId?: boolean } = {}
): AppointmentPayload {
  const payload: AppointmentPayload = {
    title: draft.title.trim(),
    scheduled_at: instantFor(draft.date, draft.time),
    timezone: draft.timezone,
    appointment_type: draft.appointmentType,
    clinician_id: draft.clinicianId,
    location_name: trimmedOrNull(draft.locationName),
    address: trimmedOrNull(draft.address),
    phone: trimmedOrNull(draft.phone),
    notes: trimmedOrNull(draft.notes),
    reminders_enabled: draft.remindersEnabled,
  };
  if (options.withClientId !== false) {
    payload.client_appointment_id = draft.clientAppointmentId;
  }
  return payload;
}

/** A PATCH body: the same fields, without the id, which cannot change. */
export function appointmentPatch(
  draft: AppointmentDraft
): Omit<AppointmentPayload, 'client_appointment_id'> {
  const { client_appointment_id: _ignored, ...patch } = appointmentPayload(draft);
  return patch;
}

export const APPOINTMENT_TYPE_VALUES: readonly AppointmentType[] = [
  'primary_care',
  'specialist',
  'therapy',
  'physiotherapy',
  'dentist',
  'lab',
  'imaging',
  'other',
];
