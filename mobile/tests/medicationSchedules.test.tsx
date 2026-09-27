/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The reminder schedule list (PRD 5, sections 4, 11, 37 and 38).
 *
 * Two things this screen has to get right, both tested here:
 *
 * **A schedule reads as a sentence.** "Mon, Wed and Fri at 9:00 AM" is how
 * people describe a routine, and it is how they will notice a mistake.
 *
 * **A paused schedule says so in words**, not by looking dimmer. Colour and
 * weight are not something everyone can read (PRD 5, section 61), and nothing
 * anywhere guesses at *why* it was paused (section 37).
 *
 * The medication picker underneath is the PRD 5 section 4 boundary made
 * visible: a reminder is always attached to a medication the user already
 * added in Health, and a medication marked as no longer taken is not offered.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  medicationRecordFixture,
  mockBackend,
  scheduleFixture,
  signInAt,
} from './helpers';

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
    schedules: [
      scheduleFixture({
        id: 'schedule-1',
        schedule_type: 'specific_days',
        times: [
          { id: 'a', time_of_day: '09:00:00', weekday: 0 },
          { id: 'b', time_of_day: '09:00:00', weekday: 2 },
          { id: 'c', time_of_day: '09:00:00', weekday: 4 },
        ],
      }),
      scheduleFixture({
        id: 'schedule-2',
        medication_name: 'Ramipril',
        medication_dose: '5 mg',
        is_active: false,
        paused_at: '2026-09-12T10:00:00Z',
      }),
    ],
    healthRecords: {
      medications: [
        medicationRecordFixture(),
        medicationRecordFixture({ id: 'medication-2', name: 'Ramipril', dose: '5' }),
        // A course that has finished. Its schedules stay paused rather than
        // being deleted, and it is not offered for a new one (PRD 5, s38).
        medicationRecordFixture({
          id: 'medication-3',
          name: 'Amoxicillin',
          is_active: false,
        }),
      ],
    },
  });
});

afterEach(() => {
  backend.restore();
});

it('reads each schedule as a sentence and says which are paused', async () => {
  renderRouter('app', { initialUrl: '/medications/schedules' });

  await waitFor(
    () => {
      expect(screen.getByText('Mon, Wed and Fri at 9:00 AM')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  expect(screen.getByText('Every day at 8:00 AM')).toBeTruthy();

  // Paused is stated, and no reason is offered or asked for.
  expect(screen.getByText('Reminders paused')).toBeTruthy();
  expect(screen.queryByText(/why|because|reason for pausing/i)).toBeNull();

  // The picker offers the medications that are being taken, and not the one
  // that has been marked inactive.
  expect(screen.getByText('Set a reminder for')).toBeTruthy();
  // Matched by hint rather than by name: "Metformin" also appears above, on
  // the schedule that already exists for it.
  expect(screen.getByRole('button', { name: 'Ramipril' }).props.accessibilityHint).toBe(
    'Sets a reminder for Ramipril'
  );
  expect(screen.queryByText('Amoxicillin')).toBeNull();

  // And it says plainly what pausing and removing do to history.
  expect(
    screen.getByText(/Pausing keeps everything you have already recorded/)
  ).toBeTruthy();
});
