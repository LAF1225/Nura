/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * What Nura was asked to show (PRD 11, sections 14, 20, 22, 96 and 130).
 *
 * The distinction this screen exists to keep is section 14's, and it is the
 * single most important claim in PRD 11: **the backend handing a command over
 * is not the robot showing it.** A card that was sent and never acknowledged
 * reads as "sent to Nura", and nothing in this app can turn that into "shown".
 *
 * Three things are under test.
 *
 * **Each row's sentence is the server's.** "Medication reminder — sent to
 * Nura" is rendered by `services/robot/wording.py`, so the two halves of
 * section 14 cannot come apart in a client that assembled its own.
 *
 * **A private reminder stays private here** (section 22). The summary under
 * each line is the payload the robot was *sent*, already reduced to the
 * privacy level in force -- so the history cannot show a medication name the
 * robot never received.
 *
 * **A failure says what failed, and a withdrawal says why.** Both from stable
 * codes turned into sentences on the server, never a firmware error string
 * (section 67).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { router } from 'expo-router';

import {
  mockBackend,
  presentationFixture,
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
    robotStatus: robotStatusFixture({ queue_depth: 2 }),
    robotCapabilities: robotCapabilitiesFixture(),
    robotPreferences: presentationPreferencesFixture(),
    robotPresentations: [
      // Sent, never acknowledged -- which is every card this project has ever
      // produced, because no physical robot has acknowledged anything.
      presentationFixture({ id: 'p1', status: 'sent' }),
      // A private medication reminder that expired unshown (section 56).
      presentationFixture({
        id: 'p2',
        status: 'expired',
        line: 'Medication reminder — expired',
      }),
      // A family message withdrawn because something more urgent arrived
      // (section 17).
      presentationFixture({
        id: 'p3',
        presentation_type: 'family_message',
        status: 'cancelled',
        layout: 'MESSAGE',
        source: 'family_message',
        priority: 60,
        title: 'Message',
        summary: 'Ayesha',
        cancel_reason: 'preempted',
        line: 'Family message — withdrawn: something more urgent took the screen',
      }),
      // A card this robot has no hardware for (section 123).
      presentationFixture({
        id: 'p4',
        status: 'not_supported',
        failure_code: 'no_display',
        line: 'Medication reminder — not supported on this Nura: this Nura has not reported a screen',
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('says sent rather than shown, and keeps a private reminder private', async () => {
  renderRouter('app', { initialUrl: '/robot' });

  await waitFor(() => {
    expect(screen.getByText('Nura Device')).toBeTruthy();
  });
  // The status card says how many are waiting, from the server's own count.
  await waitFor(() => {
    expect(screen.getByText('2 items waiting for Nura')).toBeTruthy();
  });

  await act(async () => {
    router.push('/robot/history');
  });

  await waitFor(() => {
    expect(screen.getByText('Medication reminder — sent to Nura')).toBeTruthy();
  });

  // Section 14: nothing reads as shown, because nothing acknowledged anything.
  expect(screen.queryByText('Medication reminder — shown')).toBeNull();
  expect(screen.getByText('Medication reminder — expired')).toBeTruthy();

  // Section 67: a stable code became a sentence, and no firmware error text
  // reached the screen.
  expect(
    screen.getByText(
      'Medication reminder — not supported on this Nura: this Nura has not reported a screen'
    )
  ).toBeTruthy();

  // Section 17, as the person sees it afterwards.
  expect(
    screen.getByText('Family message — withdrawn: something more urgent took the screen')
  ).toBeTruthy();

  // Section 22: the summary is what the robot was sent. A private reminder
  // says "Reminder due" here as well, and the tablet is not named anywhere.
  expect(screen.getAllByText('Reminder due').length).toBeGreaterThan(0);
  expect(screen.queryByText('Metformin')).toBeNull();

  // And the screen says why "shown" needs more than the backend's word.
  expect(
    screen.getByText(
      'Nura has to confirm that it drew something before this says it was shown.'
    )
  ).toBeTruthy();
  expect(
    screen.getByText(
      'Reminders are listed as Nura received them, so a private reminder stays private here too.'
    )
  ).toBeTruthy();
});
