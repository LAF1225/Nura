/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Supply and refills (PRD 5, sections 31-35).
 *
 * The rule the whole screen exists to keep: **the number is the user's, and
 * it is approximate.** So it is shown back with "about", the caveat is on the
 * screen rather than in a help page, and the two actions are "correct what
 * Nura holds" and "I have picked up a new supply" -- which are different
 * things and are kept apart.
 *
 * What must not appear: any estimate of how long a supply will last, any
 * suggestion to order anything, any advice about dosing.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { medicationRecordFixture, mockBackend, signInAt } from './helpers';

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
    supply: [
      {
        profile_id: 'profile-1',
        medication_id: 'medication-1',
        medication_name: 'Metformin',
        tracking_enabled: true,
        remaining_doses: 4,
        refill_threshold_doses: 5,
        last_refill_date: '2026-08-24',
        low: true,
      },
    ],
    healthRecords: {
      medications: [
        medicationRecordFixture(),
        medicationRecordFixture({
          id: 'medication-2',
          name: 'Ramipril',
          dose: '5',
        }),
      ],
    },
  });
});

afterEach(() => {
  backend.restore();
});

it('shows the user’s own count, says it is approximate, and records a refill', async () => {
  renderRouter('app', { initialUrl: '/medications/supply' });

  await waitFor(
    () => {
      expect(screen.getByText('About 4 doses left')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The threshold is the user's, and it is stated rather than assumed.
  expect(screen.getByText('Nura mentions a refill at 5 left.')).toBeTruthy();
  expect(
    screen.getAllByText('This is the count you entered, so treat it as approximate.')
      .length
  ).toBeGreaterThan(0);
  expect(screen.getByText('Running low')).toBeTruthy();

  // Nothing estimates, orders, or advises (PRD 5, sections 31, 34 and 57).
  expect(screen.queryByText(/will last|order|pharmacy|reorder|days left/i)).toBeNull();

  // A medication with no count yet is offered, rather than started silently.
  expect(screen.getByText('Start tracking')).toBeTruthy();
  expect(screen.getByRole('button', { name: /Ramipril/ })).toBeTruthy();

  // Only Taken moves the count, and the screen says so (PRD 5, section 33).
  expect(screen.getByText(/Snoozing or skipping doesn’t change it/)).toBeTruthy();

  // --- open one and record a refill, on the same mounted screen ---
  fireEvent.press(screen.getByRole('button', { name: 'Mark refilled' }));

  await waitFor(() => {
    expect(screen.getByText('Doses remaining')).toBeTruthy();
  });

  fireEvent.press(screen.getByRole('button', { name: 'Mark refilled' }));

  await waitFor(() => {
    expect(
      backend.requests.some(
        (request) =>
          request.path.endsWith('/medication-supply/medication-1/refill') &&
          request.method === 'POST'
      )
    ).toBe(true);
  });

  const refill = backend.requests.find((request) => request.path.endsWith('/refill'));
  // The count replaces the old one rather than being added to it, and the
  // day comes from the client's own clock (PRD 5, section 35).
  expect(refill?.body).toMatchObject({ remaining_doses: 4 });
  expect((refill?.body as { refilled_on: string }).refilled_on).toMatch(
    /^\d{4}-\d{2}-\d{2}$/
  );
});
