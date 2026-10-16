/**
 * The offline check-in queue (PRD 3, sections 26-28).
 *
 * The rule this exists to keep: **a user's input is never silently
 * discarded.** If the phone cannot reach the backend, the answer is written to
 * the device and the card says so, rather than a spinner that ends in nothing.
 *
 * Deliberately narrow. This is one entry for one day -- not a general offline
 * synchronisation engine for the whole app, which PRD 3 section 27 explicitly
 * rules out. There is at most one pending check-in at a time, because there is
 * at most one check-in per day and only today's can be edited.
 *
 * Where it is stored: AsyncStorage, in the app's private data directory. Not
 * secure storage -- that is for credentials, is size-limited, and a queued
 * answer is a draft, not a secret. The note is never logged, and never leaves
 * the device except in the request that stores it (PRD 3, section 44).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { DailyCheckIn, WellbeingLevel } from '../../types/today';
import { createLogger } from '../../utils/logger';
import { isRetryable } from '../../features/reliability/retry';
import { submitDailyCheckIn, type CheckInSaved } from '../api/today';

const log = createLogger('checkins');

const STORAGE_KEY = 'nura.checkin.pending';

/** A check-in the user has made but the backend has not confirmed. */
export interface PendingCheckIn {
  localDate: string;
  wellbeingLevel: WellbeingLevel;
  note: string | null;
  /** When the user chose it, which is what settles a conflict later. */
  clientUpdatedAt: string;
}

/**
 * Which failures are worth sending again -- the shared policy (PRD 13, s30).
 *
 * This file held its own copy of the list until PRD 13, as four other queues
 * did, all five identical. The policy and the reasoning behind each kind now
 * live in `features/reliability/retry.ts`; it is re-exported here because
 * other modules already import the name from this one.
 */
export { isRetryable };

function isPendingCheckIn(value: unknown): value is PendingCheckIn {
  if (value === null || typeof value !== 'object') return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.localDate === 'string' &&
    (entry.wellbeingLevel === 'good' ||
      entry.wellbeingLevel === 'okay' ||
      entry.wellbeingLevel === 'not_great') &&
    (entry.note === null || typeof entry.note === 'string') &&
    typeof entry.clientUpdatedAt === 'string'
  );
}

export async function loadPendingCheckIn(): Promise<PendingCheckIn | null> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    // A stored entry from an older build, or a corrupted one, is dropped
    // rather than allowed to crash the screen that reads it.
    return isPendingCheckIn(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export async function savePendingCheckIn(entry: PendingCheckIn): Promise<void> {
  // The note is in this value; it is written to the device and nowhere else.
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(entry));
}

export async function clearPendingCheckIn(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
}

/** A pending entry as the card should render it. */
export function pendingAsCheckIn(entry: PendingCheckIn): DailyCheckIn {
  return {
    date: entry.localDate,
    wellbeingLevel: entry.wellbeingLevel,
    note: entry.note,
    updatedAt: entry.clientUpdatedAt,
    syncStatus: 'pending',
  };
}

export interface SubmitOutcome {
  checkIn: DailyCheckIn;
  /** `pending` means it is saved on this phone and not yet on the server. */
  status: 'synced' | 'pending';
  /** False when the server kept a newer answer of its own. */
  applied: boolean;
}

/**
 * Sends a check-in, or keeps it on the phone if that is not possible.
 *
 * Only transport failures are queued. A refusal the server would repeat --
 * a rejected value, a profile that is not the caller's -- is thrown, because
 * retrying it later would fail in exactly the same way.
 */
export async function submitOrQueue(
  submission: Omit<PendingCheckIn, 'clientUpdatedAt'> & { clientUpdatedAt?: string }
): Promise<SubmitOutcome> {
  const entry: PendingCheckIn = {
    ...submission,
    clientUpdatedAt: submission.clientUpdatedAt ?? new Date().toISOString(),
  };

  try {
    const saved: CheckInSaved = await submitDailyCheckIn({
      localDate: entry.localDate,
      wellbeingLevel: entry.wellbeingLevel,
      note: entry.note,
      clientUpdatedAt: entry.clientUpdatedAt,
    });
    await clearPendingCheckIn();
    return { checkIn: saved.checkIn, status: 'synced', applied: saved.applied };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    await savePendingCheckIn(entry);
    log.warn('check-in saved on this device; will sync later');
    return { checkIn: pendingAsCheckIn(entry), status: 'pending', applied: false };
  }
}

export type SyncResult =
  /** Nothing was waiting. */
  | { status: 'idle' }
  /** The queued entry reached the backend. `applied` false means it lost. */
  | { status: 'synced'; checkIn: DailyCheckIn; applied: boolean }
  /** Still waiting; the entry is kept. */
  | { status: 'pending'; checkIn: DailyCheckIn }
  /** The entry could never succeed and has been dropped. */
  | { status: 'discarded' };

/**
 * Tries to send whatever is queued.
 *
 * Safe to call often: it does nothing when the queue is empty, and the PUT is
 * idempotent, so a duplicate send leaves the same single row.
 */
export async function syncPendingCheckIn(): Promise<SyncResult> {
  const entry = await loadPendingCheckIn();
  if (entry === null) return { status: 'idle' };

  try {
    const saved = await submitDailyCheckIn({
      localDate: entry.localDate,
      wellbeingLevel: entry.wellbeingLevel,
      note: entry.note,
      clientUpdatedAt: entry.clientUpdatedAt,
    });
    await clearPendingCheckIn();
    log.info('a queued check-in reached the backend');
    // `applied: false` means the server had a newer answer. The caller adopts
    // the returned check-in, which is how the two converge (PRD 3, s28).
    return { status: 'synced', checkIn: saved.checkIn, applied: saved.applied };
  } catch (error) {
    if (isRetryable(error)) {
      return { status: 'pending', checkIn: pendingAsCheckIn(entry) };
    }
    // The server refused it outright -- most likely the queued day is no
    // longer anybody's today. Keeping it would mean retrying forever.
    await clearPendingCheckIn();
    log.warn('a queued check-in was refused and has been dropped');
    return { status: 'discarded' };
  }
}
