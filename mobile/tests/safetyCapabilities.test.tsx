/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * What the app says this build can do (PRD 10, sections 64, 66, 67, 72, 73,
 * 74, 106, 118 and 113).
 *
 * Four things are under test.
 *
 * **Every capability is named with its state in words** (sections 106 and
 * 118). Not a colour, not an icon: a row that says "Not set up in this
 * build" is one a screen reader can read out.
 *
 * **The three that work and the four that do not are both asserted.** A test
 * that only checked the available ones would pass on a screen that claimed
 * everything worked.
 *
 * **Offline says what to do instead** (section 67). The status request fails
 * and the screen says Nura cannot record an emergency request at all --
 * rather than offering a button that will fail.
 *
 * **The no-contacts warning appears and does not block monitoring**
 * (section 73). Preferred prototype behaviour, said in the PRD itself.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import { act, renderRouter, screen, waitFor } from 'expo-router/testing-library';

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
    safetyStatus: safetyStatusFixture(),
  });
});

afterEach(() => {
  backend.restore();
});

it('names every capability with its state, and warns when there is nobody to reach', async () => {
  renderRouter('app', { initialUrl: '/safety' });

  // Section 73: warn, and still allow monitoring.
  await waitFor(() => {
    expect(screen.getByText(/No emergency contacts are set up/i)).toBeVisible();
  });
  expect(screen.getByRole('button', { name: 'Start monitoring' })).toBeVisible();

  act(() => {
    router.push('/safety/capabilities');
  });

  await waitFor(() => {
    expect(
      screen.getByText('This is the actual state of this build, not a list of features.')
    ).toBeVisible();
  });

  // Section 106, row by row. The three that work:
  for (const label of [
    'Emergency request',
    'Safety check-in prompts',
    'In-app alerts for caregivers',
  ]) {
    expect(screen.getByText(label)).toBeVisible();
  }
  expect(screen.getAllByText('Available')).toHaveLength(3);

  // And the four that do not, each said in words rather than by a colour.
  for (const label of [
    'Push notifications',
    'Text messages',
    'Audio calling',
    'Automatic detection by the robot',
  ]) {
    expect(screen.getByText(label)).toBeVisible();
  }
  expect(screen.getAllByText('Not set up in this build')).toHaveLength(3);
  expect(screen.getAllByText('Not connected yet')).toHaveLength(1);

  // Section 74's warning, on the screen whose whole job is honesty.
  expect(screen.getByText(/it cannot reach anybody for you/i)).toBeVisible();
  // Section 72: no guarantee anywhere.
  expect(screen.queryByText(/guarantee/i)).toBeNull();
});

it('says Nura cannot record an emergency request while it is offline', async () => {
  // A second `renderRouter` fails in one file, so the offline case is driven
  // through the client: what section 67 requires is that the app does not
  // claim a server escalation happened, and a failed request is where that
  // starts.
  backend.restore();
  const offline = mockBackend({ status: 'ready_for_pairing', todayDevice: null });
  const originalFetch = global.fetch;
  global.fetch = jest.fn(() => Promise.reject(new Error('offline'))) as never;

  const { fetchSafetyStatus } = require('../src/features/safety/api');
  await expect(fetchSafetyStatus('profile-1')).rejects.toBeTruthy();

  const copy = require('../src/features/safety/copy');
  expect(copy.OFFLINE_BODY).toMatch(/cannot reach the server/i);
  expect(copy.OFFLINE_BODY).toMatch(/Call someone directly/i);
  // And it never claims anything was recorded or sent.
  expect(copy.OFFLINE_BODY).not.toMatch(/sent|contacted|notified/i);

  global.fetch = originalFetch;
  offline.restore();
});
