/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The safety screens, read the way a screen reader reads them (PRD 10, §118).
 *
 * Section 118's list, checked where each item matters most.
 *
 * **Explicit text on critical actions.** Every control that starts or stops
 * something is a `button` with a readable name, found by that name rather
 * than by position.
 *
 * **No colour-only status.** Monitoring on/off and every capability state are
 * words. A chip's colour is allowed to agree with them and never to be the
 * only thing that says them.
 *
 * **An accessible SOS alternative** (section 118's own phrasing). Section 13
 * allows press-and-hold *or* tap-then-confirm, and this build chose the
 * second for exactly this reason: a hold has no accessible equivalent a
 * screen reader can describe or a shaking hand can complete.
 *
 * **Countdown text, not animation only.** Asserted as a sentence.
 *
 * **Warnings are announced.** The standing sentences are `alert`s, so a
 * screen reader says them rather than leaving them to be noticed.
 *
 * Driven through `renderRouter` on the real screens: RNTL's bare `render`
 * returns no usable queries under this project's React 19 pairing. One
 * `renderRouter` per file.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  mockBackend,
  monitoringSessionFixture,
  safetyCheckFixture,
  safetyStatusFixture,
  signInAt,
} from './helpers';

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
    safetyStatus: safetyStatusFixture({
      monitoring: monitoringSessionFixture(),
      monitoring_sentence: 'Safety Monitoring is on until 7:00 PM.',
      active_event: safetyCheckFixture(),
      emergency_contact_count: 1,
      detection_notice:
        'Safety Monitoring is on. Automatic detection by the robot is not connected yet, so Nura will not notice anything by itself. You can still ask for help at any time.',
    }),
  });
});

afterEach(() => {
  backend.restore();
});

it('announces every safety state in words, with named controls and a text countdown', async () => {
  renderRouter('app', { initialUrl: '/safety/check' });

  // Section 118: the countdown is a sentence a screen reader can read.
  await waitFor(() => {
    expect(screen.getByText(/Time is up|seconds left/)).toBeVisible();
  });

  // The prompt is an alert, so it is announced rather than noticed.
  expect(screen.getByRole('alert')).toBeTruthy();

  // Explicit text on the critical actions -- found by name, not by position.
  for (const label of ['I’m okay', 'I need help', 'Dismiss — false alarm']) {
    const control = screen.getByRole('button', { name: label });
    expect(control).toBeVisible();
    // Enabled, and announced as such rather than inferred from appearance.
    expect(control.props.accessibilityState?.disabled).toBeFalsy();
  }

  // And nothing on this screen carries meaning by colour: the state of the
  // event is a label, and the question is a sentence.
  expect(screen.getByText('Possible fall')).toBeVisible();
  expect(
    screen.getByText('Nura noticed something unusual. Ada, are you okay?')
  ).toBeVisible();
});
