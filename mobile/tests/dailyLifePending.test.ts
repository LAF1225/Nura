/**
 * Daily-life writes made offline (PRD 12, sections 37, 38, 39 and 40).
 *
 * The rule under test is one sentence: **nothing the user did is silently
 * lost.** Four groups, and the two worth reading are the last.
 *
 * `syncing` proves the queues drain and that a retry is harmless, because the
 * server's idempotency is what makes it so -- a create carries its client id,
 * an action sets a state rather than appending an event, and a step completion
 * is unique per `(run, step)`.
 *
 * `giving up` proves a write the server refused outright is dropped rather
 * than retried forever. A queue that never drains is its own kind of silent
 * loss.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { setAuthTokenProvider } from '../src/services/api/client';
import {
  clearAllPendingDailyLife,
  clientId,
  completeStepOrQueue,
  createReminderOrQueue,
  createTaskOrQueue,
  isRetryable,
  loadPendingReminders,
  loadPendingSteps,
  loadPendingTaskActions,
  loadPendingTasks,
  submitTaskActionOrQueue,
  syncPendingDailyLife,
  withPendingTasks,
} from '../src/features/productivity/pending';
import { ApiError } from '../src/services/api/errors';
import { mockBackend, signInAt, taskFixture } from './helpers';

let backend: ReturnType<typeof mockBackend>;

/** Makes every request fail the way being offline does. */
function goOffline(): () => void {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => {
    throw new ApiError('offline', 'No connection.');
  }) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

/**
 * Makes every request fail the way a *refusal* does.
 *
 * A 422, not a thrown error: the client maps a thrown fetch failure to
 * `offline`, which is retryable, and the thing under test here is what happens
 * when the server answers and says no.
 */
function refuseEverything(): () => void {
  const original = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: false,
      status: 422,
      json: async () => ({ detail: { code: 'invalid_task', message: 'No.' } }),
    }) as Response) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
  setAuthTokenProvider(async () => 'test-token');
  backend = mockBackend({ tasks: [taskFixture()] });
});

afterEach(async () => {
  backend.restore();
  await clearAllPendingDailyLife();
  setAuthTokenProvider(async () => null);
});

describe('which failures are worth keeping', () => {
  it('keeps the ones that could succeed later', () => {
    for (const kind of ['offline', 'unavailable', 'timeout', 'server', 'unauthorized']) {
      expect(isRetryable(new ApiError(kind as 'offline', 'x'))).toBe(true);
    }
  });

  it('drops the ones that never will', () => {
    for (const kind of ['validation', 'notFound', 'conflict', 'forbidden']) {
      expect(isRetryable(new ApiError(kind as 'validation', 'x'))).toBe(false);
    }
  });
});

describe('creating offline', () => {
  it('keeps a task on the phone and says so (section 37)', async () => {
    const restore = goOffline();
    const outcome = await createTaskOrQueue('profile-1', {
      title: 'Ring the chemist',
    });
    restore();

    expect(outcome.status).toBe('pending');
    expect(outcome.result).toBeNull();
    const queued = await loadPendingTasks();
    expect(queued).toHaveLength(1);
    expect(queued[0]!.title).toBe('Ring the chemist');
    expect(queued[0]!.clientTaskId).toMatch(/^task-/);
  });

  it('keeps a reminder on the phone (section 38)', async () => {
    const restore = goOffline();
    await createReminderOrQueue('profile-1', {
      title: 'Ring the bank',
      timeOfDay: '18:00',
      startDate: '2026-09-13',
    });
    restore();

    const queued = await loadPendingReminders();
    expect(queued).toHaveLength(1);
    expect(queued[0]!.input.title).toBe('Ring the bank');
  });

  it('keeps a ticked step on the phone (section 39)', async () => {
    const restore = goOffline();
    await completeStepOrQueue('profile-1', 'run-1', 'step-1');
    restore();

    const queued = await loadPendingSteps();
    expect(queued).toHaveLength(1);
    expect(queued[0]!.runId).toBe('run-1');
    expect(queued[0]!.clientCompletionId).toMatch(/^step-/);
  });

  it('does not queue a write the server refused', async () => {
    const restore = refuseEverything();
    await expect(
      createTaskOrQueue('profile-1', { title: 'Ring the chemist' })
    ).rejects.toThrow();
    restore();
    expect(await loadPendingTasks()).toEqual([]);
  });
});

describe('actions offline', () => {
  it('queues one answer per task, not a log of them', async () => {
    const restore = goOffline();
    await submitTaskActionOrQueue('profile-1', 'task-1', 'complete');
    await submitTaskActionOrQueue('profile-1', 'task-1', 'archive');
    restore();

    const queued = await loadPendingTaskActions();
    expect(queued).toHaveLength(1);
    // The last thing the person decided is the thing they meant.
    expect(queued[0]!.action).toBe('archive');
  });

  it('stamps each one with when it was pressed (section 40)', async () => {
    const restore = goOffline();
    await submitTaskActionOrQueue('profile-1', 'task-1', 'complete');
    restore();
    const queued = await loadPendingTaskActions();
    expect(Date.parse(queued[0]!.clientUpdatedAt)).toBeGreaterThan(0);
  });

  it('clears the queue once the action goes through', async () => {
    const restore = goOffline();
    await submitTaskActionOrQueue('profile-1', 'task-1', 'complete');
    restore();

    await submitTaskActionOrQueue('profile-1', 'task-1', 'complete');
    expect(await loadPendingTaskActions()).toEqual([]);
  });
});

describe('showing a queued write immediately', () => {
  it('overlays the action so the row does not revert', () => {
    const tasks: { id: string; status: string; syncStatus?: 'synced' | 'pending' }[] = [
      { id: 'task-1', status: 'open' },
    ];
    const overlaid = withPendingTasks(tasks, [
      { taskId: 'task-1', action: 'complete', clientUpdatedAt: '2026-09-13T12:00:00Z' },
    ]);
    expect(overlaid[0]!.status).toBe('completed');
    expect(overlaid[0]!.syncStatus).toBe('pending');
  });

  it('leaves a task with nothing queued alone', () => {
    const tasks = [{ id: 'task-1', status: 'open' }];
    expect(withPendingTasks(tasks, [])).toBe(tasks);
  });
});

describe('syncing', () => {
  it('sends everything queued and empties the queues', async () => {
    const restore = goOffline();
    await createTaskOrQueue('profile-1', { title: 'Ring the chemist' });
    await createReminderOrQueue('profile-1', {
      title: 'Ring the bank',
      timeOfDay: '18:00',
      startDate: '2026-09-13',
    });
    await submitTaskActionOrQueue('profile-1', 'task-1', 'complete');
    await completeStepOrQueue('profile-1', 'run-1', 'step-1');
    restore();

    const summary = await syncPendingDailyLife('profile-1');
    expect(summary.sent).toBe(4);
    expect(summary.pending).toBe(0);
    expect(await loadPendingTasks()).toEqual([]);
    expect(await loadPendingReminders()).toEqual([]);
    expect(await loadPendingTaskActions()).toEqual([]);
    expect(await loadPendingSteps()).toEqual([]);
  });

  it('sends the same client id it queued, so a retry is one row', async () => {
    const restore = goOffline();
    await createTaskOrQueue('profile-1', {
      title: 'Ring the chemist',
      clientTaskId: 'draft-7',
    });
    restore();

    await syncPendingDailyLife('profile-1');
    const body = backend.requests.find(
      (request) => request.method === 'POST' && request.path.includes('/tasks')
    )?.body as Record<string, unknown>;
    expect(body.client_task_id).toBe('draft-7');
  });

  it('keeps what still cannot be sent', async () => {
    const restore = goOffline();
    await createTaskOrQueue('profile-1', { title: 'Ring the chemist' });
    const summary = await syncPendingDailyLife('profile-1');
    restore();

    expect(summary.sent).toBe(0);
    expect(summary.pending).toBe(1);
    expect(await loadPendingTasks()).toHaveLength(1);
  });

  it('does nothing when there is nothing queued', async () => {
    const summary = await syncPendingDailyLife('profile-1');
    expect(summary).toEqual({ sent: 0, pending: 0, discarded: 0 });
  });
});

describe('giving up', () => {
  it('drops a queued write the server refuses outright', async () => {
    const offline = goOffline();
    await createTaskOrQueue('profile-1', { title: 'Ring the chemist' });
    offline();

    const refuse = refuseEverything();
    const summary = await syncPendingDailyLife('profile-1');
    refuse();

    // A queue that retries forever is its own kind of silent loss.
    expect(summary.discarded).toBe(1);
    expect(await loadPendingTasks()).toEqual([]);
  });
});

describe('client ids', () => {
  it('are distinct and carry their prefix', () => {
    const ids = new Set(Array.from({ length: 50 }, () => clientId('task')));
    expect(ids.size).toBe(50);
    for (const id of ids) expect(id.startsWith('task-')).toBe(true);
  });
});
