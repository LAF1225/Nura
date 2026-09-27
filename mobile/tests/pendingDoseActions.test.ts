/**
 * Dose actions taken offline (PRD 5, sections 62, 63 and 64).
 *
 * The promise being tested: **a medication action is never silently lost.**
 * If the phone cannot reach the backend, Taken, Snooze or Skip is written to
 * the device, the row says so, and it is sent when the connection returns.
 *
 * The second promise, just as important: a queued action cannot overwrite a
 * newer one, and an action the server would refuse forever is not retried
 * forever.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  clearAllPendingActions,
  loadPendingActions,
  queueAction,
  submitOrQueueAction,
  syncPendingActions,
  withPendingActions,
} from '../src/features/medications/pendingActions';
import type { PendingDoseAction } from '../src/features/medications/types';
import { ApiError } from '../src/services/api/errors';

// `jest.mock` is hoisted above every import, so this stub is in place before
// the module under test is loaded. Jest only lets a factory close over names
// prefixed `mock`, which is why this one is called `mockSubmit`.
const mockSubmit = jest.fn();

jest.mock('../src/features/medications/api', () => ({
  submitDoseAction: (...args: unknown[]) => mockSubmit(...args),
}));

const PROFILE = 'profile-1';

beforeEach(async () => {
  await AsyncStorage.clear();
  mockSubmit.mockReset();
});

function entry(overrides: Partial<PendingDoseAction> = {}): PendingDoseAction {
  return {
    doseId: 'dose-1',
    action: 'taken',
    actionAt: '2026-09-13T08:05:00Z',
    ...overrides,
  };
}

describe('submitOrQueueAction', () => {
  it('sends the action when the backend can be reached', async () => {
    mockSubmit.mockResolvedValue({ dose: { id: 'dose-1' }, applied: true });

    const outcome = await submitOrQueueAction(PROFILE, 'dose-1', { action: 'taken' });

    expect(outcome.status).toBe('synced');
    expect(outcome.result).not.toBeNull();
    await expect(loadPendingActions()).resolves.toEqual([]);
  });

  it('keeps the action on the phone when it cannot', async () => {
    mockSubmit.mockRejectedValue(new ApiError('offline', 'no network'));

    const outcome = await submitOrQueueAction(PROFILE, 'dose-1', { action: 'taken' });

    expect(outcome.status).toBe('pending');
    const queued = await loadPendingActions();
    expect(queued).toHaveLength(1);
    expect(queued[0]!.doseId).toBe('dose-1');
    // Stamped, so the conflict rule has something to compare later.
    expect(queued[0]!.actionAt).toEqual(expect.any(String));
  });

  it('does not queue something the server refused on its merits', async () => {
    // A snooze limit or a dose that is no longer scheduled would fail the same
    // way forever, so it is reported rather than retried (PRD 5, section 18).
    mockSubmit.mockRejectedValue(new ApiError('conflict', 'snooze limit reached'));

    await expect(
      submitOrQueueAction(PROFILE, 'dose-1', { action: 'snooze', minutes: 10 })
    ).rejects.toThrow();
    await expect(loadPendingActions()).resolves.toEqual([]);
  });

  it('keeps one answer per dose, not a log of taps', async () => {
    mockSubmit.mockRejectedValue(new ApiError('offline', 'no network'));

    await submitOrQueueAction(PROFILE, 'dose-1', { action: 'taken' });
    await submitOrQueueAction(PROFILE, 'dose-1', {
      action: 'skip',
      reasonCode: 'ran_out',
    });

    const queued = await loadPendingActions();
    expect(queued).toHaveLength(1);
    expect(queued[0]!.action).toBe('skip');
  });

  it('keeps separate answers for separate doses', async () => {
    mockSubmit.mockRejectedValue(new ApiError('offline', 'no network'));

    await submitOrQueueAction(PROFILE, 'dose-1', { action: 'taken' });
    await submitOrQueueAction(PROFILE, 'dose-2', { action: 'taken' });

    await expect(loadPendingActions()).resolves.toHaveLength(2);
  });
});

describe('syncPendingActions', () => {
  it('does nothing when there is nothing waiting', async () => {
    await expect(syncPendingActions(PROFILE)).resolves.toEqual({
      sent: 0,
      pending: 0,
      discarded: 0,
    });
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  it('sends what is queued and clears it', async () => {
    await queueAction(entry());
    mockSubmit.mockResolvedValue({ dose: { id: 'dose-1' }, applied: true });

    await expect(syncPendingActions(PROFILE)).resolves.toEqual({
      sent: 1,
      pending: 0,
      discarded: 0,
    });
    await expect(loadPendingActions()).resolves.toEqual([]);
  });

  it('sends the time the user acted, not the time it synced', async () => {
    await queueAction(entry({ actionAt: '2026-09-13T08:05:00Z' }));
    mockSubmit.mockResolvedValue({ dose: { id: 'dose-1' }, applied: true });

    await syncPendingActions(PROFILE);

    // This is what lets the server keep a newer answer made elsewhere
    // (PRD 5, section 63).
    expect(mockSubmit).toHaveBeenCalledWith(
      PROFILE,
      'dose-1',
      expect.objectContaining({ actionAt: '2026-09-13T08:05:00Z' })
    );
  });

  it('keeps an entry that is still unreachable', async () => {
    await queueAction(entry());
    mockSubmit.mockRejectedValue(new ApiError('offline', 'still no network'));

    await expect(syncPendingActions(PROFILE)).resolves.toMatchObject({ pending: 1 });
    await expect(loadPendingActions()).resolves.toHaveLength(1);
  });

  it('drops one the server will never accept', async () => {
    await queueAction(entry());
    mockSubmit.mockRejectedValue(new ApiError('notFound', 'that dose is gone'));

    await expect(syncPendingActions(PROFILE)).resolves.toMatchObject({ discarded: 1 });
    await expect(loadPendingActions()).resolves.toEqual([]);
  });

  it('sends what it can and keeps the rest', async () => {
    await queueAction(entry({ doseId: 'dose-1' }));
    await queueAction(entry({ doseId: 'dose-2' }));
    mockSubmit
      .mockResolvedValueOnce({ dose: { id: 'dose-1' }, applied: true })
      .mockRejectedValueOnce(new ApiError('timeout', 'slow'));

    await expect(syncPendingActions(PROFILE)).resolves.toEqual({
      sent: 1,
      pending: 1,
      discarded: 0,
    });
    const left = await loadPendingActions();
    expect(left.map((item) => item.doseId)).toEqual(['dose-2']);
  });
});

describe('stored entries', () => {
  it('ignores anything it cannot recognise rather than crashing a screen', async () => {
    await AsyncStorage.setItem(
      'nura.medications.pendingActions',
      JSON.stringify([{ nonsense: true }, entry()])
    );
    await expect(loadPendingActions()).resolves.toHaveLength(1);
  });

  it('survives a corrupted value', async () => {
    await AsyncStorage.setItem('nura.medications.pendingActions', 'not json');
    await expect(loadPendingActions()).resolves.toEqual([]);
  });

  it('stores a dose id and never a medication name', async () => {
    await queueAction(entry());
    const raw = await AsyncStorage.getItem('nura.medications.pendingActions');
    // PRD 5, section 64: only what is needed. A dose id means nothing on its
    // own, which is the point.
    expect(raw).not.toMatch(/metformin/i);
    expect(raw).toContain('dose-1');
  });

  it('clears everything on request', async () => {
    await queueAction(entry());
    await clearAllPendingActions();
    await expect(loadPendingActions()).resolves.toEqual([]);
  });
});

describe('withPendingActions', () => {
  const doses = [
    {
      id: 'dose-1',
      status: 'scheduled',
      actionAt: null,
      skipReasonCode: null,
      skipReasonText: null,
    },
    {
      id: 'dose-2',
      status: 'scheduled',
      actionAt: null,
      skipReasonCode: null,
      skipReasonText: null,
    },
  ];

  it('shows a queued answer straight away, flagged as unsynced', () => {
    const overlaid = withPendingActions(doses, [entry({ doseId: 'dose-1' })]);

    expect(overlaid[0]).toMatchObject({
      status: 'taken',
      actionAt: '2026-09-13T08:05:00Z',
      syncStatus: 'pending',
    });
    // Nothing else is touched.
    expect(overlaid[1]).toEqual(doses[1]);
  });

  it('carries a queued skip reason', () => {
    const overlaid = withPendingActions(doses, [
      entry({ action: 'skip', reasonCode: 'ran_out', reasonText: 'Pharmacy shut' }),
    ]);

    expect(overlaid[0]).toMatchObject({
      status: 'skipped',
      skipReasonCode: 'ran_out',
      skipReasonText: 'Pharmacy shut',
    });
  });

  it('leaves a queued snooze unrecorded', () => {
    const overlaid = withPendingActions(doses, [
      entry({ action: 'snooze', minutes: 10 }),
    ]);

    expect(overlaid[0]).toMatchObject({ status: 'snoozed', syncStatus: 'pending' });
    // A snooze is not an answer, so nothing is recorded against the dose.
    expect(overlaid[0]!.actionAt).toBeNull();
  });

  it('returns the doses untouched when nothing is queued', () => {
    expect(withPendingActions(doses, [])).toBe(doses);
  });
});
