/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Medication history (PRD 5, sections 24, 26 and 27).
 *
 * A record, not a report. This checks the three things that make it one: the
 * range filter PRD 5 section 26 asks for, one row per dose grouped by the
 * user's own day, and an adherence sentence that states its denominator
 * instead of presenting a bare figure.
 *
 * And the absence that matters: nothing on the screen scores a day, marks one
 * red, or says anything about what a person should have done.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { doseFixture, mockBackend, signInAt } from './helpers';

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
    doses: [
      doseFixture({
        id: 'dose-1',
        local_date: '2026-09-12',
        scheduled_for: '2026-09-12T08:00:00Z',
        status: 'taken',
        window: 'completed',
        action_at: '2026-09-12T08:10:00Z',
      }),
      doseFixture({
        id: 'dose-2',
        local_date: '2026-09-12',
        scheduled_for: '2026-09-12T20:00:00Z',
        status: 'missed',
        window: 'overdue',
      }),
      doseFixture({
        id: 'dose-3',
        local_date: '2026-09-13',
        scheduled_for: '2026-09-13T08:00:00Z',
        status: 'skipped',
        window: 'completed',
        skip_reason_code: 'clinician_advised',
        skip_reason_text: 'Asked to pause for a week',
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('lists what was recorded, with a range filter and a stated denominator', async () => {
  renderRouter('app', { initialUrl: '/medications/history' });

  await waitFor(
    () => {
      expect(screen.getByText(/of scheduled doses were marked taken/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The filter PRD 5 section 26 asks for.
  expect(screen.getByRole('button', { name: 'Last 7 days' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Last 30 days' })).toBeTruthy();

  // One taken, one skipped, one unrecorded -- so a third were taken, and the
  // counts behind that are on screen rather than just the percentage.
  expect(
    screen.getByText('33% of scheduled doses were marked taken in the last 7 days.')
  ).toBeTruthy();
  expect(screen.getByText(/1 taken · 1 skipped · 1 not marked/)).toBeTruthy();

  // Grouped by the user's own day. The heading is formatted for the reader's
  // locale, so it is matched loosely rather than pinning the suite to one.
  expect(screen.getByText(/^(13 September|September 13)$/)).toBeTruthy();
  expect(screen.getByText(/^(12 September|September 12)$/)).toBeTruthy();

  // Each status in its own words, and the skip reason and note shown back
  // exactly as they were given (PRD 5, section 19).
  expect(screen.getByText('Taken')).toBeTruthy();
  expect(screen.getByText('Wasn’t marked as taken')).toBeTruthy();
  expect(screen.getByText('Skipped — doctor advised')).toBeTruthy();
  expect(screen.getByText('Asked to pause for a week')).toBeTruthy();

  // Nothing grades a day or tells anybody what they should have done
  // (PRD 5, sections 24 and 57).
  expect(screen.queryByText(/good day|bad day|streak|well done|you should/i)).toBeNull();
});
