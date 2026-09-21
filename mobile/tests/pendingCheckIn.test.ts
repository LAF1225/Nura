/**
 * The offline check-in queue (PRD 3, sections 26-28, 63 and 64).
 *
 * The promise under test: a user who answers with no signal does not lose that
 * answer, sees that it is unsent, and has it sent when the connection returns.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ApiError } from '../src/services/api/errors';
import {
  clearPendingCheckIn,
  loadPendingCheckIn,
  submitOrQueue,
  syncPendingCheckIn,
} from '../src/services/checkins/pendingCheckIn';

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function storedCheckIn(level: string, note: string | null = null) {
  return {
    checkin: {
      id: 'checkin-1',
      profile_id: 'profile-1',
      checkin_date: '2026-09-21',
      wellbeing_level: level,
      note,
      created_at: '2026-09-21T08:00:00Z',
      updated_at: '2026-09-21T08:00:00Z',
    },
    applied: true,
  };
}

const originalFetch = globalThis.fetch;

beforeEach(async () => {
  await AsyncStorage.clear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe('submitOrQueue', () => {
  it('sends the check-in and keeps nothing queued when online', async () => {
    globalThis.fetch = (async () =>
      jsonResponse(storedCheckIn('good'))) as unknown as typeof fetch;

    const outcome = await submitOrQueue({
      localDate: '2026-09-21',
      wellbeingLevel: 'good',
      note: null,
    });

    expect(outcome.status).toBe('synced');
    expect(outcome.checkIn.wellbeingLevel).toBe('good');
    await expect(loadPendingCheckIn()).resolves.toBeNull();
  });

  it('keeps the answer on the phone when there is no connection', async () => {
    globalThis.fetch = (async () => {
      throw new Error('no network');
    }) as unknown as typeof fetch;

    const outcome = await submitOrQueue({
      localDate: '2026-09-21',
      wellbeingLevel: 'not_great',
      note: 'Feeling tired today.',
    });

    // Not an error from the user's point of view: their answer is saved.
    expect(outcome.status).toBe('pending');
    expect(outcome.checkIn.syncStatus).toBe('pending');

    const queued = await loadPendingCheckIn();
    expect(queued).toMatchObject({
      localDate: '2026-09-21',
      wellbeingLevel: 'not_great',
      note: 'Feeling tired today.',
    });
    expect(typeof queued?.clientUpdatedAt).toBe('string');
  });

  it('does not queue an answer the server refused outright', async () => {
    // A rejected value would fail identically on every retry, so queueing it
    // would be a queue that never drains.
    globalThis.fetch = (async () =>
      jsonResponse(
        { detail: { code: 'local_date_out_of_range' } },
        422
      )) as unknown as typeof fetch;

    await expect(
      submitOrQueue({ localDate: '2020-01-01', wellbeingLevel: 'good', note: null })
    ).rejects.toBeInstanceOf(ApiError);
    await expect(loadPendingCheckIn()).resolves.toBeNull();
  });
});

describe('syncPendingCheckIn', () => {
  it('does nothing when the queue is empty', async () => {
    globalThis.fetch = (async () => {
      throw new Error('should not be called');
    }) as unknown as typeof fetch;

    await expect(syncPendingCheckIn()).resolves.toEqual({ status: 'idle' });
  });

  it('sends a queued answer once the connection returns, and clears it', async () => {
    globalThis.fetch = (async () => {
      throw new Error('no network');
    }) as unknown as typeof fetch;
    await submitOrQueue({
      localDate: '2026-09-21',
      wellbeingLevel: 'okay',
      note: null,
    });

    const requests: unknown[] = [];
    globalThis.fetch = (async (_url: string, init: RequestInit) => {
      requests.push(JSON.parse(String(init.body)));
      return jsonResponse(storedCheckIn('okay'));
    }) as unknown as typeof fetch;

    const result = await syncPendingCheckIn();
    expect(result.status).toBe('synced');
    await expect(loadPendingCheckIn()).resolves.toBeNull();
    // The moment the user chose it travels with the request, which is what
    // lets the server keep a newer answer (PRD 3, section 28).
    expect(requests[0]).toMatchObject({
      local_date: '2026-09-21',
      wellbeing_level: 'okay',
    });
    expect((requests[0] as Record<string, unknown>).client_updated_at).toEqual(
      expect.any(String)
    );
  });

  it('adopts the server answer when the server had a newer edit', async () => {
    globalThis.fetch = (async () => {
      throw new Error('no network');
    }) as unknown as typeof fetch;
    await submitOrQueue({ localDate: '2026-09-21', wellbeingLevel: 'good', note: null });

    globalThis.fetch = (async () =>
      jsonResponse({
        ...storedCheckIn('not_great'),
        applied: false,
      })) as unknown as typeof fetch;

    const result = await syncPendingCheckIn();
    expect(result).toMatchObject({ status: 'synced', applied: false });
    if (result.status === 'synced') {
      expect(result.checkIn.wellbeingLevel).toBe('not_great');
    }
    // Either way the queue drains: the two have converged.
    await expect(loadPendingCheckIn()).resolves.toBeNull();
  });

  it('keeps the entry while the phone is still offline', async () => {
    globalThis.fetch = (async () => {
      throw new Error('no network');
    }) as unknown as typeof fetch;
    await submitOrQueue({ localDate: '2026-09-21', wellbeingLevel: 'good', note: null });

    const result = await syncPendingCheckIn();
    expect(result.status).toBe('pending');
    await expect(loadPendingCheckIn()).resolves.not.toBeNull();
  });

  it('drops an entry the server will never accept', async () => {
    globalThis.fetch = (async () => {
      throw new Error('no network');
    }) as unknown as typeof fetch;
    await submitOrQueue({ localDate: '2026-09-21', wellbeingLevel: 'good', note: null });

    // The queued day is no longer anybody's today.
    globalThis.fetch = (async () =>
      jsonResponse(
        { detail: { code: 'local_date_out_of_range' } },
        422
      )) as unknown as typeof fetch;

    await expect(syncPendingCheckIn()).resolves.toEqual({ status: 'discarded' });
    await expect(loadPendingCheckIn()).resolves.toBeNull();
  });
});

describe('stored entries', () => {
  it('ignores a corrupted or outdated stored entry instead of crashing', async () => {
    await AsyncStorage.setItem('nura.checkin.pending', '{"not":"a check-in"}');
    await expect(loadPendingCheckIn()).resolves.toBeNull();

    await AsyncStorage.setItem('nura.checkin.pending', 'not json at all');
    await expect(loadPendingCheckIn()).resolves.toBeNull();
  });

  it('clears cleanly', async () => {
    globalThis.fetch = (async () => {
      throw new Error('no network');
    }) as unknown as typeof fetch;
    await submitOrQueue({ localDate: '2026-09-21', wellbeingLevel: 'good', note: null });

    await clearPendingCheckIn();
    await expect(loadPendingCheckIn()).resolves.toBeNull();
  });
});
