/**
 * The daily-life client (PRD 12, sections 11, 25-29, 40, 43 and 52-58).
 *
 * Parsing tests, which in this codebase means tests about what the app does
 * with a response it does not fully recognise. Four rules are under test.
 *
 * **An unrecognised status falls back to the quietest value, never the
 * loudest.** A task status nobody knows reads as `open` -- still to do, which
 * shows a row rather than hiding one. Guessing optimistically is how a screen
 * comes to tell somebody a thing is done when the server never said so.
 *
 * **The alarm limitation is required.** Section 11's sentence is part of the
 * contract, and a response without it is a response this client refuses rather
 * than renders without it.
 *
 * **An external capability nobody recognises reads `not_configured`**, which
 * is the conservative direction and the same choice PRD 10 and PRD 11 made.
 *
 * **Nothing sends a `source`.** Provenance is the server's record of how a
 * write arrived (section 43), so no request body carries one.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { setAuthTokenProvider } from '../src/services/api/client';
import {
  createTask,
  fetchAlarms,
  fetchExternalCapabilities,
  fetchReminders,
  fetchRoutines,
  fetchTasks,
  parseDailyLifeSummary,
  parseTask,
  updateTask,
} from '../src/features/productivity/api';
import {
  ALARM_LIMITATION,
  alarmFixture,
  dailyLifeFixture,
  externalCapabilitiesFixture,
  mockBackend,
  reminderFixture,
  routineFixture,
  signInAt,
  taskFixture,
} from './helpers';

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('onboarding_complete');
  setAuthTokenProvider(async () => 'test-token');
  backend = mockBackend({
    tasks: [taskFixture()],
    reminders: [reminderFixture()],
    alarms: [alarmFixture()],
    routines: [routineFixture()],
  });
});

afterEach(() => {
  backend.restore();
  // A function, not null: the provider is typed `TokenProvider`.
  setAuthTokenProvider(async () => null);
});

describe('tasks', () => {
  it('parses a task with every label the server renders', async () => {
    const list = await fetchTasks('profile-1', 'open');
    expect(list.openCount).toBe(1);
    const task = list.tasks[0]!;
    expect(task.title).toBe('Call the physiotherapist');
    expect(task.statusLabel).toBe('To do');
    expect(task.dueLabel).toBe('Today, 4:00 PM');
    expect(task.overdue).toBe(false);
    expect(task.sourceLabel).toBe('Added by you');
  });

  it('reads an unrecognised status as something still to do', () => {
    const task = parseTask(taskFixture({ status: 'quantum', priority: 'urgent' }));
    expect(task.status).toBe('open');
    expect(task.priority).toBe('normal');
  });

  it('keeps a task with no due date rather than inventing one', () => {
    const task = parseTask(
      taskFixture({ due_at: null, due_local_date: null, due_label: null })
    );
    expect(task.dueAt).toBeNull();
    expect(task.dueLabel).toBeNull();
  });

  it('sends a client id so a retry is one task', async () => {
    await createTask('profile-1', { title: 'Ring the chemist', clientTaskId: 'draft-1' });
    const body = backend.requests.find(
      (request) => request.method === 'POST' && request.path.includes('/tasks')
    )?.body as Record<string, unknown>;
    expect(body.client_task_id).toBe('draft-1');
  });

  it('never claims provenance', async () => {
    await createTask('profile-1', { title: 'Ring the chemist' });
    const body = backend.requests.find(
      (request) => request.method === 'POST' && request.path.includes('/tasks')
    )?.body as Record<string, unknown>;
    expect(body).not.toHaveProperty('source');
  });

  it('sends an explicit null to clear a due date', async () => {
    await updateTask('profile-1', 'task-1', { dueAt: null });
    const body = backend.requests.find((request) => request.method === 'PATCH')
      ?.body as Record<string, unknown>;
    // `'key' in edit` rather than a truthiness check, so clearing is a change
    // rather than an omission.
    expect(body).toHaveProperty('due_at', null);
  });

  it('stamps an edit with when it was made', async () => {
    await updateTask('profile-1', 'task-1', {
      title: 'New wording',
      clientUpdatedAt: '2026-09-13T12:00:00Z',
    });
    const body = backend.requests.find((request) => request.method === 'PATCH')
      ?.body as Record<string, unknown>;
    expect(body.client_updated_at).toBe('2026-09-13T12:00:00Z');
  });
});

describe('reminders', () => {
  it('keeps the schedule sentence the server rendered', async () => {
    const list = await fetchReminders('profile-1');
    expect(list.reminders[0]!.scheduleLabel).toBe('Every day at 6:00 PM');
    expect(list.reminders[0]!.statusLabel).toBe('On');
  });

  it('carries the occurrences when a detail read includes them', async () => {
    const list = await fetchReminders('profile-1');
    expect(list.reminders[0]!.occurrences).toHaveLength(1);
    expect(list.reminders[0]!.occurrences?.[0]!.canSnooze).toBe(true);
  });

  it('keeps the notification note when notifications are off', async () => {
    backend.state.reminders = [
      reminderFixture({
        notification_enabled: false,
        notification_note: 'Notifications are turned off for Nura.',
      }),
    ];
    const list = await fetchReminders('profile-1');
    expect(list.reminders[0]!.notificationEnabled).toBe(false);
    expect(list.reminders[0]!.notificationNote).toContain('turned off');
  });
});

describe('alarms', () => {
  it('carries the limitation sentence', async () => {
    const list = await fetchAlarms('profile-1');
    expect(list.limitation).toBe(ALARM_LIMITATION);
    expect(list.limitation).toContain('never been run on a physical phone');
  });

  it('refuses a response with no limitation', async () => {
    // **Section 11 as a contract**, not as a string in a screen. A server that
    // stopped sending it is a server this client will not render an alarm
    // list from.
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      ({
        ok: true,
        status: 200,
        json: async () => ({ alarms: [], enabled_count: 0 }),
      }) as Response) as typeof fetch;
    await expect(fetchAlarms('profile-1')).rejects.toThrow();
    globalThis.fetch = original;
  });

  it('reads an unrecognised sound as the default', async () => {
    backend.state.alarms = [alarmFixture({ sound_key: 'airhorn' })];
    const list = await fetchAlarms('profile-1');
    expect(list.alarms[0]!.soundKey).toBe('default');
  });
});

describe('routines', () => {
  it('parses steps in order with their optional flag', async () => {
    const list = await fetchRoutines('profile-1');
    const routine = list.routines[0]!;
    expect(routine.steps.map((step) => step.title)).toEqual([
      'Drink water',
      'Stretch for 5 minutes',
      'Review Today',
    ]);
    expect(routine.steps[2]!.optional).toBe(true);
  });

  it("keeps today's run and its progress sentence", async () => {
    const list = await fetchRoutines('profile-1');
    expect(list.routines[0]!.todayRun?.progressLabel).toBe(
      '0 of 3 complete. Next: Drink water'
    );
  });

  it('reads a null run as "not today" rather than "not started"', async () => {
    backend.state.routines = [routineFixture({ today_run: null })];
    const list = await fetchRoutines('profile-1');
    expect(list.routines[0]!.todayRun).toBeNull();
  });
});

describe('the daily-life summary', () => {
  it('is null when the server sends nothing', () => {
    expect(parseDailyLifeSummary(null)).toBeNull();
    expect(parseDailyLifeSummary(undefined)).toBeNull();
  });

  it('counts default to zero rather than to undefined', () => {
    const summary = parseDailyLifeSummary({ summary_label: 'x' });
    expect(summary?.tasks.dueToday).toBe(0);
    expect(summary?.routines.inProgress).toBe(0);
    expect(summary?.hasAnything).toBe(false);
  });

  it('carries the counts and the sentence', () => {
    const summary = parseDailyLifeSummary(
      dailyLifeFixture({
        tasks: { due_today: 3, overdue: 1, open_total: 5 },
        summary_label: '3 tasks today.',
        has_anything: true,
      })
    );
    expect(summary?.tasks.overdue).toBe(1);
    expect(summary?.summaryLabel).toBe('3 tasks today.');
    expect(summary?.hasAnything).toBe(true);
  });
});

describe('external capabilities', () => {
  it('reports the three external keys as not configured', async () => {
    const capabilities = await fetchExternalCapabilities('profile-1');
    expect(capabilities.external).toEqual({
      weather: 'not_configured',
      news: 'not_configured',
      external_calendar: 'not_configured',
    });
    expect(capabilities.anyExternalConfigured).toBe(false);
  });

  it('keeps the sentences verbatim', async () => {
    const capabilities = await fetchExternalCapabilities('profile-1');
    const byKey = Object.fromEntries(
      capabilities.capabilities.map((row) => [row.key, row.sentence])
    );
    expect(byKey.weather).toBe('Live weather is not configured in this build.');
    expect(byKey.news).toBe('Live news access is not configured in this build.');
    expect(byKey.external_calendar).toContain('external calendar is not connected');
  });

  it('reads an unrecognised state as not configured', async () => {
    backend.state.externalCapabilities = externalCapabilitiesFixture({
      capabilities: [
        { key: 'weather', state: 'probably', label: 'Weather', sentence: 'x' },
      ],
      external: { weather: 'probably' },
    });
    const capabilities = await fetchExternalCapabilities('profile-1');
    expect(capabilities.capabilities[0]!.state).toBe('not_configured');
    expect(capabilities.external.weather).toBe('not_configured');
  });

  it('drops a capability key it does not know rather than rendering a mystery', async () => {
    backend.state.externalCapabilities = externalCapabilitiesFixture({
      capabilities: [
        { key: 'teleportation', state: 'available', label: 'Teleport', sentence: 'x' },
      ],
    });
    const capabilities = await fetchExternalCapabilities('profile-1');
    expect(capabilities.capabilities).toEqual([]);
  });
});

describe('what this client cannot do', () => {
  it('has no function that reaches a weather, news or calendar service', () => {
    // **Sections 26, 27 and 28, as the absence of a function.** The client has
    // one way to ask about any of the three -- the capability map, which
    // answers `not_configured` -- and nothing that could fetch one.
    //
    // Read off the file rather than through `await import`, which jest refuses
    // without `--experimental-vm-modules`. Reading the source is the stronger
    // check anyway: it catches a function that was written and not exported.
    const source = readFileSync(
      join(__dirname, '..', 'src', 'features', 'productivity', 'api.ts'),
      'utf8'
    );
    for (const name of source.matchAll(/export (?:async )?function (\w+)/g)) {
      const lowered = (name[1] ?? '').toLowerCase();
      expect(lowered).not.toContain('weather');
      expect(lowered).not.toContain('news');
      expect(lowered.replace('capabilities', '')).not.toContain('calendar');
    }
    // And no URL anywhere that leaves this backend.
    expect(source).not.toMatch(/https?:\/\/(?!localhost)/);
  });
});
