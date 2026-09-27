/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Today for somebody who has never logged a symptom (PRD 3 s18; PRD 6 s39).
 *
 * The card is on by default, and it draws **nothing at all** until the feature has
 * been used. Most people, most of the time, have no symptoms to report, and a
 * permanent "No active symptoms logged" panel would be a standing reminder of a
 * feature they are not using -- which is exactly what PRD 3 section 18 rules out.
 *
 * PRD 6 section 39's empty state is still implemented; it appears once somebody has
 * used the feature and everything they logged has ended, because from then on the
 * card is a way back in rather than an advertisement.
 *
 * The negative assertion is the point of this file: no symptom request is made for
 * a profile with nothing to show.
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
  // `todaySymptoms` defaults to NO_SYMPTOMS: nothing active, nothing ever logged.
  backend = mockBackend({ status: 'ready_for_pairing', todayDevice: null });
});

afterEach(() => {
  backend.restore();
});

it('draws no symptom card, and asks the server nothing about symptoms', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText(/Nothing needs your attention right now/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The card is not drawn -- not even as an empty one.
  expect(screen.queryByText('Symptoms')).toBeNull();
  expect(screen.queryByText(/No active symptoms logged/)).toBeNull();
  expect(screen.queryByRole('button', { name: 'Log a symptom' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Add an update' })).toBeNull();

  // And nothing was fetched for it: the Today response already said there is
  // nothing to show.
  expect(
    backend.requests.filter((request) => request.path.includes('/symptoms'))
  ).toHaveLength(0);
});
