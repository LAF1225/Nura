/**
 * Symptoms saved while offline (PRD 6, sections 59, 60, 61 and 91).
 *
 * The rule under test is the one PRD 6 section 59 states plainly: **do not lose
 * symptom notes or photos because of temporary connectivity loss.** So the cases
 * here are the ones where something could be lost -- no signal at all, a signal
 * that comes back halfway through, a retry, and a photo that fails after the
 * description succeeded.
 *
 * Idempotency is the other half (section 61). Every send carries the client id the
 * draft was given before it was ever attempted, so a retry converges on one
 * record rather than producing a second.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { pendingRecordFor } from '../src/features/symptoms/hooks';
import { newDraft } from '../src/features/symptoms/draft';
import {
  clearAllPendingEntries,
  loadPendingEntries,
  pendingForEpisode,
  queueEntry,
  submitOrQueueEntry,
  syncPendingEntries,
} from '../src/features/symptoms/pendingEntries';
import { ApiError } from '../src/services/api/errors';
import type { LocalPhotoDraft, SymptomDraft } from '../src/features/symptoms/types';
import { mockBackend, symptomEpisodeFixture } from './helpers';

const STORAGE_KEY = 'nura.symptoms.pendingEntries';

const PHOTO: LocalPhotoDraft = {
  clientPhotoId: 'photo-aaaabbbb',
  localUri: 'file:///tmp/symptom.jpg',
  contentType: 'image/jpeg',
  byteSize: 2048,
};

function draftFor(overrides: Partial<SymptomDraft> = {}): SymptomDraft {
  return {
    ...newDraft({ mode: 'manual_app' }),
    mainSymptom: 'Headache',
    severity: 5,
    changeState: 'worsening',
    ...overrides,
  };
}

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await clearAllPendingEntries();
  backend = mockBackend({ symptoms: [symptomEpisodeFixture()] });
});

afterEach(() => {
  backend.restore();
});

describe('the queue', () => {
  it('holds one record per save', async () => {
    const record = pendingRecordFor(draftFor());
    await queueEntry(record);
    await queueEntry(record);

    expect(await loadPendingEntries()).toHaveLength(1);
  });

  it('keeps two different saves apart', async () => {
    await queueEntry(pendingRecordFor(draftFor()));
    await queueEntry(pendingRecordFor(draftFor({ mainSymptom: 'Knee pain' })));

    expect(await loadPendingEntries()).toHaveLength(2);
  });

  it('survives a restart, which is the whole point', async () => {
    await queueEntry(pendingRecordFor(draftFor({ note: 'a description worth keeping' })));

    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    expect(stored).toBeTruthy();
    expect(String(stored)).toContain('a description worth keeping');
  });

  it('drops a corrupt record rather than crashing the screen that lists it', async () => {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify([{ nonsense: true }, 42]));
    expect(await loadPendingEntries()).toEqual([]);
  });

  it('survives storage holding something that is not JSON', async () => {
    await AsyncStorage.setItem(STORAGE_KEY, 'not json at all');
    expect(await loadPendingEntries()).toEqual([]);
  });

  it('finds what is queued for one episode', async () => {
    const forEpisode = pendingRecordFor(draftFor({ episodeId: 'episode-1' }));
    const newSymptom = pendingRecordFor(draftFor());
    expect(pendingForEpisode([forEpisode, newSymptom], 'episode-1')).toEqual([
      forEpisode,
    ]);
  });
});

describe('building a record from a draft', () => {
  it('carries the episode body for a new symptom', () => {
    const record = pendingRecordFor(draftFor());
    expect(record.episodeId).toBeUndefined();
    expect(record.episode?.name).toBe('Headache');
    expect(record.displayName).toBe('Headache');
  });

  it('carries only the episode id for a follow-up', () => {
    const record = pendingRecordFor(draftFor({ episodeId: 'episode-1' }));
    expect(record.episodeId).toBe('episode-1');
    expect(record.episode).toBeUndefined();
  });

  it('remembers the bout a recurrence follows (PRD 6, section 38)', () => {
    const record = pendingRecordFor(draftFor(), { recurOf: 'episode-0' });
    expect(record.recurOf).toBe('episode-0');
  });

  it('carries the photos that still have to be uploaded', () => {
    const record = pendingRecordFor(draftFor({ photos: [PHOTO] }));
    expect(record.photos).toEqual([PHOTO]);
  });
});

describe('saving with a connection', () => {
  it('reaches the server and leaves nothing queued', async () => {
    const outcome = await submitOrQueueEntry('profile-1', pendingRecordFor(draftFor()));

    expect(outcome.status).toBe('synced');
    expect(outcome.episodeId).toBeTruthy();
    expect(await loadPendingEntries()).toEqual([]);
  });

  it('returns the server’s own safety notice for a follow-up', async () => {
    const outcome = await submitOrQueueEntry(
      'profile-1',
      pendingRecordFor(draftFor({ episodeId: 'episode-1' }))
    );
    expect(outcome.notice).toContain('worsening');
  });

  it('sends a recurrence through the recurrence route', async () => {
    await submitOrQueueEntry(
      'profile-1',
      pendingRecordFor(draftFor(), { recurOf: 'episode-1' })
    );

    expect(
      backend.requests.some(
        (request) => request.method === 'POST' && request.path.endsWith('/recur')
      )
    ).toBe(true);
  });

  it('uploads the photos after the description has landed', async () => {
    const outcome = await submitOrQueueEntry(
      'profile-1',
      pendingRecordFor(draftFor({ photos: [PHOTO] }))
    );

    expect(outcome.photosUploaded).toBe(1);
    expect(outcome.photosPending).toBe(0);
  });
});

describe('saving with no connection (PRD 6, section 59)', () => {
  function offline(): void {
    globalThis.fetch = (async () => {
      throw new ApiError('offline', 'no connection');
    }) as typeof fetch;
  }

  it('keeps the whole description on the phone and says so', async () => {
    offline();
    const outcome = await submitOrQueueEntry('profile-1', pendingRecordFor(draftFor()));

    expect(outcome.status).toBe('pending');
    expect(outcome.episodeId).toBeNull();

    const queued = await loadPendingEntries();
    expect(queued).toHaveLength(1);
    expect(queued[0]?.episode?.name).toBe('Headache');
  });

  it('keeps the photos, with their local files (PRD 6, section 60)', async () => {
    offline();
    const outcome = await submitOrQueueEntry(
      'profile-1',
      pendingRecordFor(draftFor({ photos: [PHOTO] }))
    );

    expect(outcome.photosPending).toBe(1);
    expect(outcome.photosUploaded).toBe(0);
    const queued = await loadPendingEntries();
    expect(queued[0]?.photos[0]?.localUri).toBe('file:///tmp/symptom.jpg');
  });

  it('sends nothing at all rather than reporting a success it did not have', async () => {
    offline();
    const outcome = await submitOrQueueEntry('profile-1', pendingRecordFor(draftFor()));
    expect(outcome.notice).toBeNull();
  });
});

describe('syncing when the connection returns', () => {
  it('sends what was queued and clears it', async () => {
    const record = pendingRecordFor(draftFor());
    await queueEntry(record);

    const summary = await syncPendingEntries('profile-1');
    expect(summary.sent).toBe(1);
    expect(await loadPendingEntries()).toEqual([]);
  });

  it('does nothing when there is nothing to send', async () => {
    expect(await syncPendingEntries('profile-1')).toEqual({
      sent: 0,
      pending: 0,
      discarded: 0,
    });
    expect(backend.requests).toHaveLength(0);
  });

  it('sends the same client id, so a retry cannot duplicate the record', async () => {
    const record = pendingRecordFor(draftFor());
    await queueEntry(record);
    await syncPendingEntries('profile-1');
    // Queue it again, exactly as an interrupted response would leave it.
    await queueEntry(record);
    await syncPendingEntries('profile-1');

    const sentIds = backend.requests
      .filter((request) => request.method === 'POST')
      .map(
        (request) =>
          (
            (request.body as Record<string, unknown>)?.first_entry as Record<
              string,
              unknown
            >
          )?.client_entry_id
      );
    expect(new Set(sentIds).size).toBe(1);
    expect(sentIds[0]).toBe(record.clientEntryId);
  });

  it('drops a record the server refuses outright, rather than retrying forever', async () => {
    await queueEntry(pendingRecordFor(draftFor()));
    globalThis.fetch = (async () => ({
      ok: false,
      status: 422,
      json: async () => ({ detail: { code: 'invalid' } }),
    })) as unknown as typeof fetch;

    const summary = await syncPendingEntries('profile-1');
    expect(summary.discarded).toBe(1);
    expect(await loadPendingEntries()).toEqual([]);
  });

  it('keeps a record when the failure is worth retrying', async () => {
    await queueEntry(pendingRecordFor(draftFor()));
    globalThis.fetch = (async () => {
      throw new ApiError('unavailable', 'backend down');
    }) as typeof fetch;

    const summary = await syncPendingEntries('profile-1');
    expect(summary.sent).toBe(0);
    expect(summary.pending).toBe(1);
    expect(await loadPendingEntries()).toHaveLength(1);
  });
});

describe('a photo that fails after the description succeeded', () => {
  it('keeps the photo queued against the entry it belongs to', async () => {
    let call = 0;
    const realFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      call += 1;
      if (String(input).includes('/photos')) {
        throw new ApiError('offline', 'no connection');
      }
      return realFetch(input, init);
    }) as typeof fetch;

    const outcome = await submitOrQueueEntry(
      'profile-1',
      pendingRecordFor(draftFor({ photos: [PHOTO] }))
    );

    expect(call).toBeGreaterThan(1);
    // The description is safely stored; only the photo is outstanding.
    expect(outcome.episodeId).toBeTruthy();
    expect(outcome.status).toBe('pending');
    expect(outcome.photosPending).toBe(1);

    const queued = await loadPendingEntries();
    // The retry now knows where the photo goes, so it uploads rather than
    // creating the episode a second time.
    expect(queued[0]?.episodeId).toBe(outcome.episodeId);
    expect(queued[0]?.episode).toBeUndefined();
    expect(queued[0]?.photos).toHaveLength(1);
  });
});
