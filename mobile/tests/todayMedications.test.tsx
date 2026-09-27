/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Today with a medication due (PRD 5, sections 28, 29 and 53).
 *
 * Runs against the real `app/` directory, so this is the screen a user gets:
 * the next dose with Taken, Snooze and Skip on it, the counts, and the
 * overdue row in Important Today. No robot is involved anywhere.
 *
 * One `renderRouter` per file (see navigation.test.tsx), so the "no schedules"
 * state and the Care screens have files of their own.
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

// No OS scheduler under Node. The reminder service is exercised properly in
// medicationNotifications.test.ts; here it only has to not blow up.
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

/**
 * This morning, on the machine running the test.
 *
 * The card subtracts the dose it is showing from "later today" only when that
 * dose is actually one of today's -- `next_due` may be yesterday's, still
 * waiting to be recorded -- so the fixture has to sit on the real local day
 * rather than on a date written into the file.
 */
const THIS_MORNING = (() => {
  const at = new Date();
  at.setHours(8, 0, 0, 0);
  return at.toISOString();
})();

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    preferredName: 'Ada',
    todayDevice: null,
    checkIn: { wellbeing_level: 'good', note: null },
    doses: [
      {
        id: 'dose-1',
        profile_id: 'profile-1',
        medication_id: 'medication-1',
        medication_name: 'Metformin',
        medication_dose: '500 mg',
        schedule_id: 'schedule-1',
        scheduled_for: THIS_MORNING,
        local_date: '2026-09-13',
        status: 'scheduled',
        window: 'overdue',
        action_at: null,
        source: null,
        skip_reason_code: null,
        skip_reason_text: null,
        snoozed_until: null,
        snooze_count: 0,
        late: false,
        can_snooze: true,
      },
    ],
    todayMedications: {
      next_due: {
        dose_id: 'dose-1',
        medication_id: 'medication-1',
        medication_name: 'Metformin',
        medication_dose: '500 mg',
        scheduled_for: THIS_MORNING,
        status: 'scheduled',
        window: 'overdue',
        can_snooze: true,
      },
      due_today_count: 3,
      overdue_count: 1,
      remaining_today_count: 3,
      low_supply: [
        {
          medication_id: 'medication-1',
          medication_name: 'Metformin',
          remaining_doses: 4,
        },
      ],
      has_schedules: true,
    },
    important: [
      {
        id: 'medication-dose:dose-1',
        type: 'medication_dose',
        title: 'Metformin — 500 mg',
        subtitle: 'Not marked as taken',
        due_at: THIS_MORNING,
        priority: 'important',
        action_route: '/medications',
      },
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('shows the next dose with its three actions, and records Taken', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      // Twice on purpose: once on the card, once in Important Today. The
      // card is where it is acted on; the row is where it is noticed.
      expect(screen.getAllByText('Metformin — 500 mg')).toHaveLength(2);
    },
    { timeout: 30_000 }
  );

  // All three actions, each with its own text. PRD 5 section 61 rules out
  // icon-only controls, so every one of these is found by its label.
  for (const label of ['Taken', 'Snooze', 'Skip']) {
    expect(screen.getByRole('button', { name: label })).toBeTruthy();
  }

  // The window is stated in words beside the time, not by colour alone --
  // on the card and again on the Important Today row (PRD 5, s24 and s61).
  expect(screen.getAllByText(/Not marked as taken/).length).toBeGreaterThan(0);
  // Two more today, beyond the one being shown.
  expect(screen.getByText('2 more later today')).toBeTruthy();
  // A routine reminder, never dressed up as an emergency (PRD 5, s29).
  expect(screen.queryByText(/urgent|emergency|alert/i)).toBeNull();

  // The refill note, cautiously worded because the count came from the user.
  expect(screen.getByText('You have about 4 doses of Metformin left.')).toBeTruthy();

  // The card itself is drawn from the Today response (PRD 5, section 53).
  expect(
    backend.requests.filter((request) => request.path.startsWith('/api/v1/today')).length
  ).toBeGreaterThan(0);

  // Today's doses are fetched too, but for the *reminders* rather than for
  // the card: somebody who has just reinstalled, or whose phone has been off
  // for a week, gets their local notifications rebuilt without going anywhere
  // (PRD 5, sections 43 and 55). Only somebody with schedules pays for it --
  // todayNoMedications.test.tsx checks that nothing is fetched otherwise.
  expect(
    backend.requests.some((request) => request.path.includes('/medication-doses/today'))
  ).toBe(true);

  // --- and now record it, on the same mounted screen ---
  fireEvent.press(screen.getByRole('button', { name: 'Taken' }));

  await waitFor(() => {
    const recorded = backend.requests.find(
      (request) =>
        request.path === '/api/v1/profiles/profile-1/medication-doses/dose-1/taken' &&
        request.method === 'POST'
    );
    expect(recorded).toBeTruthy();
  });

  // No status and no source: a dose moves by *doing* something to it, and how
  // the action arrived is the server's own observation (PRD 5, s17 and s46).
  const recorded = backend.requests.find((request) =>
    request.path.endsWith('/medication-doses/dose-1/taken')
  );
  expect(recorded?.body).not.toHaveProperty('status');
  expect(recorded?.body).not.toHaveProperty('source');
});
