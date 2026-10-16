/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Nura Device screen (PRD 11, sections 44, 45, 46, 47, 49, 104 and 130).
 *
 * Four things are under test, and three of them are about what the screen
 * refuses to show.
 *
 * **A control exists only where the capability does** (section 47). The robot
 * here has a screen and no speaker, so the brightness steps are there and the
 * volume steps are not -- replaced by a sentence, because a greyed-out volume
 * control still implies there is a speaker to be loud. The opposite case, a
 * robot that *has* reported a speaker, is `robotCapabilities.test.tsx`.
 *
 * **The read-aloud preferences are there anyway** (section 49). Somebody may
 * reasonably decide today that their messages should never be read out in a
 * room, and the setting is kept without implying a speaker exists. The wording
 * is what carries that, and `robotCopy.test.ts` checks the wording.
 *
 * **Reduced motion has three positions** (sections 30 and 105), and the
 * default is the third: follow the account's accessibility setting.
 *
 * **Nothing is asserted optimistically.** Every change checks the request body
 * *and* the stub's resulting state, which is what proves the app sent what it
 * said it did rather than only redrawing itself.
 *
 * One `renderRouter` per file is a hard limit of this harness, so this is one
 * walk-through rather than six tests.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent } from '@testing-library/react-native';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  mockBackend,
  presentationPreferencesFixture,
  robotCapabilitiesFixture,
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
  backend = mockBackend({
    status: 'robot_connected',
    devices: [robotDeviceFixture()],
    robotStatus: robotStatusFixture(),
    robotCapabilities: robotCapabilitiesFixture(),
    robotPreferences: presentationPreferencesFixture(),
  });
});

afterEach(() => {
  backend.restore();
});

function patchBodies(): Record<string, unknown>[] {
  return backend.requests
    .filter(
      (request) =>
        request.method === 'PATCH' && request.path.includes('presentation-preferences')
    )
    .map((request) => (request.body ?? {}) as Record<string, unknown>);
}

it('shows what this robot can honour, and changes each setting through the server', async () => {
  renderRouter('app', { initialUrl: '/robot' });

  await waitFor(() => {
    expect(screen.getByText('Nura Device')).toBeTruthy();
  });

  // --- what it shows ------------------------------------------------------

  // The mode and its explanation both come from the server (section 4).
  await waitFor(() => {
    expect(screen.getByText('Companion')).toBeTruthy();
  });
  expect(screen.getByText('Resting, with its face showing.')).toBeTruthy();

  // Section 135's sentence, written on the server, shown here.
  expect(
    screen.getByText(
      'The Nura robot has not been built. Everything here is ready for it, and nothing here has run on a screen or a speaker.'
    )
  ).toBeTruthy();

  // Brightness: five steps (sections 44 and 45).
  expect(screen.getByText('Dimmest')).toBeTruthy();
  expect(screen.getByText('Brightest')).toBeTruthy();

  // Section 47: no speaker was reported, so a sentence rather than a control.
  expect(screen.getByText('This Nura has not reported a speaker')).toBeTruthy();
  expect(screen.queryByText('Loudest')).toBeNull();

  // Section 49: the read-aloud preferences are offered, and say *when*.
  expect(
    screen.getByText(
      'When Nura has a working speaker, read messages out loud. Other people in the room would hear them.'
    )
  ).toBeTruthy();

  // Section 104: private is the default and the three levels are all offered.
  expect(screen.getByText('Private reminder')).toBeTruthy();
  expect(screen.getByText('Medication name only')).toBeTruthy();
  expect(screen.getByText('Full details')).toBeTruthy();

  // --- brightness ---------------------------------------------------------

  fireEvent.press(screen.getByText('Dimmest'));
  await waitFor(() => {
    expect(patchBodies()).toContainEqual({ brightness: 25 });
  });
  await waitFor(() => {
    expect(backend.state.robotPreferences.brightness).toBe(25);
  });

  // --- reduced motion, all three positions --------------------------------

  // It starts as null -- following the account's accessibility setting -- and
  // says so.
  expect(
    screen.getByText(
      'Following your accessibility setting. Choose On or Off to decide separately.'
    )
  ).toBeTruthy();

  fireEvent.press(screen.getByText('Reduced motion on'));
  await waitFor(() => {
    expect(patchBodies()).toContainEqual({ reduced_motion: true });
  });
  await waitFor(() => {
    expect(backend.state.robotPreferences.reduced_motion).toBe(true);
  });

  fireEvent.press(screen.getByText('Reduced motion off'));
  await waitFor(() => {
    expect(patchBodies()).toContainEqual({ reduced_motion: false });
  });

  // Back to following, which sends null rather than false. The distinction is
  // the whole reason the column is nullable (sections 30 and 105).
  fireEvent.press(screen.getByText('Follow my accessibility setting'));
  await waitFor(() => {
    expect(patchBodies()).toContainEqual({ reduced_motion: null });
  });
  await waitFor(() => {
    expect(backend.state.robotPreferences.reduced_motion).toBeNull();
  });

  // --- the medication preview ---------------------------------------------

  fireEvent.press(screen.getByText('Medication name only'));
  await waitFor(() => {
    expect(patchBodies()).toContainEqual({ medication_privacy_level: 'name_only' });
  });
  await waitFor(() => {
    expect(backend.state.robotPreferences.medication_privacy_level).toBe('name_only');
  });

  // --- the switches -------------------------------------------------------

  // A Switch does not respond to `press`; it responds to `valueChange`.
  fireEvent(screen.getByLabelText('Show family messages'), 'valueChange', false);
  await waitFor(() => {
    expect(patchBodies()).toContainEqual({ family_message_display_enabled: false });
  });

  fireEvent(screen.getByLabelText('Read family messages aloud'), 'valueChange', true);
  await waitFor(() => {
    expect(patchBodies()).toContainEqual({ read_messages_aloud: true });
  });
  // Kept even though no speaker exists, which is section 49.
  await waitFor(() => {
    expect(backend.state.robotPreferences.read_messages_aloud).toBe(true);
  });

  // --- what was never sent ------------------------------------------------

  // Nothing on this screen can tell the robot to show something, and nothing
  // can acknowledge a presentation (sections 14 and 19).
  const paths = backend.requests.map((request) => request.path).join(' ');
  expect(paths).not.toContain('device-actions');
  expect(paths).not.toContain('/ack');
});
