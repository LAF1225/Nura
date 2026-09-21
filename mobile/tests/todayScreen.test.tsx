/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Today with a linked robot that is offline (PRD 3, sections 6, 63 and 64).
 *
 * Runs against the real `app/` directory, so this is the screen a user gets:
 * the greeting, the check-in prompt, the empty Important Today section, and a
 * device whose status comes from the backend's `last_seen_at` alone. No robot
 * is involved -- the stub simply answers as the backend would.
 *
 * One `renderRouter` per file (see navigation.test.tsx), so the other Today
 * states have files of their own.
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

// Stands in for a configured Supabase project so the auth gate can let us in.
jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    preferredName: 'Safdar',
    checkIn: null,
    todayDevice: {
      device_id: 'device-1',
      display_name: 'Nura',
      connection_status: 'offline',
      last_seen_at: new Date(Date.now() - 42 * 60_000).toISOString(),
      setup_completed: true,
    },
  });
});

afterEach(() => {
  backend.restore();
});

it('greets, offers the check-in, shows an offline robot, and records an answer', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText(/, Safdar$/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The greeting is time-of-day dependent, so assert the shape rather than
  // pinning the suite to a clock.
  expect(screen.getByText(/^Good (morning|afternoon|evening), Safdar$/)).toBeTruthy();

  // The prompt and all three answers, each with its own text.
  expect(screen.getByText('How are you feeling today?')).toBeTruthy();
  for (const label of ['Good', 'Okay', 'Not great']) {
    expect(screen.getByRole('radio', { name: label })).toBeTruthy();
  }

  // Important Today: empty, and phrased as good news rather than "No data".
  expect(screen.getByText('Nothing needs your attention right now.')).toBeTruthy();

  // The device, straight from the backend's answer.
  expect(screen.getByText(/Nura is currently offline/)).toBeTruthy();
  expect(screen.getByText(/Last connected 42 minutes ago/)).toBeTruthy();

  // Asked for the local date, not left to the server to guess (PRD 3, s39).
  const todayRequest = backend.requests.find((request) =>
    request.path.startsWith('/api/v1/today')
  );
  expect(todayRequest?.path).toMatch(/local_date=\d{4}-\d{2}-\d{2}/);

  // --- and now check in, on the same mounted screen ---
  fireEvent.press(screen.getByRole('radio', { name: 'Good' }));

  await waitFor(() => {
    expect(screen.getByText(/You checked in as “Good” today\./)).toBeTruthy();
  });

  // PUT, so sending it twice cannot produce two rows for one day.
  const submission = backend.requests.find(
    (request) =>
      request.path.startsWith('/api/v1/daily-checkins/today') && request.method === 'PUT'
  );
  expect(submission?.body).toMatchObject({ wellbeing_level: 'good' });

  // An acknowledgement, never an interpretation (PRD 3, section 45).
  expect(screen.getByText('Thanks for checking in.')).toBeTruthy();
});
