/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The robot screens, read out loud (PRD 11, sections 46, 95, 106 and 130).
 *
 * Section 130 asks for screen-reader labels and for Light/Dark/System to work.
 * This file is the first half; `themeRendering.test.tsx` covers the second for
 * every screen at once.
 *
 * Three things are under test, and each one is a decision made in
 * `RobotCards.tsx` rather than an afterthought.
 *
 * **A state is announced, never only drawn.** A capability row reads as
 * "Screen: Not tested yet", a mode reads as a sentence, and the preview's
 * cards read as their layout and their lines. Nothing is carried by a colour
 * or a chip alone.
 *
 * **The empty state is a sentence, not a disabled screen.** An account with no
 * robot is told what these settings are for and offered the setup flow -- the
 * same decision PRD 2 made about an offline robot, which is never described as
 * broken.
 *
 * **The preview says it is a preview** (section 95), in an `alert` role so a
 * screen reader reaches it before the cards it is about.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { router } from 'expo-router';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('robot_connected');
  // No robot at all, which is every account today.
  backend = mockBackend({ status: 'robot_connected', devices: [] });
});

afterEach(() => {
  backend.restore();
});

it('explains itself with no robot, and the preview announces what it is', async () => {
  renderRouter('app', { initialUrl: '/robot' });

  await waitFor(() => {
    expect(screen.getByText('No Nura connected yet')).toBeTruthy();
  });

  // Not a screen of dead controls: a sentence and a way forward.
  expect(
    screen.getByText(
      'Set up a Nura to choose how it looks and behaves. These settings wait here until you do.'
    )
  ).toBeTruthy();
  expect(screen.getByText('Set up Nura')).toBeTruthy();
  expect(screen.queryByText('Brightest')).toBeNull();
  expect(screen.queryByText('Loudest')).toBeNull();

  // The title is a header, so a screen reader can jump to it.
  const title = screen.getByText('Nura Device');
  expect(title.props.accessibilityRole).toBe('header');

  // --- the preview, which needs no robot at all ---------------------------

  await act(async () => {
    router.push('/robot/preview');
  });

  await waitFor(() => {
    expect(screen.getByText('Preview only')).toBeTruthy();
  });

  // Section 95: the disclaimer is an alert, so it is announced rather than
  // being a caption somebody swipes past.
  const disclaimer = screen.getByLabelText(
    'Preview only. A drawing of how each kind of card is laid out on Nura’s screen.'
  );
  expect(disclaimer.props.accessibilityRole).toBe('alert');

  // Each sample card is announced as its layout and its lines together, so a
  // screen reader hears one coherent thing rather than four fragments.
  expect(
    screen.getByLabelText(
      'EMERGENCY layout. EMERGENCY MODE. Nura is processing your safety request.. Calling is not configured.'
    )
  ).toBeTruthy();
  expect(
    screen.getByLabelText('STATUS layout. Safety Monitoring. ON until 10:30 PM')
  ).toBeTruthy();

  // The medication sample is the private one, because private is the default
  // (section 104) and a preview that named a tablet would teach the wrong
  // expectation.
  expect(
    screen.getByLabelText(
      'REMINDER layout. Medication. Reminder due. Use the Nura app to respond.'
    )
  ).toBeTruthy();
  expect(screen.queryByText('Metformin')).toBeNull();

  // Nothing in the preview claims the robot drew any of it.
  expect(
    screen.getByText(
      'This is how the card would look on Nura’s screen. It does not mean the robot showed it.'
    )
  ).toBeTruthy();
});
