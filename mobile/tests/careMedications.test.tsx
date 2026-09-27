/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Care tab (PRD 5, sections 6 and 30).
 *
 * Care was a placeholder through PRD 3 and 4. PRD 5 gives it its first real
 * section, and this test is mostly about the boundary it has to hold:
 *
 *     Health = what the medication is
 *     Care   = reminders, schedules, adherence, refills
 *
 * So Care shows counts and a way in, and never the medication record itself.
 * The parts of the tab that do not exist yet still say so rather than showing
 * disabled rows (PRD 3, section 35).
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, scheduleFixture, signInAt } from './helpers';

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
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    schedules: [scheduleFixture(), scheduleFixture({ id: 'schedule-2' })],
    todayMedications: {
      next_due: {
        dose_id: 'dose-1',
        medication_id: 'medication-1',
        medication_name: 'Metformin',
        medication_dose: '500 mg',
        scheduled_for: '2026-09-13T20:00:00Z',
        status: 'scheduled',
        window: 'upcoming',
        can_snooze: true,
      },
      due_today_count: 2,
      overdue_count: 1,
      remaining_today_count: 1,
      low_supply: [
        {
          medication_id: 'medication-1',
          medication_name: 'Metformin',
          remaining_doses: 4,
        },
      ],
      has_schedules: true,
    },
  });
});

afterEach(() => {
  backend.restore();
});

it('summarises medications and keeps everything else honest about not existing', async () => {
  renderRouter('app', { initialUrl: '/care' });

  await waitFor(
    () => {
      expect(screen.getByText('2 reminder schedules')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  expect(screen.getByRole('header', { name: 'Care' })).toBeTruthy();
  expect(screen.getByText('Medications')).toBeTruthy();
  expect(screen.getByText('Metformin — 500 mg')).toBeTruthy();

  // An unrecorded dose is stated plainly, with no warning colour or wording
  // (PRD 5, sections 24 and 29).
  expect(screen.getByText('1 dose hasn’t been marked as taken.')).toBeTruthy();
  expect(screen.queryByText(/overdue|urgent|alert|warning/i)).toBeNull();

  // The refill note keeps its "about", because the count came from the user.
  expect(screen.getByText('You have about 4 doses of Metformin left.')).toBeTruthy();

  // A way into the rest of it.
  expect(screen.getByRole('button', { name: 'View all' })).toBeTruthy();

  // Care holds no medication *record* -- no dose form, no frequency text, no
  // way to edit what the medication is. That lives in Health (PRD 5, s30).
  expect(screen.queryByText(/Add a medication/)).toBeNull();

  // And the parts of Care that do not exist say so (PRD 3, section 35).
  expect(screen.getByText('No caregivers are set up yet.')).toBeTruthy();
});
