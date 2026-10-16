/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * What this Nura can do, said in words (PRD 11, sections 10, 12, 47, 91, 124).
 *
 * Four things are under test.
 *
 * **All twelve capabilities are shown, with the state in words.** Section 10
 * rules out one `robot_ready` boolean, and this is what that buys: "the screen
 * works and the speaker has never been tested" is two different rows, and a
 * screen reader can read both out.
 *
 * **`not_verified` reads as "Not tested yet"** -- not as working, and not as
 * broken (sections 12 and 91). This is the state a real first build would
 * honestly report, and the one a hopeful screen would round up.
 *
 * **A stale report says why** (section 124). The device said the display
 * worked; the firmware it said that under is no longer running; so the state
 * acted on is "not tested yet" and the row explains itself.
 *
 * **A reported speaker brings the volume control with it** (section 47), which
 * is the other half of `robotSettings.test.tsx`'s assertion that it is absent.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { router } from 'expo-router';

import {
  mockBackend,
  presentationPreferencesFixture,
  robotCapabilitiesFixture,
  robotCapabilityRowsFixture,
  robotDeviceFixture,
  robotStatusFixture,
  signInAt,
} from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('robot_connected');

  // A robot whose display passed a self-test under an older firmware, and
  // whose speaker now works. Both halves matter: the stale row is section
  // 124's case, and the speaker is what brings the Audio controls back.
  const rows = robotCapabilityRowsFixture({
    speaker: 'available',
    audio_playback: 'available',
    tts: 'available',
  });
  const display = rows.find((row) => row.key === 'display') as Record<string, unknown>;
  display.state = 'not_verified';
  display.reported_state = 'available';
  display.state_label = 'Not tested yet';
  display.stale = true;
  display.firmware_version = '0.0.9';

  backend = mockBackend({
    status: 'robot_connected',
    devices: [robotDeviceFixture()],
    robotStatus: robotStatusFixture(),
    robotPreferences: presentationPreferencesFixture(),
    robotCapabilities: robotCapabilitiesFixture({
      capabilities: rows,
      display_available: false,
      text_available: false,
      animation_available: true,
      audio_available: true,
      speech_available: true,
      input_available: false,
    }),
  });
});

afterEach(() => {
  backend.restore();
});

it('names every part, says what state it is in, and explains a stale report', async () => {
  renderRouter('app', { initialUrl: '/robot' });

  // The speaker is available, so the Audio controls exist (section 47).
  await waitFor(() => {
    expect(screen.getByText('Loudest')).toBeTruthy();
  });
  expect(screen.queryByText('This Nura has not reported a speaker')).toBeNull();

  await act(async () => {
    router.push('/robot/capabilities');
  });

  await waitFor(() => {
    expect(screen.getByText('Screen')).toBeTruthy();
  });

  // All twelve, in the server's fixed order. A client that only rendered the
  // ones it recognised would silently stop asking about a new one.
  for (const label of [
    'Screen',
    'Text on screen',
    'Animation',
    'Speaker',
    'Spoken words',
    'Sounds and chimes',
    'Microphone',
    'Listening for its name',
    'Camera',
    'Camera detection',
    'Buttons',
    'Touch screen',
  ]) {
    expect(screen.getByText(label)).toBeTruthy();
  }

  // Sections 12 and 91: the state the app acts on, in the server's words.
  expect(screen.getByText('Not tested yet')).toBeTruthy();
  // And section 124's explanation of why it differs from what was reported.
  expect(
    screen.getByText(
      'Reported by an older version of Nura’s software. It has not been checked since.'
    )
  ).toBeTruthy();

  // The parts nothing has reported say so, rather than saying "off" -- one
  // row each, which is section 10's point about twelve keys and not one flag.
  expect(
    screen.getAllByText('Nura has not told us about this part.').length
  ).toBeGreaterThan(2);
  expect(screen.getAllByText('Not reported').length).toBeGreaterThan(2);

  // Nothing here claims the robot works.
  expect(
    screen.getByText(
      'The Nura robot has not been built. Everything here is ready for it, and nothing here has run on a screen or a speaker.'
    )
  ).toBeTruthy();
});
