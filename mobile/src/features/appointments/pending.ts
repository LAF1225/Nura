/**
 * Appointments and questions saved while offline (PRD 7, section 53).
 *
 * The rule this exists to keep: **nothing the user typed is silently lost.** If
 * the phone cannot reach the backend, the appointment or the question is written
 * to the device and the row says so, rather than a spinner that ends in nothing.
 *
 * Three decisions worth reading.
 *
 * **Two small queues, not one.** An appointment draft and a question draft are
 * sent to different endpoints and can fail independently, and a question belongs
 * to an appointment that may itself still be pending. Keeping them apart means
 * neither can block the other, and a question for an appointment that never
 * reached the server is dropped rather than retried forever.
 *
 * **The server enforces the idempotency, not this queue.** Every retry sends the
 * same client id, and the backend answers a replay with the row it already
 * stored (PRD 7, section 53). That is why a send that fails *after* the server
 * accepted it -- a dropped response -- still converges on one record.
 *
 * **Report generation is never queued.** A PDF is built by the backend, so there
 * is nothing useful to keep on the phone, and PRD 7 section 53 says plainly not
 * to pretend generation succeeded while offline. The screen says what happened
 * and the selections are kept so it can be tried again.
 *
 * Where it is stored: AsyncStorage, in the app's private data directory. Not
 * secure storage -- that is for credentials. It does hold appointment titles and
 * question text, which is unavoidable for an offline draft and is why nothing
 * here is ever logged (PRD 7, section 57).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { isRetryable } from '../reliability/retry';
import { createLogger } from '../../utils/logger';
import { createAppointment, createQuestion } from './api';
import type { PendingAppointment, PendingQuestion } from './types';

const log = createLogger('appointments');

const APPOINTMENTS_KEY = 'nura.appointments.pending';
const QUESTIONS_KEY = 'nura.appointments.pendingQuestions';

/**
 * Which failures are worth sending again -- the shared policy (PRD 13, s30).
 *
 * This file held its own copy of the list until PRD 13, as four other queues
 * did, all five identical. The policy and the reasoning behind each kind now
 * live in `features/reliability/retry.ts`; it is re-exported here because
 * other modules already import the name from this one.
 */
export { isRetryable };

function isPendingAppointment(value: unknown): value is PendingAppointment {
  if (value === null || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.clientAppointmentId === 'string' &&
    typeof record.savedAt === 'string' &&
    typeof record.payload === 'object' &&
    record.payload !== null
  );
}

function isPendingQuestion(value: unknown): value is PendingQuestion {
  if (value === null || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.clientQuestionId === 'string' &&
    typeof record.appointmentId === 'string' &&
    typeof record.text === 'string' &&
    typeof record.savedAt === 'string'
  );
}

async function readAll<T>(
  key: string,
  guard: (value: unknown) => value is T
): Promise<T[]> {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Records from an older build, or corrupted ones, are dropped rather than
    // allowed to crash the screen that lists them.
    return parsed.filter(guard);
  } catch {
    return [];
  }
}

async function writeAll<T>(key: string, records: T[]): Promise<void> {
  if (records.length === 0) {
    await AsyncStorage.removeItem(key);
    return;
  }
  await AsyncStorage.setItem(key, JSON.stringify(records));
}

// --- appointments -----------------------------------------------------------

export function loadPendingAppointments(): Promise<PendingAppointment[]> {
  return readAll(APPOINTMENTS_KEY, isPendingAppointment);
}

/** Replaces any record with the same client id. One record per save. */
export async function queueAppointment(record: PendingAppointment): Promise<void> {
  const existing = await loadPendingAppointments();
  await writeAll(APPOINTMENTS_KEY, [
    ...existing.filter((item) => item.clientAppointmentId !== record.clientAppointmentId),
    record,
  ]);
}

export async function clearPendingAppointment(clientId: string): Promise<void> {
  const existing = await loadPendingAppointments();
  await writeAll(
    APPOINTMENTS_KEY,
    existing.filter((item) => item.clientAppointmentId !== clientId)
  );
}

export async function clearAllPendingAppointments(): Promise<void> {
  await AsyncStorage.removeItem(APPOINTMENTS_KEY);
}

// --- questions --------------------------------------------------------------

export function loadPendingQuestions(): Promise<PendingQuestion[]> {
  return readAll(QUESTIONS_KEY, isPendingQuestion);
}

export async function queueQuestion(record: PendingQuestion): Promise<void> {
  const existing = await loadPendingQuestions();
  await writeAll(QUESTIONS_KEY, [
    ...existing.filter((item) => item.clientQuestionId !== record.clientQuestionId),
    record,
  ]);
}

export async function clearPendingQuestion(clientId: string): Promise<void> {
  const existing = await loadPendingQuestions();
  await writeAll(
    QUESTIONS_KEY,
    existing.filter((item) => item.clientQuestionId !== clientId)
  );
}

export async function clearAllPendingQuestions(): Promise<void> {
  await AsyncStorage.removeItem(QUESTIONS_KEY);
}

/** Pending questions for one appointment, for its detail screen. */
export function pendingForAppointment(
  records: PendingQuestion[],
  appointmentId: string
): PendingQuestion[] {
  return records.filter((record) => record.appointmentId === appointmentId);
}

// --- saving -----------------------------------------------------------------

export interface SaveOutcome<T> {
  /** The stored record, when the save reached the server. */
  record: T | null;
  /** `pending` means it is on this phone and not yet on the server. */
  status: 'synced' | 'pending';
}

/**
 * Saves an appointment, or keeps it on the phone if that is not possible.
 *
 * Resolves either way: "saved on this phone" is a success from the user's point
 * of view, and the screen says which happened. It rejects only when the server
 * refuses the appointment itself -- an unknown clinician, an unknown zone --
 * which is a rule the user needs to hear about rather than a failure to retry.
 */
export async function submitOrQueueAppointment(
  profileId: string,
  record: PendingAppointment
): Promise<SaveOutcome<Awaited<ReturnType<typeof createAppointment>>>> {
  try {
    const saved = await createAppointment(profileId, record.payload);
    await clearPendingAppointment(record.clientAppointmentId);
    return { record: saved, status: 'synced' };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    await queueAppointment(record);
    // Nothing about the appointment is logged -- a line says what happened,
    // never what it was about (PRD 7, section 57).
    log.warn('appointment saved on this device; will sync later');
    return { record: null, status: 'pending' };
  }
}

/**
 * Adds a question, or keeps it on the phone if that is not possible.
 *
 * A question for an appointment that is itself still pending cannot be sent:
 * there is no appointment id to attach it to yet. Those are queued and picked up
 * by the next sync, once the appointment has landed and the screen has been
 * reopened with the real id.
 */
export async function submitOrQueueQuestion(
  profileId: string,
  record: PendingQuestion
): Promise<SaveOutcome<Awaited<ReturnType<typeof createQuestion>>>> {
  try {
    const saved = await createQuestion(profileId, record.appointmentId, {
      text: record.text,
      client_question_id: record.clientQuestionId,
    });
    await clearPendingQuestion(record.clientQuestionId);
    return { record: saved, status: 'synced' };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    await queueQuestion(record);
    log.warn('question saved on this device; will sync later');
    return { record: null, status: 'pending' };
  }
}

export interface SyncSummary {
  sent: number;
  /** Still waiting; those records are kept. */
  pending: number;
  /** Could never succeed as written, and have been dropped. */
  discarded: number;
}

function empty(): SyncSummary {
  return { sent: 0, pending: 0, discarded: 0 };
}

/**
 * Tries to send everything queued.
 *
 * Safe to call often: it does nothing when both queues are empty, and every send
 * is idempotent on the server, so a duplicate attempt leaves the same single row
 * (PRD 7, section 53).
 *
 * Appointments go first. A question can only be sent once the appointment it
 * belongs to exists, and doing them in this order means a pair saved together
 * offline lands in one pass rather than two.
 */
export async function syncPending(profileId: string): Promise<SyncSummary> {
  const summary = empty();

  for (const record of await loadPendingAppointments()) {
    try {
      const outcome = await submitOrQueueAppointment(profileId, record);
      if (outcome.status === 'synced') summary.sent += 1;
      else summary.pending += 1;
    } catch {
      // The server refused the appointment outright. Keeping it would mean
      // retrying forever.
      await clearPendingAppointment(record.clientAppointmentId);
      summary.discarded += 1;
    }
  }

  for (const record of await loadPendingQuestions()) {
    try {
      const outcome = await submitOrQueueQuestion(profileId, record);
      if (outcome.status === 'synced') summary.sent += 1;
      else summary.pending += 1;
    } catch {
      await clearPendingQuestion(record.clientQuestionId);
      summary.discarded += 1;
    }
  }

  if (summary.sent > 0 || summary.discarded > 0) {
    log.info('queued appointments synced', {
      sent: summary.sent,
      discarded: summary.discarded,
    });
  }
  return summary;
}
