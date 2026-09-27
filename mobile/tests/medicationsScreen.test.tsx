/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The medication management screen (PRD 5, sections 5, 7, 24, 27 and 57).
 *
 * Mounted at `/medications` through the real router, so this is the screen a
 * user gets: today's doses with their three actions, what has already been
 * recorded, the adherence sentence, and the ways into schedules, supply and
 * history.
 *
 * Also the place the copy rules are checked on a real screen rather than on a
 * function: no guilt wording for an unrecorded dose, and exactly one sentence
 * that comes near advice -- the one pointing at a clinician.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { doseFixture, mockBackend, scheduleFixture, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.mock('expo-notifications', () => ({
  SchedulableTriggerInputTypes: { DATE: 'date' },
  AndroidImportance: { HIGH: 4 },
  getPermissionsAsync: async () => ({ granted: true, canAskAgain: true }),
  requestPermissionsAsync: async () => ({ granted: true }),
  setNotificationChannelAsync: async () => undefined,
  scheduleNotificationAsync: async () => 'notification-1',
  cancelScheduledNotificationAsync: async () => undefined,
}));

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    schedules: [scheduleFixture()],
    doses: [
      // Waiting, and past its grace period.
      doseFixture({ id: 'dose-1', window: 'overdue' }),
      // Already recorded, and recorded without being taken.
      doseFixture({
        id: 'dose-2',
        scheduled_for: '2026-09-13T20:00:00Z',
        status: 'skipped',
        window: 'completed',
        skip_reason_code: 'ran_out',
        action_at: '2026-09-13T20:05:00Z',
        can_snooze: false,
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('shows today’s doses, what was recorded, and the way into everything else', async () => {
  renderRouter('app', { initialUrl: '/medications' });

  await waitFor(
    () => {
      expect(screen.getByText('Metformin — 500 mg')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The waiting dose has all three actions, each labelled in words.
  for (const label of ['Taken', 'Snooze', 'Skip']) {
    expect(screen.getByRole('button', { name: label })).toBeTruthy();
  }

  // The recorded one is stated, not offered again, and the reason is shown
  // back exactly as it was chosen (PRD 5, section 19).
  expect(screen.getByText(/skipped — ran out/i)).toBeTruthy();

  // Nothing anywhere on the screen scolds about a dose (PRD 5, section 24).
  expect(screen.queryByText(/you missed|failed|forgot to|should have/i)).toBeNull();

  // Exactly one sentence that comes near advice, and it points at a person
  // rather than giving any (PRD 5, section 57).
  expect(
    screen.getAllByText(/follow the instructions from your clinician or pharmacist/i)
  ).toHaveLength(1);

  // The three ways further in (PRD 5, section 7).
  expect(screen.getByText('Reminder schedules')).toBeTruthy();
  expect(screen.getByText('Supply and refills')).toBeTruthy();
  expect(screen.getByText('History')).toBeTruthy();
  // One schedule exists, and the row says so rather than making it a badge.
  expect(screen.getByText('1 schedule')).toBeTruthy();

  // --- record the waiting dose, on the same mounted screen ---
  fireEvent.press(screen.getByRole('button', { name: 'Taken' }));

  await waitFor(() => {
    expect(
      backend.requests.some(
        (request) =>
          request.path.endsWith('/medication-doses/dose-1/taken') &&
          request.method === 'POST'
      )
    ).toBe(true);
  });

  // And the screen reflects it, because the dose came back taken.
  await waitFor(() => {
    expect(screen.queryByRole('button', { name: 'Taken' })).toBeNull();
  });
});
