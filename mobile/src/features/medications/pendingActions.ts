/**
 * Dose actions taken while offline (PRD 5, sections 62, 63 and 64).
 *
 * The rule this exists to keep: **a medication action is never silently
 * lost.** If the phone cannot reach the backend, Taken, Snooze or Skip is
 * written to the device and the row says so, rather than a spinner that ends
 * in nothing.
 *
 * Narrow on purpose. It queues *one action per dose*, not a log of them:
 * pressing Taken and then Skip on the same dose should send one final answer,
 * because the server holds one row per dose and the last thing the person
 * decided is the thing they meant (PRD 5, section 63). That also means a
 * queue cannot grow without limit from somebody tapping a button repeatedly.
 *
 * Each entry carries `actionAt` -- when the user actually pressed it. That is
 * what lets the server keep a newer answer made on another device instead of
 * letting a stale queued Taken overwrite it.
 *
 * Where it is stored: AsyncStorage, in the app's private data directory. Not
 * secure storage -- that is for credentials. The medication name is *not*
 * stored here; only a dose id, which means nothing on its own
 * (PRD 5, section 64).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { createLogger } from '../../utils/logger';
import { isRetryable } from '../reliability/retry';
import { submitDoseAction } from './api';
import type { DoseActionInput, DoseActionResult, PendingDoseAction } from './types';

const log = createLogger('medications');

const STORAGE_KEY = 'nura.medications.pendingActions';

/**
 * Failures worth keeping the entry for. Everything else means the request
 * would fail the same way forever, so holding onto it would be a queue that
 * retries and never drains.
 */

function isPendingAction(value: unknown): value is PendingDoseAction {
  if (value === null || typeof value !== 'object') return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.doseId === 'string' &&
    (entry.action === 'taken' || entry.action === 'snooze' || entry.action === 'skip') &&
    typeof entry.actionAt === 'string'
  );
}

export async function loadPendingActions(): Promise<PendingDoseAction[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Entries from an older build, or corrupted ones, are dropped rather than
    // allowed to crash the screen that reads them.
    return parsed.filter(isPendingAction);
  } catch {
    return [];
  }
}

async function writeAll(entries: PendingDoseAction[]): Promise<void> {
  if (entries.length === 0) {
    await AsyncStorage.removeItem(STORAGE_KEY);
    return;
  }
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
}

/** Replaces any queued action for the same dose. One answer per dose. */
export async function queueAction(entry: PendingDoseAction): Promise<void> {
  const existing = await loadPendingActions();
  await writeAll([...existing.filter((item) => item.doseId !== entry.doseId), entry]);
}

export async function clearPendingAction(doseId: string): Promise<void> {
  const existing = await loadPendingActions();
  await writeAll(existing.filter((item) => item.doseId !== doseId));
}

export async function clearAllPendingActions(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
}

export interface ActionOutcome {
  /** Null when the action is queued: there is no server answer to show yet. */
  result: DoseActionResult | null;
  /** `pending` means it is saved on this phone and not yet on the server. */
  status: 'synced' | 'pending';
}

/**
 * Sends a dose action, or keeps it on the phone if that is not possible.
 *
 * Resolves either way: "saved on this phone" is a success from the user's
 * point of view, and the row says which happened. It only rejects when the
 * server refuses the action itself -- a snooze limit reached, a dose that is
 * no longer scheduled -- because retrying those later changes nothing.
 */
export async function submitOrQueueAction(
  profileId: string,
  doseId: string,
  input: DoseActionInput
): Promise<ActionOutcome> {
  const entry: PendingDoseAction = {
    ...input,
    doseId,
    actionAt: input.actionAt ?? new Date().toISOString(),
  };

  try {
    const result = await submitDoseAction(profileId, doseId, entry);
    await clearPendingAction(doseId);
    return { result, status: 'synced' };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    await queueAction(entry);
    // The medication is not named: a log line says what happened, never what.
    log.warn('dose action saved on this device; will sync later');
    return { result: null, status: 'pending' };
  }
}

export interface SyncSummary {
  sent: number;
  /** Still waiting; those entries are kept. */
  pending: number;
  /** Could never succeed as written, and have been dropped. */
  discarded: number;
}

/**
 * Tries to send everything queued.
 *
 * Safe to call often: it does nothing when the queue is empty, and every
 * action is an idempotent state change on the server, so a duplicate send
 * leaves the same single dose (PRD 5, section 48).
 */
export async function syncPendingActions(profileId: string): Promise<SyncSummary> {
  const entries = await loadPendingActions();
  if (entries.length === 0) return { sent: 0, pending: 0, discarded: 0 };

  const keep: PendingDoseAction[] = [];
  let sent = 0;
  let discarded = 0;

  for (const entry of entries) {
    try {
      await submitDoseAction(profileId, entry.doseId, entry);
      sent += 1;
    } catch (error) {
      if (isRetryable(error)) {
        keep.push(entry);
      } else {
        // The server refused it outright -- most often a dose that no longer
        // exists, or a snooze the rules will not allow. Keeping it would mean
        // retrying forever.
        discarded += 1;
      }
    }
  }

  await writeAll(keep);
  if (sent > 0 || discarded > 0) {
    log.info('queued dose actions synced', { sent, discarded });
  }
  return { sent, pending: keep.length, discarded };
}

/**
 * Applies whatever is queued on top of the server's doses, so a pending
 * action shows immediately rather than reverting on the next refresh.
 *
 * Only the fields the user can actually have changed are overlaid, and each
 * one is flagged `pending` so the row can say it has not synced yet.
 */
export function withPendingActions<
  Dose extends {
    id: string;
    status: string;
    actionAt: string | null;
    skipReasonCode: unknown;
    skipReasonText: string | null;
    syncStatus?: 'synced' | 'pending';
  },
>(doses: Dose[], pending: PendingDoseAction[]): Dose[] {
  if (pending.length === 0) return doses;
  const byDose = new Map(pending.map((entry) => [entry.doseId, entry]));

  return doses.map((dose) => {
    const entry = byDose.get(dose.id);
    if (entry === undefined) return dose;
    if (entry.action === 'snooze') {
      return { ...dose, status: 'snoozed', syncStatus: 'pending' as const };
    }
    return {
      ...dose,
      status: entry.action === 'taken' ? 'taken' : 'skipped',
      actionAt: entry.actionAt,
      skipReasonCode: entry.action === 'skip' ? (entry.reasonCode ?? 'none') : null,
      skipReasonText: entry.action === 'skip' ? (entry.reasonText ?? null) : null,
      syncStatus: 'pending' as const,
    };
  });
}
