/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Today symptoms card (PRD 6, sections 39, 40, 52 and 91).
 *
 * Today already carries the symptom block in its own response, so the card costs
 * no extra request (PRD 3, section 16). What this checks is what the card says and
 * -- as much -- what it does not: PRD 6 section 40 forbids labelling a symptom
 * urgent without a reviewed safety rule, and those rules are switched off
 * (section 44). So a symptom the user recorded as worsening appears as a plain
 * row, with the one action that matters from Today.
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
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    todaySymptoms: {
      active_count: 2,
      worsening_count: 1,
      most_recent: {
        episode_id: 'episode-1',
        name: 'Headache',
        severity: 5,
        change_state: 'worsening',
        updated_at: '2026-09-27T09:00:00Z',
      },
      has_episodes: true,
    },
    important: [
      {
        id: 'symptom-episode:episode-1',
        type: 'symptom_episode',
        title: 'Headache — 5/10',
        subtitle: 'You recorded this as worsening',
        priority: 'normal',
        action_route: '/symptoms/episode-1',
      },
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('shows the symptom most recently written about, without dressing it up as an alert', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      // Twice: on the card, and as the Important Today row.
      expect(screen.getAllByText('Headache — 5/10')).toHaveLength(2);
    },
    { timeout: 30_000 }
  );

  // The card: the user's own number, when it was last touched, which way it is
  // going, and the count behind it.
  expect(screen.getAllByText(/Getting worse/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Last updated/)).toBeTruthy();
  expect(screen.getByText(/2 active symptoms · 1 recorded as worsening/)).toBeTruthy();

  // The one action worth having on Today.
  expect(screen.getByRole('button', { name: 'Add an update' })).toBeTruthy();

  // Important Today carries it as an ordinary row (PRD 6, section 40).
  expect(screen.getByText('You recorded this as worsening')).toBeTruthy();

  // Nothing anywhere claims urgency, and nothing is a diagnosis.
  for (const wording of [
    /urgent/i,
    /emergency/i,
    /seek help/i,
    /call/i,
    /migraine/i,
    /probably/i,
  ]) {
    expect(screen.queryByText(wording)).toBeNull();
  }

  // The card is drawn from the Today response -- no second request for it.
  expect(
    backend.requests.filter((request) => request.path.includes('/symptoms')).length
  ).toBe(0);
});
