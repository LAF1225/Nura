/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Today for somebody with no medication reminders (PRD 3, s18; PRD 5, s28).
 *
 * This is the state almost every account is in, including every account that
 * exists today, so it has to read as a finished screen rather than as a
 * feature waiting to be switched on.
 *
 * Two promises, and both are absences, which is why they get a test of their
 * own: **nothing is drawn** -- no empty medication card promising a feature
 * nobody has set up -- and **nothing is fetched**, so the people who will
 * never use reminders do not pay a request for them on every launch.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.mock('expo-notifications', () => ({
  SchedulableTriggerInputTypes: { DATE: 'date' },
  AndroidImportance: { HIGH: 4 },
  getPermissionsAsync: async () => ({ granted: false, canAskAgain: true }),
  requestPermissionsAsync: async () => ({ granted: false }),
  setNotificationChannelAsync: async () => undefined,
  scheduleNotificationAsync: async () => 'notification-1',
  cancelScheduledNotificationAsync: async () => undefined,
}));

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  // `todayMedications` defaults to the no-schedules block, which is what the
  // backend answers for anybody who has not set a reminder up.
  backend = mockBackend({
    status: 'ready_for_pairing',
    preferredName: 'Ada',
    todayDevice: null,
    checkIn: null,
  });
});

afterEach(() => {
  backend.restore();
});

it('draws no medication card and fetches no doses', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText('How are you feeling today?')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The card is registered, available and visible by default -- and still
  // draws nothing, because there is nothing to draw (PRD 3, section 18).
  expect(screen.queryByRole('button', { name: 'Taken' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Snooze' })).toBeNull();
  expect(screen.queryByText(/Medications/)).toBeNull();
  expect(screen.queryByText(/dose/i)).toBeNull();

  // Important Today stays as PRD 3 left it: good news, not "No data".
  expect(screen.getByText('Nothing needs your attention right now.')).toBeTruthy();

  // And nothing was fetched for a feature this account does not use.
  expect(backend.requests.some((request) => request.path.includes('/medication-'))).toBe(
    false
  );
});
