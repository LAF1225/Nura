/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * What Nura can reach (PRD 12, sections 25, 26, 27, 28, 29, 57 and 83).
 *
 * The screen exists so that somebody who asked Nura about the weather can find
 * out why it could not answer, rather than concluding the assistant is broken.
 *
 * **Every sentence it shows is the server's**, derived from whether a provider
 * is both named and implemented -- none is, in any deployment. So the test
 * asserts the PRD's own wording, word for word, and that nothing on the screen
 * suggests the three external keys might work.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
  backend = mockBackend({ status: 'onboarding_complete' });
});

afterEach(() => {
  backend.restore();
});

it('says weather, news and an external calendar are not set up in this build', async () => {
  renderRouter('app', { initialUrl: '/daily/capabilities' });

  await waitFor(() => {
    expect(screen.getByText('Weather')).toBeTruthy();
  });

  // --- the PRD's own sentences ----------------------------------------------
  expect(screen.getByText('Live weather is not configured in this build.')).toBeTruthy();
  expect(
    screen.getByText('Live news access is not configured in this build.')
  ).toBeTruthy();
  expect(
    screen.getByText('I can add that to Nura, but an external calendar is not connected.')
  ).toBeTruthy();

  // --- and the state, in words beside each one ------------------------------
  expect(screen.getAllByText('Not set up in this build').length).toBe(3);
  expect(screen.getAllByText('Available').length).toBe(4);

  // Announced as one sentence per row, so a screen reader hears the state
  // rather than seeing a chip.
  expect(
    screen.getByLabelText('Weather. Live weather is not configured in this build.')
  ).toBeTruthy();

  // --- what the screen says about the build ---------------------------------
  expect(
    screen.getByText(
      'Nura cannot look anything up on the internet in this build, and nothing ' +
        'you add here goes to any calendar outside Nura.'
    )
  ).toBeTruthy();

  // --- and what it never says -----------------------------------------------
  for (const claim of ['Connect', 'Coming soon', 'Sign in to', 'Enable']) {
    expect(screen.queryByText(new RegExp(claim))).toBeNull();
  }
});
