/**
 * Symptom entries saved while offline (PRD 6, sections 59, 60 and 61).
 *
 * The rule this exists to keep: **a symptom description is never silently
 * lost.** If the phone cannot reach the backend, the whole thing -- the episode
 * it would create, the observation, and the local photos still to upload -- is
 * written to the device and the row says so, rather than a spinner that ends in
 * nothing (PRD 6, section 59).
 *
 * Three decisions worth reading.
 *
 * **One pending record is one save.** It carries the episode body (for a new
 * symptom) or an episode id (for a follow-up), the entry, and the photos. Keyed
 * by `clientEntryId`, so pressing Save twice replaces rather than duplicates.
 *
 * **The server enforces the idempotency, not this queue.** Every retry sends the
 * same `clientEntryId`, and the backend answers a replay with the entry it
 * already stored (PRD 6, section 61). That is why a send that fails *after* the
 * server accepted it -- a dropped response -- still converges on one record.
 *
 * **A photo is not reported as uploaded until the backend says so**
 * (PRD 6, section 60). Photos are uploaded one at a time after the entry lands,
 * and any that fail stay in the record with their local URI so a later attempt
 * can finish the job.
 *
 * Where it is stored: AsyncStorage, in the app's private data directory. Not
 * secure storage -- that is for credentials. It does hold symptom text, which is
 * unavoidable for an offline draft and is why nothing here is ever logged
 * (PRD 6, section 62).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { isApiError, type ApiErrorKind } from '../../services/api/errors';
import { createLogger } from '../../utils/logger';
import { createEntry, createEpisode, recordRecurrence, uploadPhoto } from './api';
import type { PendingSymptomEntry } from './types';

const log = createLogger('symptoms');

const STORAGE_KEY = 'nura.symptoms.pendingEntries';

/**
 * Failures worth keeping the record for. Everything else means the request would
 * fail the same way forever, so holding on would be a queue that retries and
 * never drains.
 *
 * `unauthorized` is retryable on purpose: the user can sign in again, and their
 * description of a symptom should survive that.
 */
const RETRYABLE: readonly ApiErrorKind[] = [
  'offline',
  'unavailable',
  'timeout',
  'server',
  'unauthorized',
  'configuration',
  'unknown',
];

function isRetryable(error: unknown): boolean {
  return isApiError(error) && RETRYABLE.includes(error.kind);
}

function isPending(value: unknown): value is PendingSymptomEntry {
  if (value === null || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.clientEntryId === 'string' &&
    typeof record.savedAt === 'string' &&
    typeof record.entry === 'object' &&
    record.entry !== null
  );
}

export async function loadPendingEntries(): Promise<PendingSymptomEntry[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Records from an older build, or corrupted ones, are dropped rather than
    // allowed to crash the screen that lists them.
    return parsed.filter(isPending);
  } catch {
    return [];
  }
}

async function writeAll(records: PendingSymptomEntry[]): Promise<void> {
  if (records.length === 0) {
    await AsyncStorage.removeItem(STORAGE_KEY);
    return;
  }
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(records));
}

/** Replaces any record with the same client id. One record per save. */
export async function queueEntry(record: PendingSymptomEntry): Promise<void> {
  const existing = await loadPendingEntries();
  await writeAll([
    ...existing.filter((item) => item.clientEntryId !== record.clientEntryId),
    record,
  ]);
}

export async function clearPendingEntry(clientEntryId: string): Promise<void> {
  const existing = await loadPendingEntries();
  await writeAll(existing.filter((item) => item.clientEntryId !== clientEntryId));
}

export async function clearAllPendingEntries(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
}

/** Pending records for one episode, for the detail screen's list. */
export function pendingForEpisode(
  records: PendingSymptomEntry[],
  episodeId: string
): PendingSymptomEntry[] {
  return records.filter((record) => record.episodeId === episodeId);
}

export interface SaveOutcome {
  /** The episode the entry ended up on, when the save reached the server. */
  episodeId: string | null;
  /** `pending` means it is on this phone and not yet on the server. */
  status: 'synced' | 'pending';
  /** Photos that reached the backend. */
  photosUploaded: number;
  /** Photos still waiting, which the row reports as pending upload (s60). */
  photosPending: number;
  /** The safety notice the server returned, when there was one. */
  notice: string | null;
}

/**
 * Uploads a record's photos, returning the ones that did not make it.
 *
 * One at a time rather than in parallel: a handful of photos over a poor
 * connection is exactly the case where six simultaneous uploads all time out.
 * Each carries its own `clientPhotoId`, so a retry of one that already landed
 * returns the stored photo instead of adding a second (PRD 6, section 61).
 */
async function uploadPhotos(
  profileId: string,
  episodeId: string,
  entryId: string,
  record: PendingSymptomEntry
): Promise<{ uploaded: number; remaining: PendingSymptomEntry['photos'] }> {
  const remaining: PendingSymptomEntry['photos'] = [];
  let uploaded = 0;

  for (const photo of record.photos) {
    try {
      await uploadPhoto(profileId, episodeId, entryId, photo);
      uploaded += 1;
    } catch (error) {
      if (isRetryable(error)) {
        remaining.push(photo);
      } else {
        // The server refused the file itself -- too large, or not an image.
        // Keeping it would mean retrying forever, so it is dropped and the
        // description it belonged to is kept.
        log.warn('a symptom photo was refused and will not be retried');
      }
    }
  }
  return { uploaded, remaining };
}

/**
 * Saves a symptom, or keeps it on the phone if that is not possible.
 *
 * Resolves either way: "saved on this phone" is a success from the user's point
 * of view, and the screen says which happened. It rejects only when the server
 * refuses the description itself, which is a rule the user needs to hear about
 * rather than a failure to retry.
 */
export async function submitOrQueueEntry(
  profileId: string,
  record: PendingSymptomEntry
): Promise<SaveOutcome> {
  try {
    let episodeId = record.episodeId;
    let entryId: string;
    let notice: string | null = null;

    if (episodeId === undefined) {
      if (record.episode === undefined) {
        throw new Error('a pending symptom must carry an episode or an episode id');
      }
      // A recurrence is still a new episode, but a *linked* one. Sending it
      // through the recurrence route keeps the chain back to the earlier bout
      // even when the save happened hours earlier, offline
      // (PRD 6, section 38).
      const episode =
        record.recurOf === undefined
          ? await createEpisode(profileId, record.episode)
          : await recordRecurrence(profileId, record.recurOf, record.episode);
      episodeId = episode.id;
      entryId = episode.latestEntry?.id ?? '';
      notice = episode.safety.notice;
    } else {
      const saved = await createEntry(profileId, episodeId, record.entry);
      entryId = saved.entry.id;
      notice = saved.safety.notice;
    }

    const photos =
      entryId.length > 0 && record.photos.length > 0
        ? await uploadPhotos(profileId, episodeId, entryId, record)
        : { uploaded: 0, remaining: record.photos };

    if (photos.remaining.length > 0) {
      // The description is safely stored; only some photos are outstanding. The
      // record is kept with the episode and entry now known, so the retry
      // uploads rather than re-creating anything.
      await queueEntry({
        ...record,
        episodeId,
        episode: undefined,
        recurOf: undefined,
        photos: photos.remaining,
      });
      return {
        episodeId,
        status: 'pending',
        photosUploaded: photos.uploaded,
        photosPending: photos.remaining.length,
        notice,
      };
    }

    await clearPendingEntry(record.clientEntryId);
    return {
      episodeId,
      status: 'synced',
      photosUploaded: photos.uploaded,
      photosPending: 0,
      notice,
    };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    await queueEntry(record);
    // Nothing about the symptom is logged -- a line says what happened, never
    // what it was about (PRD 6, sections 62 and 65).
    log.warn('symptom saved on this device; will sync later');
    return {
      episodeId: record.episodeId ?? null,
      status: 'pending',
      photosUploaded: 0,
      photosPending: record.photos.length,
      notice: null,
    };
  }
}

export interface SyncSummary {
  sent: number;
  /** Still waiting; those records are kept. */
  pending: number;
  /** Could never succeed as written, and have been dropped. */
  discarded: number;
}

/**
 * Tries to send everything queued.
 *
 * Safe to call often: it does nothing when the queue is empty, and every send is
 * idempotent on the server, so a duplicate attempt leaves the same single entry
 * (PRD 6, section 61).
 */
export async function syncPendingEntries(profileId: string): Promise<SyncSummary> {
  const records = await loadPendingEntries();
  if (records.length === 0) return { sent: 0, pending: 0, discarded: 0 };

  let sent = 0;
  let discarded = 0;
  let pending = 0;

  for (const record of records) {
    try {
      const outcome = await submitOrQueueEntry(profileId, record);
      if (outcome.status === 'synced') sent += 1;
      else pending += 1;
    } catch {
      // The server refused the description outright. Keeping it would mean
      // retrying forever.
      await clearPendingEntry(record.clientEntryId);
      discarded += 1;
    }
  }

  if (sent > 0 || discarded > 0) {
    log.info('queued symptoms synced', { sent, discarded });
  }
  return { sent, pending, discarded };
}
