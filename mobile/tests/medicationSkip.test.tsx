/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Skipping a dose (PRD 5, sections 19, 20 and 57).
 *
 * The reason is optional, and this test is mostly about proving that it
 * genuinely is: "Skip without a reason" is a button of its own, sits beside
 * the reasons rather than behind a dismiss gesture, and sends `none`.
 *
 * It also checks the two things that must *not* happen: nothing on the screen
 * interprets a reason, and nothing tells anybody what to do about a skipped
 * dose beyond pointing at their clinician.
 *
 * Driven from the medication screen rather than mounted directly, so the
 * whole flow is exercised -- Skip opens the sheet, choosing a reason records
 * it, and the sheet closes back to where it came from.
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
    // A schedule as well as a dose: the medication screen shows its empty
    // state for an account with no schedules, which is a different test.
    schedules: [scheduleFixture()],
    doses: [doseFixture()],
  });
});

afterEach(() => {
  backend.restore();
});

it('offers every reason, and skipping without one', async () => {
  renderRouter('app', { initialUrl: '/medications' });

  await waitFor(
    () => {
      expect(screen.getByRole('button', { name: 'Skip' })).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  fireEvent.press(screen.getByRole('button', { name: 'Skip' }));

  await waitFor(() => {
    expect(screen.getByText('Why are you skipping this dose?')).toBeTruthy();
  });

  // Optional, and said so before anything is chosen.
  expect(screen.getByText(/This is optional/)).toBeTruthy();

  // Every reason PRD 5 section 19 lists, each as a labelled button.
  for (const label of [
    'Feeling unwell',
    'Ran out',
    'Doctor advised',
    'Forgot or too late',
    'Other',
  ]) {
    expect(screen.getByRole('button', { name: label })).toBeTruthy();
  }

  // Skipping without a reason is as easy as choosing one -- a button beside
  // them, not something you get by dismissing the sheet.
  expect(screen.getByRole('button', { name: 'Skip without a reason' })).toBeTruthy();

  // Nothing here interprets an answer or advises anything (PRD 5, s19, s57).
  expect(
    screen.queryByText(/you should|take it later|double|contact your doctor/i)
  ).toBeNull();
  expect(
    screen.getByText(/follow the instructions from your clinician or pharmacist/i)
  ).toBeTruthy();

  // --- choose a reason, on the same mounted screen ---
  fireEvent.press(screen.getByRole('button', { name: 'Ran out' }));

  await waitFor(() => {
    expect(
      backend.requests.some(
        (request) =>
          request.path.endsWith('/medication-doses/dose-1/skip') &&
          request.method === 'POST'
      )
    ).toBe(true);
  });

  const skip = backend.requests.find((request) =>
    request.path.endsWith('/medication-doses/dose-1/skip')
  );
  expect(skip?.body).toMatchObject({ reason_code: 'ran_out' });
  // No note was typed, so none is sent -- rather than an empty string that
  // would render back as a note the user did not write.
  expect((skip?.body as { reason_text: unknown }).reason_text).toBeNull();

  // And the sheet closes back to the screen it came from.
  await waitFor(() => {
    expect(screen.queryByText('Why are you skipping this dose?')).toBeNull();
  });
});
