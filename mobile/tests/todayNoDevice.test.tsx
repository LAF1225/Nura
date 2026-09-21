/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Today with no robot linked, and a check-in already made
 * (PRD 3, sections 6, 11, 54, 57 and 63).
 *
 * This is the state the app is actually in while the hardware is being built,
 * so it has to read as a normal, finished screen -- an invitation, not an
 * error. The check-in is shown as recorded, with a way to change it.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    preferredName: 'Ada',
    todayDevice: null,
    checkIn: { wellbeing_level: 'okay', note: 'Feeling tired today.' },
  });
});

afterEach(() => {
  backend.restore();
});

it('treats "no robot yet" as a normal state and shows the recorded check-in', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText('Your Nura isn’t connected yet')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // An invitation, with no error wording anywhere near it (PRD 3, s54).
  expect(
    screen.getByText(/You can keep setting up the app now and connect the robot/)
  ).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Connect' })).toBeTruthy();
  expect(screen.queryByText(/error/i)).toBeNull();
  expect(screen.queryByText(/missing/i)).toBeNull();

  // The check-in, as recorded, with the user's own note shown back to them.
  expect(screen.getByText(/You checked in as “Okay” today\./)).toBeTruthy();
  expect(screen.getByText('Feeling tired today.')).toBeTruthy();
  expect(screen.getByText('This week: 1 check-in completed')).toBeTruthy();

  // A way to change it is offered rather than the prompt being shown again.
  //
  // What happens *after* pressing Change is not asserted here: reopening the
  // chooser is local component state, and this React 19 + RNTL environment
  // does not flush a local `useState` update from a press (a three-line
  // component with no router behaves the same way). PRD 3 section 52 covers
  // this case -- the logic that survives is tested elsewhere
  // (dashboardCards.test.ts, todayLogic.test.ts), and the limitation is in
  // the README rather than papered over with a test that proves nothing.
  expect(screen.getByRole('button', { name: 'Change' })).toBeTruthy();
  expect(screen.queryByText('How are you feeling today?')).toBeNull();
});
