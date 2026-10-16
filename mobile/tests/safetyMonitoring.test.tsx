/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Starting and stopping Safety Monitoring (PRD 10, sections 4, 5, 7, 8,
 * 59, 60, 61, 62, 66 and 113).
 *
 * Four things are under test.
 *
 * **Off is a state, said in words.** Section 4 forbids silent monitoring, so
 * the screen says it is off before anything is on.
 *
 * **The duration and the timeout are chosen, and the choice is sent.** Both
 * asserted on the request body rather than on the screen: what matters is
 * that the server was told, because the server is what decides when
 * monitoring ends (section 61).
 *
 * **The second prompt's timing is on screen** (section 8). Twenty seconds,
 * stated rather than implied.
 *
 * **Monitoring on says nothing is watching** (section 66). The sentence that
 * stops somebody reading "Safety Monitoring is on" as a detector.
 *
 * One `renderRouter` for the file, because a second one in the same file
 * fails with "render has not been called"; navigation is `router.push`.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import {
  act,
  fireEvent,
  renderRouter,
  screen,
  waitFor,
} from 'expo-router/testing-library';

import { mockBackend, safetyStatusFixture, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    safetyStatus: safetyStatusFixture({ emergency_contact_count: 2 }),
  });
});

afterEach(() => {
  backend.restore();
});

it('starts monitoring with the duration and timeout that were chosen, then stops it', async () => {
  renderRouter('app', { initialUrl: '/safety' });

  // Section 4: off, and said so.
  await waitFor(() => {
    expect(screen.getByText('Safety Monitoring is off.')).toBeVisible();
  });
  expect(screen.getByRole('button', { name: 'Start monitoring' })).toBeVisible();

  act(() => {
    router.push('/safety/start');
  });

  // Section 5's four presets and nothing else.
  await waitFor(() => {
    expect(screen.getByText('Monitor for')).toBeVisible();
  });
  for (const label of ['30 minutes', '1 hour', 'Until bedtime', 'Until turned off']) {
    expect(screen.getByText(label)).toBeVisible();
  }

  // Section 7's options, with its default.
  for (const seconds of [15, 30, 45, 60, 90]) {
    expect(screen.getByText(`${seconds} seconds`)).toBeVisible();
  }

  // Section 8: the exact timing, written down.
  expect(screen.getByText(/waits 20 seconds, then starts escalation/i)).toBeVisible();

  fireEvent.press(screen.getByText('30 minutes'));
  fireEvent.press(screen.getByText('90 seconds'));
  fireEvent(screen.getByLabelText('Ask a second time'), 'valueChange', true);

  fireEvent.press(screen.getAllByRole('button', { name: 'Start monitoring' })[0]!);

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/monitoring/start'))
    ).toHaveLength(1);
  });
  const sent = backend.requests.find((request) =>
    request.path.includes('/monitoring/start')
  )?.body as Record<string, unknown>;
  expect(sent.duration_mode).toBe('30_minutes');
  expect(sent.response_timeout_seconds).toBe(90);
  expect(sent.second_prompt_enabled).toBe(true);
  // The phone's own zone, not a server guess: "until bedtime" needs one, and
  // only the phone knows it (section 6).
  expect(typeof sent.timezone).toBe('string');
  // And no end instant: the server works that out (section 61).
  expect(sent.ends_at).toBeUndefined();

  // Back on the Safety screen, monitoring is on -- and the screen says
  // nothing is actually watching (section 66).
  await waitFor(() => {
    expect(screen.getByText('Safety Monitoring is on until 7:00 PM.')).toBeVisible();
  });
  expect(
    screen.getByText(/Automatic detection by the robot is not connected yet/i)
  ).toBeVisible();
  // The timeout that was chosen, read back from the session the server
  // stored it on (section 7) -- not the default this screen started with.
  expect(screen.getByText('Response timeout: 90 seconds')).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'Stop monitoring' }));

  await waitFor(() => {
    expect(screen.getByText('Safety Monitoring is off.')).toBeVisible();
  });
  expect(
    backend.requests.filter((request) => request.path.includes('/monitoring/stop'))
  ).toHaveLength(1);
});
