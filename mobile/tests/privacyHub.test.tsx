/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Privacy & Security hub (PRD 13, sections 4 to 10, 36 to 38, 50).
 *
 * One test, because the harness allows one `renderRouter` per file -- the same
 * shape every screen test in this project has. It is a walk down the screen,
 * and what it asserts is mostly that the screen shows *the server's* answer.
 *
 * That emphasis is the point rather than a shortcut. Section 4 says reuse the
 * destination screens and do not duplicate the settings; sections 9 and 10 say
 * no hard-coded optimistic wording; section 38 says unverified hardware stays
 * labelled as such. A hub that kept its own copy of what a caregiver can see,
 * or its own sentence about a microphone, would eventually disagree with the
 * thing it describes -- so a test asserting wording this screen invented would
 * be asserting the bug.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  capabilityLineFixture,
  dataExportFixture,
  mockBackend,
  privacySummaryFixture,
  signInAt,
} from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
});

afterEach(() => {
  backend?.restore();
});

it('shows what Nura stores, who can see it, and what it cannot reach', async () => {
  backend = mockBackend({
    status: 'onboarding_complete',
    privacySummary: privacySummaryFixture({
      memory_count: 4,
      active_memory_count: 3,
      conversation_count: 2,
      caregivers: [
        {
          relationship_id: 'rel-1',
          name: 'Ayesha',
          role: 'family',
          granted: ['medications', 'appointments'],
          accepted_at: '2026-10-01T09:00:00Z',
        },
      ],
      robot_linked: true,
      robot_capabilities: [
        capabilityLineFixture({
          key: 'display',
          label: 'Screen',
          state: 'not_verified',
          state_label: 'Not tested yet',
        }),
        capabilityLineFixture({
          key: 'speaker',
          label: 'Speaker',
          state: 'not_connected',
          state_label: 'Not connected',
        }),
      ],
      robot_previews: [['Medication reminders', 'Private']],
      latest_export: dataExportFixture(),
    }),
  });

  renderRouter('app', { initialUrl: '/privacy' });

  await waitFor(() => {
    expect(screen.getByText('Privacy Mode')).toBeTruthy();
  });

  // --- what Nura stores (sections 5 and 7) ---------------------------------
  // Counts read from the server, not cached in the app.
  expect(screen.getByText('3 of 4 in use')).toBeTruthy();
  expect(screen.getByText('2 conversations')).toBeTruthy();
  // Section 5's state and its limit, both the server's sentences.
  expect(
    screen.getByText(
      'Privacy Mode is off. Nura may start a conversation or suggest something to remember.'
    )
  ).toBeTruthy();
  expect(screen.getByText(/not a hardware switch/)).toBeTruthy();

  // --- camera and microphone (section 6) ----------------------------------
  // The honest row is what Nura has never asked for, not what it turned off.
  expect(screen.getByText(/Nura does not listen/)).toBeTruthy();
  expect(screen.getByText(/Nura does not watch/)).toBeTruthy();

  // --- who can see it (section 8) -----------------------------------------
  expect(screen.getByText('1 person')).toBeTruthy();
  expect(screen.getByText('Ayesha')).toBeTruthy();
  // The categories the *server* says they hold.
  expect(screen.getByText('medications, appointments')).toBeTruthy();

  // --- safety (section 9) --------------------------------------------------
  // PRD 10's own map. "Not set up in this build" because no provider exists,
  // not because this screen says so.
  expect(screen.getByText('Emergency request')).toBeTruthy();
  expect(screen.getByText('Push notifications')).toBeTruthy();
  expect(screen.getByText('Not set up in this build')).toBeTruthy();

  // --- the robot (sections 10 and 38) --------------------------------------
  expect(screen.getByText('Not tested yet')).toBeTruthy();
  expect(screen.getByText('Not connected')).toBeTruthy();
  expect(screen.getByText('Medication reminders')).toBeTruthy();
  expect(screen.getByText('Private')).toBeTruthy();

  // --- what Nura can reach (section 37) -----------------------------------
  // No production UI shows mock live data, and the sentences are PRD 12's.
  expect(screen.getByText('Live weather is not configured in this build.')).toBeTruthy();
  expect(
    screen.getByText('Live news access is not configured in this build.')
  ).toBeTruthy();
  expect(
    screen.getByText('I can add that to Nura, but an external calendar is not connected.')
  ).toBeTruthy();

  // --- the build's own honesty (section 36) --------------------------------
  // One sentence here; the detail lives in the docs rather than as a warning
  // on every ordinary screen.
  expect(screen.getByText(/not yet been tested on a physical phone/)).toBeTruthy();

  // --- accessibility (section 50) -----------------------------------------
  // A capability row is announced as one label and one state. Read out as two
  // unconnected strings it would be uninterpretable.
  expect(screen.getByLabelText('Emergency request. Available')).toBeTruthy();
  expect(screen.getByLabelText('Screen. Not tested yet')).toBeTruthy();

  // --- the way on (sections 17 and 21) ------------------------------------
  expect(screen.getByText('Export your data')).toBeTruthy();
  expect(screen.getByText('Delete your data')).toBeTruthy();

  // --- and nothing claims more than it should -----------------------------
  // Section 35's vocabulary, as an absence: nothing on a privacy screen says a
  // thing was delivered, displayed or synced.
  for (const forbidden of [/\bDelivered\b/, /\bDisplayed\b/, /\bSynced\b/]) {
    expect(screen.queryByText(forbidden)).toBeNull();
  }
});
